import json
import math
import random
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from PIL import Image

from backend.config import DATA_DIR, ensure_data_dirs, settings
from backend.database import (
    connect,
    insert_inventory,
    media_url,
    now_iso,
    read_csv_points,
    read_image_metadata_points,
    read_new_csv_points,
    row_to_dict,
    rows_to_dicts,
)
from backend.districts import district_for_point
from backend.models import (
    create_mask_comparison_overlay,
    draw_prediction_overlay,
    predict_image_remote,
    predict_video_remote,
    preprocess_image_512,
    susceptibility_overlay_png,
    true_mask_preview,
    video_to_browser_preview,
    video_to_gif_preview,
    write_overlay_video_from_prediction,
)


VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}

RASTER_FOLDERS = {
    "do_cao": "do_cao",
    "do_doc": "do_doc",
    "huong_suon": "huong_suon",
    "do_cong": "do_cong",
    "twi": "twi",
    "luong_mua": "luong_mua",
    "thach_hoc": "thach_hoc",
    "lop_phu": "lop_phu",
    "khoang_cach_duong": "khoang_cach_duong",
    "khoang_cach_song": "khoang_cach_song",
}


def safe_name(filename: str | None) -> str:
    name = Path(filename or "upload").name
    clean = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)
    return clean or "upload"


async def save_upload(file: UploadFile, folder: str) -> Path:
    ensure_data_dirs()
    target_dir = DATA_DIR / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / f"{uuid4().hex}_{safe_name(file.filename)}"
    output_path.write_bytes(await file.read())
    return output_path


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def shifted_coordinate(lon: float, lat: float) -> tuple[float, float]:
    distance_km = random.uniform(settings.new_point_shift_km_min, settings.new_point_shift_km_max)
    bearing = random.uniform(0, 2 * math.pi)
    d_lat = (distance_km / 111.0) * math.cos(bearing)
    d_lon = (distance_km / (111.0 * max(math.cos(math.radians(lat)), 0.2))) * math.sin(bearing)
    return round(lon + d_lon, 6), round(lat + d_lat, 6)


def nearest_inventory(lon: float, lat: float) -> tuple[dict[str, Any] | None, float | None]:
    with connect() as conn:
        rows = rows_to_dicts(conn.execute("SELECT * FROM inventory").fetchall())
    if not rows:
        return None, None

    distances = [
        (row, haversine_m(lon, lat, float(row["lon"]), float(row["lat"])))
        for row in rows
    ]
    row, distance = min(distances, key=lambda item: item[1])
    return row, distance


def choose_mock_location(force_duplicate: bool) -> tuple[dict[str, Any], dict[str, Any] | None, float | None]:
    if force_duplicate:
        source = random.choice(read_csv_points())
    else:
        new_points = read_new_csv_points()
        source = random.choice(new_points) if new_points else random.choice(read_csv_points())
        if not new_points:
            source["lon"], source["lat"] = shifted_coordinate(source["lon"], source["lat"])
        source["huyen"] = district_for_point(source["lon"], source["lat"])
        source["xa"] = ""
        source["thon"] = ""

    lon = source["lon"]
    lat = source["lat"]
    matched, distance = nearest_inventory(lon, lat)
    return source, matched, distance


def choose_image_upload_location(
    filename: str,
    force_duplicate: bool,
) -> tuple[dict[str, Any], dict[str, Any] | None, float | None, bool]:
    metadata = read_image_metadata_points()
    key = Path(filename).name.lower()
    if key in metadata:
        source = dict(metadata[key])
        source["huyen"] = source.get("huyen") or district_for_point(source["lon"], source["lat"])
        source["xa"] = source.get("xa", "")
        source["thon"] = source.get("thon", "")
        matched, distance = nearest_inventory(source["lon"], source["lat"])
        return source, matched, distance, True

    source, matched, distance = choose_mock_location(force_duplicate)
    return source, matched, distance, False


def extract_first_frame(video_path: Path) -> Path:
    try:
        import cv2
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="Chua cai opencv-python de xu ly video.") from exc

    capture = cv2.VideoCapture(str(video_path))
    ok, frame = capture.read()
    capture.release()
    if not ok:
        raise HTTPException(status_code=400, detail="Khong doc duoc frame dau tien tu video.")

    frame_path = DATA_DIR / "output/image" / f"{video_path.stem}_frame0.jpg"
    cv2.imwrite(str(frame_path), frame)
    return frame_path


def create_output_video(video_path: Path, prediction: dict[str, Any]) -> Path:
    try:
        import cv2
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="Chua cai opencv-python de tao video output.") from exc

    output_path = DATA_DIR / "output/video" / f"{video_path.stem}_segmented.mp4"
    capture = cv2.VideoCapture(str(video_path))
    fps = capture.get(cv2.CAP_PROP_FPS) or 24
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)
    writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))

    bbox = prediction.get("bbox_px") or {}
    x1 = int(bbox.get("x1", width * 0.4))
    y1 = int(bbox.get("y1", height * 0.4))
    x2 = int(bbox.get("x2", width * 0.6))
    y2 = int(bbox.get("y2", height * 0.6))

    while True:
        ok, frame = capture.read()
        if not ok:
            break
        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 220), -1)
        frame = cv2.addWeighted(overlay, 0.32, frame, 0.68, 0)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 220), 3)
        cv2.putText(
            frame,
            "Landslide",
            (x1, max(y1 - 12, 24)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 220),
            2,
            cv2.LINE_AA,
        )
        writer.write(frame)

    capture.release()
    writer.release()
    return output_path


def compact_video_prediction(prediction: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in prediction.items()
        if key not in {"overlay_video_base64"}
    }


async def run_detection(file: UploadFile, force_duplicate: bool, update_susceptibility: bool) -> dict[str, Any]:
    suffix = Path(file.filename or "").suffix.lower()
    is_video = suffix in VIDEO_SUFFIXES or (file.content_type or "").startswith("video/")
    folder = "uploads/video" if is_video else "uploads/image"
    input_path = await save_upload(file, folder)
    return await run_detection_path(
        input_path=input_path,
        filename=file.filename or input_path.name,
        content_type=file.content_type,
        force_duplicate=force_duplicate,
        update_susceptibility=update_susceptibility,
        use_upload_metadata=not is_video,
    )


async def run_existing_upload(relative_path: str, force_duplicate: bool, update_susceptibility: bool) -> dict[str, Any]:
    base = (DATA_DIR / "uploads").resolve()
    input_path = (DATA_DIR / relative_path.lstrip("/\\")).resolve()
    if base not in input_path.parents:
        raise HTTPException(status_code=400, detail="File phai nam trong data/uploads.")
    if not input_path.exists():
        raise HTTPException(status_code=404, detail="Khong tim thay file upload co san.")
    return await run_detection_path(
        input_path=input_path,
        filename=input_path.name,
        content_type=None,
        force_duplicate=force_duplicate,
        update_susceptibility=update_susceptibility,
        use_upload_metadata=True,
    )


def segment_sample_paths(sample_name: str) -> tuple[Path, Path | None]:
    safe_sample = Path(sample_name).name
    image_path = DATA_DIR / "segment" / "img" / safe_sample
    mask_path = DATA_DIR / "segment" / "mask" / safe_sample
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Khong tim thay anh mau trong data/segment/img.")
    return image_path, mask_path if mask_path.exists() else None


async def run_segment_sample(sample_name: str, force_duplicate: bool, update_susceptibility: bool) -> dict[str, Any]:
    image_path, mask_path = segment_sample_paths(sample_name)
    return await run_detection_path(
        input_path=image_path,
        filename=image_path.name,
        content_type=None,
        force_duplicate=force_duplicate,
        update_susceptibility=update_susceptibility,
        true_mask_path=mask_path,
        use_upload_metadata=False,
    )


async def run_detection_path(
    input_path: Path,
    filename: str,
    content_type: str | None,
    force_duplicate: bool,
    update_susceptibility: bool,
    true_mask_path: Path | None = None,
    use_upload_metadata: bool = False,
) -> dict[str, Any]:
    suffix = input_path.suffix.lower()
    is_video = suffix in VIDEO_SUFFIXES or (content_type or "").startswith("video/")

    if is_video:
        return await run_video_detection_path(
            input_path=input_path,
            filename=filename,
            force_duplicate=force_duplicate,
            update_susceptibility=update_susceptibility,
        )

    preprocessed_path = DATA_DIR / "output/image" / f"{input_path.stem}_512.jpg"
    output_image_path = DATA_DIR / "output/image" / f"{input_path.stem}_segmented.jpg"
    preprocess_image_512(input_path, preprocessed_path)
    prediction = await predict_image_remote(preprocessed_path)
    create_mask_comparison_overlay(
        preprocessed_path,
        true_mask_path,
        prediction,
        output_image_path,
    )
    true_mask_output_path = None
    if true_mask_path:
        true_mask_output_path = DATA_DIR / "output/image" / f"{input_path.stem}_true_mask.png"
        true_mask_preview(true_mask_path, true_mask_output_path)
    output_video_path = None
    media_type = "image"

    metadata_used = False
    if use_upload_metadata:
        location, matched, distance, metadata_used = choose_image_upload_location(filename, force_duplicate)
    else:
        location, matched, distance = choose_mock_location(force_duplicate)
    area_m2 = float(prediction.get("area_m2") or location.get("dien_tich") or 0)
    location["dien_tich"] = round(area_m2, 2)
    if metadata_used:
        location["mo_ta"] = (
            f"Phat hien tu anh upload {Path(filename).name}; toa do lay tu quangtri_metadata.csv."
        )
    else:
        location["mo_ta"] = (
            "Phat hien moi tu video/anh upload, toa do mock tu data.csv va anh 4.7m/pixel."
        )
    location["source"] = "ai_detected"
    location["observed_at"] = now_iso()

    is_duplicate = bool(
        (force_duplicate or metadata_used)
        and matched
        and distance is not None
        and distance <= settings.duplicate_distance_m
    )

    inventory_id = None
    if is_duplicate:
        decision = "duplicate"
        alert = (
            f"Ket qua trung diem kiem ke #{matched['id']} "
            f"({distance:.1f} m), khong them ban ghi moi."
        )
    else:
        decision = "new"
        location["is_new"] = True
        location["matched_inventory_id"] = matched["id"] if matched else None
        with connect() as conn:
            inventory_id = insert_inventory(conn, location)
            conn.commit()
        alert = "Canh bao diem sat lo moi: da them vao database va can kiem chung."

    predict_status = prediction.get("status", "unknown")
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO detection_jobs (
                filename, input_path, output_video_path, output_image_path,
                media_type, lon, lat, area_m2, width_m, height_m,
                duplicate_mode, decision, alert_message, predict_status,
                predict_payload, inventory_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                filename,
                str(input_path),
                str(output_video_path) if output_video_path else None,
                str(output_image_path) if output_image_path else None,
                media_type,
                location["lon"],
                location["lat"],
                area_m2,
                prediction.get("width_m"),
                prediction.get("height_m"),
                1 if force_duplicate else 0,
                decision,
                alert,
                predict_status,
                json.dumps(prediction, ensure_ascii=False),
                inventory_id,
                now_iso(),
            ),
        )
        detection_id = int(cur.lastrowid)
        conn.commit()

    susceptibility_map = None
    if update_susceptibility and decision == "new":
        susceptibility_map = create_susceptibility_map(detection_id, force_new=True)

    return {
        "detection_id": detection_id,
        "media_type": media_type,
        "decision": decision,
        "alert": alert,
        "predict_status": predict_status,
        "prediction": prediction,
        "point": {
            "lon": location["lon"],
            "lat": location["lat"],
            "huyen": location.get("huyen", ""),
            "xa": location.get("xa", ""),
            "thon": location.get("thon", ""),
            "dien_tich": area_m2,
            "quy_mo": location.get("quy_mo", ""),
            "mo_ta": location.get("mo_ta", ""),
            "observed_at": location["observed_at"],
            "inventory_id": inventory_id,
        },
        "matched_inventory": matched,
        "distance_to_match_m": round(distance, 2) if distance is not None else None,
        "metadata_used": metadata_used,
        "metadata_file": Path(filename).name if metadata_used else None,
        "output_video_url": media_url(output_video_path),
        "output_image_url": media_url(output_image_path),
        "preprocessed_image_url": media_url(preprocessed_path),
        "true_mask_url": media_url(true_mask_output_path),
        "susceptibility_map": susceptibility_map,
        "stats": get_stats(),
    }


async def run_video_detection_path(
    input_path: Path,
    filename: str,
    force_duplicate: bool,
    update_susceptibility: bool,
) -> dict[str, Any]:
    prediction = await predict_video_remote(input_path)
    output_video_path = DATA_DIR / "output/video" / f"{input_path.stem}_overlay.mp4"
    write_overlay_video_from_prediction(input_path, prediction, output_video_path)
    output_browser_video_path, output_browser_video_mime_type, output_browser_video_encoder = (
        video_to_browser_preview(
            output_video_path,
            DATA_DIR / "output/video" / f"{input_path.stem}_overlay_browser",
        )
    )
    output_gif_path = DATA_DIR / "output/video" / f"{input_path.stem}_overlay_preview.gif"
    video_to_gif_preview(output_video_path, output_gif_path, prediction)

    location, matched, distance = choose_mock_location(force_duplicate)
    area_pixels = float(prediction.get("total_landslide_area_pixels") or 0)
    area_m2 = area_pixels * settings.pixel_size_m * settings.pixel_size_m
    if area_m2 <= 0:
        area_m2 = float(location.get("dien_tich") or 0)
    location["dien_tich"] = round(area_m2, 2)
    location["mo_ta"] = (
        "Phat hien tu video upload bang /predict-video, overlay video do model tra ve."
    )
    location["source"] = "ai_detected_video"
    location["observed_at"] = now_iso()

    is_duplicate = bool(
        force_duplicate
        and matched
        and distance is not None
        and distance <= settings.duplicate_distance_m
    )

    inventory_id = None
    if is_duplicate:
        decision = "duplicate"
        alert = (
            f"Ket qua video trung diem kiem ke #{matched['id']} "
            f"({distance:.1f} m), khong them ban ghi moi."
        )
    else:
        decision = "new"
        location["is_new"] = True
        location["matched_inventory_id"] = matched["id"] if matched else None
        with connect() as conn:
            inventory_id = insert_inventory(conn, location)
            conn.commit()
        alert = "Canh bao diem sat lo moi tu video: da them vao database va can kiem chung."

    predict_status = prediction.get("status", "unknown")
    compact_prediction = compact_video_prediction(prediction)
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO detection_jobs (
                filename, input_path, output_video_path, output_image_path,
                media_type, lon, lat, area_m2, width_m, height_m,
                duplicate_mode, decision, alert_message, predict_status,
                predict_payload, inventory_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                filename,
                str(input_path),
                str(output_video_path),
                None,
                "video",
                location["lon"],
                location["lat"],
                area_m2,
                None,
                None,
                1 if force_duplicate else 0,
                decision,
                alert,
                predict_status,
                json.dumps(compact_prediction, ensure_ascii=False),
                inventory_id,
                now_iso(),
            ),
        )
        detection_id = int(cur.lastrowid)
        conn.commit()

    susceptibility_map = None
    if update_susceptibility and decision == "new":
        susceptibility_map = create_susceptibility_map(detection_id, force_new=True)

    return {
        "detection_id": detection_id,
        "media_type": "video",
        "decision": decision,
        "alert": alert,
        "predict_status": predict_status,
        "prediction": compact_prediction,
        "video_summary": compact_prediction,
        "point": {
            "lon": location["lon"],
            "lat": location["lat"],
            "huyen": location.get("huyen", ""),
            "xa": location.get("xa", ""),
            "thon": location.get("thon", ""),
            "dien_tich": area_m2,
            "quy_mo": location.get("quy_mo", ""),
            "mo_ta": location.get("mo_ta", ""),
            "observed_at": location["observed_at"],
            "inventory_id": inventory_id,
        },
        "matched_inventory": matched,
        "distance_to_match_m": round(distance, 2) if distance is not None else None,
        "output_browser_video_url": (
            media_url(output_browser_video_path) if output_browser_video_path else None
        ),
        "output_browser_video_mime_type": output_browser_video_mime_type,
        "output_browser_video_encoder": output_browser_video_encoder,
        "output_video_url": media_url(output_video_path),
        "output_gif_url": media_url(output_gif_path) if output_gif_path.exists() else None,
        "output_video_mime_type": prediction.get("overlay_video_mime_type", "video/mp4"),
        "output_image_url": None,
        "preprocessed_image_url": None,
        "true_mask_url": None,
        "susceptibility_map": susceptibility_map,
        "stats": get_stats(),
    }


async def register_raster(file: UploadFile, name: str, factor_type: str) -> dict[str, Any]:
    folder = RASTER_FOLDERS.get(factor_type, factor_type)
    target = await save_upload(file, f"raster/{folder}")
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO raster_layers (name, factor_type, file_path, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, factor_type, str(target), now_iso()),
        )
        conn.commit()
        raster_id = int(cur.lastrowid)
    return {"id": raster_id, "name": name, "factor_type": factor_type, "file_path": str(target)}


def create_susceptibility_map(
    source_detection_id: int | None = None,
    force_new: bool = False,
) -> dict[str, Any]:
    existing = latest_susceptibility_map(prefer_real=True)
    if existing.get("status") != "empty" and not force_new:
        existing["message"] = "Dang hien thi ban do nhay cam LSM that tu data/susceptibility."
        return existing

    if existing.get("status") != "empty" and force_new and existing.get("overlay_path"):
        overlay_path = Path(existing["overlay_path"])
        if overlay_path.exists():
            created_at = now_iso()
            bbox_json = json.dumps(existing.get("bbox")) if existing.get("bbox") else existing.get("bbox_json")
            title = f"Phien ban LSM {created_at}"
            message = "Da tao phien ban ban do moi tu LSM that hien co."
            with connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO susceptibility_maps (
                        title, raster_path, overlay_path, bbox_json,
                        source_detection_id, status, message, created_at
                    ) VALUES (?, ?, ?, ?, ?, 'done', ?, ?)
                    """,
                    (
                        title,
                        existing.get("raster_path"),
                        existing.get("overlay_path"),
                        bbox_json,
                        source_detection_id,
                        message,
                        created_at,
                    ),
                )
                conn.commit()
                map_id = int(cur.lastrowid)
            return {
                **existing,
                "id": map_id,
                "title": title,
                "source_detection_id": source_detection_id,
                "status": "done",
                "message": message,
                "created_at": created_at,
            }

    with connect() as conn:
        points = rows_to_dicts(
            conn.execute("SELECT * FROM inventory WHERE is_new = 1 OR source = 'csv_kiem_ke'").fetchall()
        )

    created_at = now_iso()
    output_path = DATA_DIR / "susceptibility" / f"ban_do_nhay_cam_{uuid4().hex[:8]}.png"
    bbox = susceptibility_overlay_png(points, output_path)

    with connect() as conn:
        raster_count = conn.execute("SELECT COUNT(*) AS total FROM raster_layers").fetchone()["total"]
        status = "done"
        message = (
            f"Da tao ban do nhay cam demo tu {len(points)} diem va {raster_count} lop raster da dang ky."
        )
        cur = conn.execute(
            """
            INSERT INTO susceptibility_maps (
                title, overlay_path, bbox_json, source_detection_id, status, message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"Ban do nhay cam sat lo {created_at}",
                str(output_path),
                json.dumps(bbox),
                source_detection_id,
                status,
                message,
                created_at,
            ),
        )
        conn.commit()
        map_id = int(cur.lastrowid)

    return {
        "id": map_id,
        "title": f"Ban do nhay cam sat lo #{map_id}",
        "overlay_url": media_url(output_path),
        "bbox": bbox,
        "status": status,
        "message": message,
        "created_at": created_at,
        "source_detection_id": source_detection_id,
    }


def list_points() -> list[dict[str, Any]]:
    with connect() as conn:
        return rows_to_dicts(conn.execute("SELECT * FROM inventory ORDER BY created_at DESC").fetchall())


def list_detections() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = rows_to_dicts(
            conn.execute("SELECT * FROM detection_jobs ORDER BY created_at DESC LIMIT 50").fetchall()
        )
    for row in rows:
        row["output_video_url"] = media_url(row.get("output_video_path"))
        row["output_image_url"] = media_url(row.get("output_image_path"))
    return rows


def list_uploads() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for folder, media_type in [("uploads/image", "image")]:
        root = DATA_DIR / folder
        if not root.exists():
            continue
        suffixes = VIDEO_SUFFIXES if media_type == "video" else IMAGE_SUFFIXES
        for path in root.iterdir():
            if path.is_file() and path.suffix.lower() in suffixes:
                rows.append(
                    {
                        "name": path.name,
                        "media_type": media_type,
                        "relative_path": str(path.relative_to(DATA_DIR)).replace("\\", "/"),
                        "size": path.stat().st_size,
                        "url": media_url(path),
                    }
                )
    return sorted(rows, key=lambda row: row["name"].lower())


def tif_preview(path: Path) -> Path:
    if path.suffix.lower() not in (".tif", ".tiff"):
        return path
    preview_dir = DATA_DIR / "segment" / "preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_path = preview_dir / f"{path.stem}.png"
    if preview_path.exists():
        return preview_path

    import numpy as np
    import rasterio
    from PIL import Image

    with rasterio.open(path) as src:
        if src.count >= 3:
            arr = src.read([1, 2, 3]).astype("float32")
            arr = np.moveaxis(arr, 0, -1)
        else:
            band = src.read(1).astype("float32")
            arr = np.repeat(band[:, :, None], 3, axis=2)
        valid = np.isfinite(arr)
        if valid.any():
            low, high = np.nanpercentile(arr[valid], [2, 98])
            arr = np.clip((arr - low) / max(high - low, 1e-6), 0, 1)
        Image.fromarray((np.nan_to_num(arr) * 255).astype("uint8")).save(preview_path)
    return preview_path


def list_segment_samples() -> list[dict[str, Any]]:
    image_dir = DATA_DIR / "segment" / "img"
    mask_dir = DATA_DIR / "segment" / "mask"
    if not image_dir.exists():
        return []

    rows = []
    for image_path in sorted(image_dir.iterdir(), key=lambda item: item.name.lower()):
        if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        mask_path = mask_dir / image_path.name
        image_preview = tif_preview(image_path)
        mask_preview = None
        if mask_path.exists():
            mask_preview = DATA_DIR / "segment" / "preview" / f"{mask_path.stem}_mask_green.png"
            mask_preview.parent.mkdir(parents=True, exist_ok=True)
            true_mask_preview(mask_path, mask_preview)
        rows.append(
            {
                "name": image_path.name,
                "image_url": media_url(image_preview),
                "mask_url": media_url(mask_preview),
                "image_path": str(image_path),
                "mask_path": str(mask_path) if mask_path.exists() else None,
            }
        )
    return rows


def list_rasters() -> list[dict[str, Any]]:
    with connect() as conn:
        return rows_to_dicts(conn.execute("SELECT * FROM raster_layers ORDER BY created_at DESC").fetchall())


def latest_susceptibility_map(prefer_real: bool = False) -> dict[str, Any]:
    with connect() as conn:
        if prefer_real:
            row = row_to_dict(
                conn.execute(
                    """
                    SELECT *
                    FROM susceptibility_maps
                    WHERE raster_path IS NOT NULL
                       OR title LIKE 'ExtraTrees%'
                    ORDER BY raster_path IS NOT NULL DESC, created_at DESC
                    LIMIT 1
                    """
                ).fetchone()
            )
        else:
            row = row_to_dict(
                conn.execute("SELECT * FROM susceptibility_maps ORDER BY created_at DESC LIMIT 1").fetchone()
            )
    if not row:
        return {"status": "empty", "message": "Chua co ban do nhay cam."}
    bbox = json.loads(row["bbox_json"]) if row.get("bbox_json") else None
    return {
        **row,
        "bbox": bbox,
        "overlay_url": media_url(row.get("overlay_path")),
    }


def susceptibility_map_payload(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    overlay_path = row.get("overlay_path")
    if overlay_path and not Path(overlay_path).exists():
        return None
    bbox = json.loads(row["bbox_json"]) if row.get("bbox_json") else None
    return {
        **row,
        "bbox": bbox,
        "overlay_url": media_url(row.get("overlay_path")),
        "raster_url": media_url(row.get("raster_path")),
    }


def list_susceptibility_maps() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT *
                FROM susceptibility_maps
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()
        )
    return [payload for row in rows if (payload := susceptibility_map_payload(row))]


def get_susceptibility_map(map_id: int) -> dict[str, Any]:
    with connect() as conn:
        row = row_to_dict(
            conn.execute("SELECT * FROM susceptibility_maps WHERE id = ?", (map_id,)).fetchone()
        )
    payload = susceptibility_map_payload(row)
    if not payload:
        raise HTTPException(status_code=404, detail="Khong tim thay ban do nhay cam.")
    return payload


def get_stats() -> dict[str, Any]:
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS total FROM inventory").fetchone()["total"]
        new_total = conn.execute("SELECT COUNT(*) AS total FROM inventory WHERE is_new = 1").fetchone()["total"]
        jobs = conn.execute("SELECT COUNT(*) AS total FROM detection_jobs").fetchone()["total"]
        new_jobs = conn.execute("SELECT COUNT(*) AS total FROM detection_jobs WHERE decision = 'new'").fetchone()["total"]
        duplicate_jobs = conn.execute(
            "SELECT COUNT(*) AS total FROM detection_jobs WHERE decision = 'duplicate'"
        ).fetchone()["total"]
        area = conn.execute("SELECT COALESCE(SUM(dien_tich), 0) AS total FROM inventory").fetchone()["total"]
        by_huyen = rows_to_dicts(
            conn.execute(
                """
                SELECT COALESCE(huyen, 'khong_ro') AS huyen, COUNT(*) AS total
                FROM inventory
                GROUP BY huyen
                ORDER BY total DESC
                """
            ).fetchall()
        )
        by_quy_mo = rows_to_dicts(
            conn.execute(
                """
                SELECT COALESCE(NULLIF(quy_mo, ''), 'khong_ro') AS quy_mo, COUNT(*) AS total
                FROM inventory
                GROUP BY quy_mo
                ORDER BY total DESC
                """
            ).fetchall()
        )
        recent = rows_to_dicts(
            conn.execute(
                """
                SELECT *
                FROM inventory
                ORDER BY created_at DESC
                LIMIT 80
                """
            ).fetchall()
        )
    return {
        "inventory_total": total,
        "new_inventory_total": new_total,
        "detection_jobs_total": jobs,
        "new_detection_jobs": new_jobs,
        "duplicate_detection_jobs": duplicate_jobs,
        "area_total_m2": round(float(area or 0), 2),
        "by_huyen": by_huyen,
        "by_quy_mo": by_quy_mo,
        "recent": recent,
    }


def create_report() -> dict[str, Any]:
    stats = get_stats()
    points = list_points()
    report_path = DATA_DIR / "reports" / f"bao_cao_{uuid4().hex[:8]}.txt"
    lines = [
        "BAO CAO KIEM KE SAT LO WEBGIS",
        f"Thoi gian tao: {now_iso()} UTC",
        f"Tong so diem: {stats['inventory_total']}",
        f"Diem moi tu AI: {stats['new_inventory_total']}",
        f"Lan phat hien: {stats['detection_jobs_total']}",
        f"Lan bao diem moi: {stats['new_detection_jobs']}",
        f"Lan trung diem cu: {stats['duplicate_detection_jobs']}",
        f"Tong dien tich uoc tinh: {stats['area_total_m2']} m2",
        "",
        "Thong ke theo huyen:",
    ]
    for item in stats["by_huyen"]:
        lines.append(f"- {item['huyen']}: {item['total']} diem")
    lines.extend(["", "Thong ke theo quy mo:"])
    for item in stats["by_quy_mo"]:
        lines.append(f"- {item['quy_mo']}: {item['total']} diem")
    lines.extend(["", "Danh sach diem gan day:"])
    for point in points[:20]:
        lines.append(
            f"- #{point['id']} {point['huyen']} / {point['xa']} / {point['thon']}: "
            f"{point['dien_tich']} m2, ngay {point['observed_at']}"
        )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return {"report_url": media_url(report_path), "report_path": str(report_path), "stats": stats}
