import csv
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.config import DATA_DIR, ensure_data_dirs, settings


SAMPLE_ROWS = [
    {
        "lon": "107.0535",
        "lat": "16.7924",
        "huyen": "Huong Hoa",
        "xa": "Huong Phung",
        "thon": "Cu Bai",
        "dien_tich": "2200",
        "quy_mo": "trung binh",
        "mo_ta": "Diem sat lo taluy duong, can theo doi sau mua lon",
    },
    {
        "lon": "106.9821",
        "lat": "16.6593",
        "huyen": "Dakrong",
        "xa": "Ta Long",
        "thon": "A Vao",
        "dien_tich": "4100",
        "quy_mo": "lon",
        "mo_ta": "Vet truot tren suon doc gan khu dan cu",
    },
    {
        "lon": "107.1877",
        "lat": "16.8206",
        "huyen": "Gio Linh",
        "xa": "Linh Truong",
        "thon": "Khe Me",
        "dien_tich": "900",
        "quy_mo": "nho",
        "mo_ta": "Diem truot nho ven duong dat",
    },
    {
        "lon": "106.9132",
        "lat": "16.7388",
        "huyen": "Dakrong",
        "xa": "Ba Long",
        "thon": "Khe Van",
        "dien_tich": "6300",
        "quy_mo": "lon",
        "mo_ta": "Khu vuc co tien su sat lo sau mua bao",
    },
]


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    ensure_data_dirs()
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    ensure_sample_csv()
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lon REAL NOT NULL,
                lat REAL NOT NULL,
                huyen TEXT,
                xa TEXT,
                thon TEXT,
                dien_tich REAL,
                quy_mo TEXT,
                mo_ta TEXT,
                source TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_new INTEGER NOT NULL DEFAULT 0,
                matched_inventory_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS detection_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                input_path TEXT NOT NULL,
                output_video_path TEXT,
                output_image_path TEXT,
                media_type TEXT NOT NULL,
                lon REAL,
                lat REAL,
                area_m2 REAL,
                width_m REAL,
                height_m REAL,
                duplicate_mode INTEGER NOT NULL,
                decision TEXT NOT NULL,
                alert_message TEXT,
                predict_status TEXT NOT NULL,
                predict_payload TEXT,
                inventory_id INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS raster_layers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                factor_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS susceptibility_maps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                raster_path TEXT,
                overlay_path TEXT,
                bbox_json TEXT,
                source_detection_id INTEGER,
                status TEXT NOT NULL,
                message TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        seed_inventory(conn)
        auto_register_existing_rasters(conn)
        auto_register_existing_susceptibility(conn)
        conn.commit()


def ensure_sample_csv() -> None:
    if settings.csv_path.exists():
        return
    with settings.csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["lon", "lat", "huyen", "xa", "thon", "dien_tich", "quy_mo", "mo_ta"],
        )
        writer.writeheader()
        writer.writerows(SAMPLE_ROWS)


def read_csv_points() -> list[dict[str, Any]]:
    ensure_sample_csv()
    rows: list[dict[str, Any]] = []
    with settings.csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("lon") or not row.get("lat"):
                continue
            rows.append(
                {
                    "lon": float(row["lon"]),
                    "lat": float(row["lat"]),
                    "huyen": row.get("huyen", ""),
                    "xa": row.get("xa", ""),
                    "thon": row.get("thon", ""),
                    "dien_tich": float(row.get("dien_tich") or 0),
                    "quy_mo": row.get("quy_mo", ""),
                    "mo_ta": row.get("mo_ta", ""),
                }
            )
    return rows


def read_new_csv_points() -> list[dict[str, Any]]:
    if not settings.csv_new_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with settings.csv_new_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("lon") or not row.get("lat"):
                continue
            rows.append(
                {
                    "lon": float(row["lon"]),
                    "lat": float(row["lat"]),
                    "huyen": "",
                    "xa": "",
                    "thon": "",
                    "dien_tich": float(row.get("dien_tich") or 0),
                    "quy_mo": row.get("quy_mo", ""),
                    "mo_ta": row.get("mo_ta", "Diem sat lo moi tu CSV moi"),
                    "label": row.get("label", ""),
                }
            )
    return rows


def read_image_metadata_points() -> dict[str, dict[str, Any]]:
    if not settings.image_metadata_path.exists():
        return {}

    points: dict[str, dict[str, Any]] = {}
    with settings.image_metadata_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            file_name = (row.get("file_name") or "").strip()
            if not file_name or not row.get("lon") or not row.get("lat"):
                continue
            key = Path(file_name).name.lower()
            try:
                lon = float(row["lon"])
                lat = float(row["lat"])
            except ValueError:
                continue
            points[key] = {
                "file_name": file_name,
                "lon": lon,
                "lat": lat,
                "huyen": district_for_metadata(lon, lat),
                "xa": "",
                "thon": "",
                "dien_tich": 0,
                "quy_mo": "",
                "mo_ta": f"Toa do anh lay tu metadata {settings.image_metadata_path.name}.",
                "label": row.get("label", ""),
                "pixel_size_m": float(row.get("pixel_size_m") or 0),
                "chip_size_px": int(float(row.get("chip_size_px") or 0)),
                "chip_size_m": float(row.get("chip_size_m") or 0),
                "crs": row.get("crs", ""),
            }
    return points


def district_for_metadata(lon: float, lat: float) -> str:
    try:
        from backend.districts import district_for_point

        return district_for_point(lon, lat)
    except Exception:
        return ""


def seed_inventory(conn: sqlite3.Connection) -> None:
    for row in read_csv_points():
        exists = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM inventory
            WHERE source = 'csv_kiem_ke'
              AND ABS(lon - ?) < 0.000001
              AND ABS(lat - ?) < 0.000001
            """,
            (row["lon"], row["lat"]),
        ).fetchone()["total"]
        if exists:
            continue
        conn.execute(
            """
            INSERT INTO inventory (
                lon, lat, huyen, xa, thon, dien_tich, quy_mo, mo_ta,
                source, observed_at, created_at, is_new
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'csv_kiem_ke', ?, ?, 0)
            """,
            (
                row["lon"],
                row["lat"],
                row["huyen"],
                row["xa"],
                row["thon"],
                row["dien_tich"],
                row["quy_mo"],
                row["mo_ta"],
                "khong_co_du_lieu",
                now_iso(),
            ),
        )
    conn.commit()


def auto_register_existing_rasters(conn: sqlite3.Connection) -> None:
    raster_root = DATA_DIR / "raster"
    if not raster_root.exists():
        return
    for path in raster_root.rglob("*.tif"):
        exists = conn.execute(
            "SELECT COUNT(*) AS total FROM raster_layers WHERE file_path = ?",
            (str(path),),
        ).fetchone()["total"]
        if exists:
            continue
        factor_type = path.parent.name
        name = path.stem
        conn.execute(
            """
            INSERT INTO raster_layers (name, factor_type, file_path, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, factor_type, str(path), now_iso()),
        )


def auto_register_existing_susceptibility(conn: sqlite3.Connection) -> None:
    susceptibility_root = DATA_DIR / "susceptibility"
    if not susceptibility_root.exists():
        return
    for tif_path in list(susceptibility_root.glob("*.tif")) + list(susceptibility_root.glob("*.tiff")):
        exists = conn.execute(
            "SELECT COUNT(*) AS total FROM susceptibility_maps WHERE raster_path = ?",
            (str(tif_path),),
        ).fetchone()["total"]
        preview_path, bbox = susceptibility_tif_preview(tif_path)
        if exists:
            conn.execute(
                """
                UPDATE susceptibility_maps
                SET overlay_path = ?, bbox_json = ?, message = ?
                WHERE raster_path = ?
                """,
                (
                    str(preview_path),
                    f'{{"west":{bbox["west"]},"south":{bbox["south"]},"east":{bbox["east"]},"north":{bbox["north"]}}}',
                    "Da tao PNG preview tu GeoTIFF ban do nhay cam.",
                    str(tif_path),
                ),
            )
            continue
        conn.execute(
            """
            INSERT INTO susceptibility_maps (
                title, raster_path, overlay_path, bbox_json, status, message, created_at
            ) VALUES (?, ?, ?, ?, 'done', ?, ?)
            """,
            (
                tif_path.stem,
                str(tif_path),
                str(preview_path),
                f'{{"west":{bbox["west"]},"south":{bbox["south"]},"east":{bbox["east"]},"north":{bbox["north"]}}}',
                "Da tao PNG preview tu GeoTIFF ban do nhay cam.",
                now_iso(),
            ),
        )
    for path in susceptibility_root.glob("*.png"):
        exists = conn.execute(
            "SELECT COUNT(*) AS total FROM susceptibility_maps WHERE overlay_path = ?",
            (str(path),),
        ).fetchone()["total"]
        if exists:
            continue
        bbox = {"west": 106.55, "south": 16.30, "east": 107.45, "north": 17.15}
        conn.execute(
            """
            INSERT INTO susceptibility_maps (
                title, overlay_path, bbox_json, status, message, created_at
            ) VALUES (?, ?, ?, 'done', ?, ?)
            """,
            (
                path.stem,
                str(path),
                '{"west":106.55,"south":16.30,"east":107.45,"north":17.15}',
                "Da nap ban do nhay cam co san trong thu muc data/susceptibility.",
                now_iso(),
            ),
        )


def susceptibility_tif_preview(tif_path: Path) -> tuple[Path, dict[str, float]]:
    import numpy as np
    import rasterio
    from rasterio.warp import transform_bounds
    from PIL import Image

    preview_path = tif_path.with_name(f"{tif_path.stem}_preview.png")
    with rasterio.open(tif_path) as src:
        arr = src.read(1).astype("float32")
        if src.nodata is not None:
            arr = np.where(arr == src.nodata, np.nan, arr)
        valid = np.isfinite(arr)
        norm = np.zeros(arr.shape, dtype="float32")
        if valid.any():
            low, high = np.nanpercentile(arr[valid], [2, 98])
            norm = np.clip((arr - low) / max(high - low, 1e-6), 0, 1)
        norm = np.nan_to_num(norm, nan=0.0)
        classes = np.clip(np.floor(norm * 5), 0, 4).astype(np.uint8)
        colors = np.array(
            [
                [37, 99, 235, 150],    # Rat thap
                [14, 165, 233, 160],   # Thap
                [34, 197, 94, 170],    # Trung binh
                [245, 158, 11, 180],   # Cao
                [220, 38, 38, 190],    # Rat cao
            ],
            dtype=np.uint8,
        )
        rgba = np.zeros((arr.shape[0], arr.shape[1], 4), dtype=np.uint8)
        rgba[valid] = colors[classes[valid]]
        rgba[..., 3] = np.where(valid, rgba[..., 3], 0)
        Image.fromarray(rgba).save(preview_path)
        if src.crs and str(src.crs).upper() not in ("EPSG:4326", "OGC:CRS84"):
            west, south, east, north = transform_bounds(
                src.crs, "EPSG:4326", *src.bounds, densify_pts=21
            )
        else:
            west, south, east, north = src.bounds
        bbox = {"west": float(west), "south": float(south), "east": float(east), "north": float(north)}
    return preview_path, bbox


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def insert_inventory(conn: sqlite3.Connection, item: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO inventory (
            lon, lat, huyen, xa, thon, dien_tich, quy_mo, mo_ta,
            source, observed_at, created_at, is_new, matched_inventory_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["lon"],
            item["lat"],
            item.get("huyen", ""),
            item.get("xa", ""),
            item.get("thon", ""),
            item.get("dien_tich", 0),
            item.get("quy_mo", ""),
            item.get("mo_ta", ""),
            item.get("source", "ai_detected"),
            item.get("observed_at", now_iso()),
            now_iso(),
            1 if item.get("is_new") else 0,
            item.get("matched_inventory_id"),
        ),
    )
    return int(cur.lastrowid)


def media_url(path: str | Path | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    try:
        rel = p.relative_to(settings.database_path.parent)
    except ValueError:
        rel = p
    return "/media/" + rel.as_posix()
