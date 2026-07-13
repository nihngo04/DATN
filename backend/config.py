import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
ENV_PATH = BASE_DIR / "backend" / ".env"
ENV_EXAMPLE_PATH = BASE_DIR / "backend" / ".env.example"

try:
    from dotenv import load_dotenv

    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
    else:
        load_dotenv(ENV_EXAMPLE_PATH)
except ImportError:
    pass


def default_csv_path() -> Path:
    configured = os.getenv("CSV_PATH")
    if configured:
        return Path(configured)
    real_csv = BASE_DIR / "quangtri_diemsatlo.csv"
    if real_csv.exists():
        return real_csv
    return BASE_DIR / "data.csv"


def default_new_csv_path() -> Path:
    configured = os.getenv("CSV_NEW_PATH")
    if configured:
        return Path(configured)
    return DATA_DIR / "inventory_new" / "quangtri_landslide_new.csv"


def default_image_metadata_path() -> Path:
    configured = os.getenv("IMAGE_METADATA_PATH")
    if configured:
        return Path(configured)
    return DATA_DIR / "metadata" / "quangtri_metadata.csv"


class Settings:
    csv_path = default_csv_path()
    csv_new_path = default_new_csv_path()
    image_metadata_path = default_image_metadata_path()
    database_path = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "webgis.sqlite3")))
    predict_image_url = os.getenv(
        "PREDICT_IMAGE_URL",
        "https://YOUR_CLOUD_RUN_URL/predict-image",
    )
    predict_video_url = os.getenv(
        "PREDICT_VIDEO_URL",
        predict_image_url.replace("/predict-image", "/predict-video"),
    )
    predict_video_timeout_seconds = float(os.getenv("PREDICT_VIDEO_TIMEOUT_SECONDS", "900"))
    predict_video_max_frames = int(os.getenv("PREDICT_VIDEO_MAX_FRAMES", "300"))
    predict_video_frame_stride = int(os.getenv("PREDICT_VIDEO_FRAME_STRIDE", "1"))
    predict_video_threshold = float(os.getenv("PREDICT_VIDEO_THRESHOLD", "0.3"))
    pixel_size_m = float(os.getenv("PIXEL_SIZE_M", "4.7"))
    duplicate_distance_m = float(os.getenv("DUPLICATE_DISTANCE_M", "150"))
    new_point_shift_km_min = float(os.getenv("NEW_POINT_SHIFT_KM_MIN", "2.0"))
    new_point_shift_km_max = float(os.getenv("NEW_POINT_SHIFT_KM_MAX", "5.0"))
    quang_tri_center_lat = float(os.getenv("QUANG_TRI_CENTER_LAT", "16.75"))
    quang_tri_center_lon = float(os.getenv("QUANG_TRI_CENTER_LON", "107.08"))


settings = Settings()


def ensure_data_dirs() -> None:
    for dirname in [
        "uploads/video",
        "uploads/image",
        "output/video",
        "output/image",
        "model/segmen",
        "model/extratrees",
        "raster/do_cao",
        "raster/do_doc",
        "raster/huong_suon",
        "raster/luong_mua",
        "raster/thach_hoc",
        "raster/lop_phu",
        "raster/khoang_cach_duong",
        "raster/khoang_cach_song",
        "susceptibility",
        "reports",
    ]:
        (DATA_DIR / dirname).mkdir(parents=True, exist_ok=True)
