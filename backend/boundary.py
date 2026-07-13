import struct
from pathlib import Path
from typing import Any

from backend.config import DATA_DIR


def boundary_geojson() -> dict[str, Any]:
    shp_path = DATA_DIR / "boundary" / "quangtri_boundary.shp"
    if not shp_path.exists():
        return {"type": "FeatureCollection", "features": []}

    data = shp_path.read_bytes()
    features = []
    offset = 100
    while offset + 8 <= len(data):
        _record_number, content_words = struct.unpack(">2i", data[offset : offset + 8])
        offset += 8
        content_size = content_words * 2
        content = data[offset : offset + content_size]
        offset += content_size
        if len(content) < 44:
            continue

        shape_type = struct.unpack("<i", content[:4])[0]
        if shape_type not in (5, 15, 25, 31):
            continue

        min_x, min_y, max_x, max_y = struct.unpack("<4d", content[4:36])
        num_parts, num_points = struct.unpack("<2i", content[36:44])
        parts_start = 44
        points_start = parts_start + num_parts * 4
        if len(content) < points_start + num_points * 16:
            continue

        parts = list(struct.unpack(f"<{num_parts}i", content[parts_start:points_start]))
        points = [
            struct.unpack("<2d", content[points_start + idx * 16 : points_start + (idx + 1) * 16])
            for idx in range(num_points)
        ]

        rings = []
        for part_index, start in enumerate(parts):
            end = parts[part_index + 1] if part_index + 1 < len(parts) else num_points
            ring = [[float(x), float(y)] for x, y in points[start:end]]
            if ring and ring[0] != ring[-1]:
                ring.append(ring[0])
            if len(ring) >= 4:
                rings.append(ring)

        if not rings:
            continue

        geometry = {"type": "Polygon", "coordinates": rings}
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": "Vung nghien cuu Quang Tri",
                    "bbox": [min_x, min_y, max_x, max_y],
                },
                "geometry": geometry,
            }
        )

    return {"type": "FeatureCollection", "features": features}
