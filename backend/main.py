from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import DATA_DIR, ensure_data_dirs, settings
from backend.boundary import boundary_geojson
from backend.districts import districts_geojson
from backend.database import connect, init_db
from backend.workflow import (
    create_report,
    create_susceptibility_map,
    get_susceptibility_map,
    get_stats,
    latest_susceptibility_map,
    list_detections,
    list_points,
    list_rasters,
    list_segment_samples,
    list_susceptibility_maps,
    list_uploads,
    register_raster,
    run_detection,
    run_existing_upload,
    run_segment_sample,
)


app = FastAPI(title="Landslide WebGIS Demo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


ensure_data_dirs()
app.mount("/media", StaticFiles(directory=str(DATA_DIR)), name="media")


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok", "database": str(settings.database_path)}


@app.get("/api/settings")
def read_settings() -> dict:
    with connect() as conn:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    values = {row["key"]: row["value"] for row in rows}
    return {
        "predict_image_url": settings.predict_image_url,
        "pixel_size_m": settings.pixel_size_m,
        "duplicate_distance_m": settings.duplicate_distance_m,
        "force_duplicate": values.get("force_duplicate", "false") == "true",
        "tile_provider": values.get("tile_provider", "esri"),
        "custom_tile_url": values.get("custom_tile_url", ""),
    }


@app.post("/api/settings")
def save_settings(
    force_duplicate: bool = Form(False),
    tile_provider: str = Form("esri"),
    custom_tile_url: str = Form(""),
) -> dict:
    with connect() as conn:
        values = {
            "force_duplicate": "true" if force_duplicate else "false",
            "tile_provider": tile_provider,
            "custom_tile_url": custom_tile_url,
        }
        for key, value in values.items():
            conn.execute(
                """
                INSERT INTO app_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
        conn.commit()
    return read_settings()


@app.post("/api/workflows/detect")
async def detect_workflow(
    file: UploadFile = File(...),
    force_duplicate: bool = Form(False),
    update_susceptibility: bool = Form(True),
) -> dict:
    return await run_detection(
        file=file,
        force_duplicate=force_duplicate,
        update_susceptibility=update_susceptibility,
    )


@app.post("/api/workflows/detect-existing")
async def detect_existing_workflow(
    relative_path: str = Form(...),
    force_duplicate: bool = Form(False),
    update_susceptibility: bool = Form(True),
) -> dict:
    return await run_existing_upload(
        relative_path=relative_path,
        force_duplicate=force_duplicate,
        update_susceptibility=update_susceptibility,
    )


@app.post("/api/workflows/detect-segment-sample")
async def detect_segment_sample_workflow(
    sample_name: str = Form(...),
    force_duplicate: bool = Form(False),
    update_susceptibility: bool = Form(True),
) -> dict:
    return await run_segment_sample(
        sample_name=sample_name,
        force_duplicate=force_duplicate,
        update_susceptibility=update_susceptibility,
    )


@app.get("/api/uploads")
def uploads() -> list[dict]:
    return list_uploads()


@app.get("/api/segment-samples")
def segment_samples() -> list[dict]:
    return list_segment_samples()


@app.post("/api/rasters")
async def upload_raster_layer(
    file: UploadFile = File(...),
    name: str = Form(...),
    factor_type: str = Form(...),
) -> dict:
    return await register_raster(file=file, name=name, factor_type=factor_type)


@app.get("/api/points")
def points() -> list[dict]:
    return list_points()


@app.get("/api/boundary")
def boundary() -> dict:
    return boundary_geojson()


@app.get("/api/boundary/huyen")
def district_boundary() -> dict:
    return districts_geojson()


@app.get("/api/detections")
def detections() -> list[dict]:
    return list_detections()


@app.get("/api/rasters")
def rasters() -> list[dict]:
    return list_rasters()


@app.get("/api/stats")
def stats() -> dict:
    return get_stats()


@app.post("/api/reports")
def report() -> dict:
    return create_report()


@app.post("/api/susceptibility/maps")
def create_map(force_new: bool = Form(True)) -> dict:
    return create_susceptibility_map(force_new=force_new)


@app.get("/api/susceptibility/maps")
def susceptibility_maps() -> list[dict]:
    return list_susceptibility_maps()


@app.get("/api/susceptibility/maps/latest")
def latest_map() -> dict:
    return latest_susceptibility_map(prefer_real=True)


@app.get("/api/susceptibility/maps/{map_id}")
def susceptibility_map(map_id: int) -> dict:
    return get_susceptibility_map(map_id)
