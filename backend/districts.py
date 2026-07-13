import sqlite3
import struct
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.config import DATA_DIR, settings
from backend.database import read_csv_points


def normalize_name(value: str) -> str:
    value = (value or "").replace("Đ", "D").replace("đ", "d")
    text = unicodedata.normalize("NFD", value or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return "_".join(text.lower().replace("-", " ").split())


def display_name(raw: str, name_map: dict[str, str]) -> str:
    key = normalize_name(raw.replace("_", " "))
    manual = {
        "trieu_phong": "Triệu Phong",
        "quang_tri": "Thị xã Quảng Trị",
        "dong_ha": "Đông Hà",
        "gio_linh": "Gio Linh",
        "hai_lang": "Hải Lăng",
        "cam_lo": "Cam Lộ",
        "huong_hoa": "Hướng Hóa",
        "dakrong": "Đakrông",
        "vinh_linh": "Vĩnh Linh",
    }
    if key in manual:
        return manual[key]
    return name_map.get(key, " ".join(part.capitalize() for part in raw.split("_")))


def csv_district_name_map() -> dict[str, str]:
    names: dict[str, str] = {}
    for row in read_csv_points():
        huyen = row.get("huyen") or ""
        if huyen:
            names[normalize_name(huyen)] = huyen
    return names


def gpkg_header_size(blob: bytes) -> int:
    if blob[:2] != b"GP":
        return 0
    flags = blob[3]
    envelope_code = (flags >> 1) & 0b111
    envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    return 8 + envelope_sizes.get(envelope_code, 0)


def parse_wkb_geometry(wkb: bytes) -> list[list[list[tuple[float, float]]]]:
    byte_order = "<" if wkb[0] == 1 else ">"
    geom_type = struct.unpack(f"{byte_order}I", wkb[1:5])[0]
    offset = 5

    if geom_type == 3:
        polygon, _offset = parse_wkb_polygon(wkb, offset, byte_order)
        return [[polygon]]

    if geom_type == 6:
        polygon_count = struct.unpack(f"{byte_order}I", wkb[offset : offset + 4])[0]
        offset += 4
        polygons = []
        for _ in range(polygon_count):
            child_order = "<" if wkb[offset] == 1 else ">"
            child_type = struct.unpack(f"{child_order}I", wkb[offset + 1 : offset + 5])[0]
            offset += 5
            if child_type != 3:
                break
            polygon, offset = parse_wkb_polygon(wkb, offset, child_order)
            polygons.append(polygon)
        return [polygons]

    return []


def parse_wkb_polygon(wkb: bytes, offset: int, byte_order: str) -> tuple[list[list[tuple[float, float]]], int]:
    ring_count = struct.unpack(f"{byte_order}I", wkb[offset : offset + 4])[0]
    offset += 4
    rings = []
    for _ in range(ring_count):
        point_count = struct.unpack(f"{byte_order}I", wkb[offset : offset + 4])[0]
        offset += 4
        ring = []
        for _ in range(point_count):
            x, y = struct.unpack(f"{byte_order}2d", wkb[offset : offset + 16])
            offset += 16
            ring.append((x, y))
        rings.append(ring)
    return rings, offset


def transform_rings_to_wgs84(rings: list[list[tuple[float, float]]], src_crs: int) -> list[list[tuple[float, float]]]:
    if src_crs == 4326:
        return rings

    from rasterio.warp import transform

    transformed = []
    for ring in rings:
        xs = [point[0] for point in ring]
        ys = [point[1] for point in ring]
        lons, lats = transform(f"EPSG:{src_crs}", "EPSG:4326", xs, ys)
        transformed.append(list(zip(lons, lats)))
    return transformed


def point_in_ring(lon: float, lat: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i, point in enumerate(ring):
        xi, yi = point
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def point_in_polygon(lon: float, lat: float, rings: list[list[tuple[float, float]]]) -> bool:
    if not rings or not point_in_ring(lon, lat, rings[0]):
        return False
    for hole in rings[1:]:
        if point_in_ring(lon, lat, hole):
            return False
    return True


@lru_cache(maxsize=1)
def load_districts() -> list[dict[str, Any]]:
    gpkg_path = DATA_DIR / "boundary" / "huyen" / "huyen_boundary.gpkg"
    if not gpkg_path.exists():
        return []

    name_map = csv_district_name_map()
    conn = sqlite3.connect(gpkg_path)
    try:
        row = conn.execute(
            "SELECT table_name, srs_id FROM gpkg_contents WHERE data_type = 'features' LIMIT 1"
        ).fetchone()
        if not row:
            return []
        table_name, srs_id = row
        geom_col = conn.execute(
            "SELECT column_name FROM gpkg_geometry_columns WHERE table_name = ? LIMIT 1",
            (table_name,),
        ).fetchone()[0]
        rows = conn.execute(f"SELECT {geom_col}, name FROM {table_name}").fetchall()
    finally:
        conn.close()

    districts = []
    for geom_blob, raw_name in rows:
        header_size = gpkg_header_size(geom_blob)
        multipolygon = parse_wkb_geometry(geom_blob[header_size:])
        polygons = []
        for polygon_group in multipolygon:
            for rings in polygon_group:
                polygons.append(transform_rings_to_wgs84(rings, int(srs_id)))
        districts.append(
            {
                "raw_name": raw_name,
                "name": display_name(raw_name, name_map),
                "polygons": polygons,
            }
        )
    return districts


def district_for_point(lon: float, lat: float) -> str:
    for district in load_districts():
        for polygon in district["polygons"]:
            if point_in_polygon(lon, lat, polygon):
                return district["name"]
    return ""


def districts_geojson() -> dict[str, Any]:
    features = []
    for district in load_districts():
        coordinates = []
        for polygon in district["polygons"]:
            coordinates.append([[[float(x), float(y)] for x, y in ring] for ring in polygon])
        if not coordinates:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {"name": district["name"]},
                "geometry": {"type": "MultiPolygon", "coordinates": coordinates},
            }
        )
    return {"type": "FeatureCollection", "features": features}
