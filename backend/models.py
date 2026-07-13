import base64
import io
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from PIL import Image, ImageDraw

from backend.config import settings


def preprocess_image_512(image_path: Path, output_path: Path) -> Path:
    image = Image.open(image_path).convert("RGB")
    image = image.resize((512, 512), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (512, 512), (0, 0, 0))
    canvas.paste(image, (0, 0))
    canvas.save(output_path, format="JPEG", quality=92)
    return output_path


async def predict_image_remote(image_path: Path) -> dict[str, Any]:
    if "YOUR_CLOUD_RUN_URL" in settings.predict_image_url:
        return mock_prediction(image_path, "mock_placeholder_url")

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            with image_path.open("rb") as f:
                response = await client.post(
                    settings.predict_image_url,
                    files={"file": (image_path.name, f, "image/jpeg")},
                )
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = response.json()
            payload.setdefault("status", "remote_ok")
            return payload

        if "image/" in content_type:
            return {
                "status": "remote_ok",
                "overlay_b64": base64.b64encode(response.content).decode("utf-8"),
            }

        return {"status": "remote_ok", "raw": response.text[:1000]}
    except Exception as exc:
        payload = mock_prediction(image_path, "mock_remote_failed")
        payload["remote_error"] = str(exc)
        return payload


async def predict_video_remote(video_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    if "YOUR_CLOUD_RUN_URL" in settings.predict_video_url:
        payload = mock_video_prediction(video_path, "mock_placeholder_url")
        enrich_video_metrics(payload, started)
        return payload

    try:
        form_data = {
            "threshold": str(settings.predict_video_threshold),
            "frame_stride": str(settings.predict_video_frame_stride),
        }
        total_frames = video_total_frames(video_path)
        if total_frames:
            form_data["max_frames"] = str(total_frames)

        async with httpx.AsyncClient(timeout=settings.predict_video_timeout_seconds) as client:
            with video_path.open("rb") as f:
                response = await client.post(
                    settings.predict_video_url,
                    params=form_data,
                    files={"file": (video_path.name, f, "video/mp4")},
                    data=form_data,
                )
        response.raise_for_status()
        payload = response.json()
        payload.setdefault("status", "remote_ok")
        enrich_video_metrics(payload, started)
        return payload
    except Exception as exc:
        payload = mock_video_prediction(video_path, "mock_remote_failed")
        payload["remote_error"] = str(exc)
        enrich_video_metrics(payload, started)
        return payload


def enrich_video_metrics(payload: dict[str, Any], started: float) -> None:
    latency = max(time.perf_counter() - started, 0.001)
    payload["request_latency_seconds"] = round(latency, 3)

    processed_frames = float(payload.get("processed_frames") or 0)
    inference_time = float(payload.get("inference_time_seconds") or 0)
    payload["effective_fps"] = round(processed_frames / inference_time, 2) if inference_time > 0 else 0
    payload["wall_fps"] = round(processed_frames / latency, 2) if latency > 0 else 0


def mock_video_prediction(video_path: Path, status: str) -> dict[str, Any]:
    return {
        "status": status,
        "class_name": "landslide",
        "threshold": settings.predict_video_threshold,
        "video_width": 0,
        "video_height": 0,
        "source_fps": 0,
        "output_fps": 0,
        "source_total_frames": 0,
        "processed_frames": 0,
        "frame_stride": settings.predict_video_frame_stride,
        "max_frames": None,
        "total_landslide_area_pixels": 0,
        "average_landslide_area_ratio": 0,
        "max_probability": 0,
        "inference_time_seconds": 0,
        "frames": [],
    }


def write_overlay_video_from_prediction(
    video_path: Path,
    prediction: dict[str, Any],
    output_path: Path,
) -> Path:
    encoded = prediction.get("overlay_video_base64")
    if encoded:
        output_path.write_bytes(base64.b64decode(encoded))
        return output_path

    # Fallback: keep the original video available when the remote call failed.
    output_path.write_bytes(video_path.read_bytes())
    return output_path


def video_total_frames(video_path: Path) -> int | None:
    try:
        import cv2
    except ImportError:
        return None

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return None
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    capture.release()
    return total_frames if total_frames > 0 else None


def video_to_gif_preview(
    video_path: Path,
    output_path: Path,
    metrics: dict[str, Any] | None = None,
) -> Path | None:
    try:
        import cv2
    except ImportError:
        return None

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return None

    source_fps = capture.get(cv2.CAP_PROP_FPS) or 15
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    target_fps = 6
    max_gif_frames = 90
    stride = max(1, int(source_fps / target_fps))
    if total_frames > max_gif_frames * stride:
        stride = max(stride, total_frames // max_gif_frames)

    frames: list[Image.Image] = []
    frame_index = 0
    max_width = 960
    while len(frames) < max_gif_frames:
        ok, frame = capture.read()
        if not ok:
            break
        if frame_index % stride == 0:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(frame)
            if image.width > max_width:
                ratio = max_width / image.width
                image = image.resize((max_width, max(2, int(image.height * ratio))), Image.Resampling.LANCZOS)
            frames.append(image.convert("P", palette=Image.Palette.ADAPTIVE))
        frame_index += 1

    capture.release()
    if not frames:
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration_ms = max(80, int(1000 / target_fps))
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        optimize=True,
        duration=duration_ms,
        loop=0,
    )
    return output_path


def video_to_webm_preview(video_path: Path, output_path: Path) -> Path | None:
    try:
        import cv2
    except ImportError:
        return None

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return None

    source_fps = capture.get(cv2.CAP_PROP_FPS) or 15
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if width <= 0 or height <= 0:
        capture.release()
        return None

    max_width = 960
    if width > max_width:
        ratio = max_width / width
        width = max_width
        height = max(2, int(height * ratio))

    # VP8/WebM is broadly playable in modern browsers and avoids MP4 codec issues.
    width = width if width % 2 == 0 else width - 1
    height = height if height % 2 == 0 else height - 1
    fps = max(1, min(float(source_fps), 24.0))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"VP80"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        capture.release()
        return None

    wrote = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if frame.shape[1] != width or frame.shape[0] != height:
            frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        writer.write(frame)
        wrote += 1

    capture.release()
    writer.release()
    if wrote == 0 or not output_path.exists() or output_path.stat().st_size == 0:
        return None
    return output_path


def ffmpeg_executable() -> str | None:
    configured = os.getenv("FFMPEG_BINARY")
    if configured and Path(configured).exists():
        return configured

    found = shutil.which("ffmpeg")
    if found:
        return found

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def video_to_browser_preview(video_path: Path, output_stem: Path) -> tuple[Path | None, str | None, str]:
    output_stem.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = ffmpeg_executable()
    if ffmpeg:
        mp4_path = output_stem.with_suffix(".mp4")
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-vf",
            "scale='min(1280,iw)':-2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            str(mp4_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=300)
            if mp4_path.exists() and mp4_path.stat().st_size > 0:
                return mp4_path, "video/mp4", "ffmpeg_h264"
        except Exception:
            pass

    webm_path = output_stem.with_suffix(".webm")
    preview_path = video_to_webm_preview(video_path, webm_path)
    if preview_path:
        return preview_path, "video/webm", "opencv_vp8"
    return None, None, "unavailable"


def mock_prediction(image_path: Path, status: str) -> dict[str, Any]:
    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    box_w = max(int(width * 0.22), 40)
    box_h = max(int(height * 0.16), 40)
    x1 = max(int(width * 0.50 - box_w / 2), 0)
    y1 = max(int(height * 0.52 - box_h / 2), 0)
    x2 = min(x1 + box_w, width - 1)
    y2 = min(y1 + box_h, height - 1)

    area_m2 = box_w * box_h * settings.pixel_size_m * settings.pixel_size_m
    return {
        "status": status,
        "confidence": 0.86,
        "bbox_px": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        "width_m": round(box_w * settings.pixel_size_m, 2),
        "height_m": round(box_h * settings.pixel_size_m, 2),
        "area_m2": round(area_m2, 2),
    }


def draw_prediction_overlay(image_path: Path, prediction: dict[str, Any], output_path: Path) -> None:
    image = Image.open(image_path).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    bbox = prediction.get("bbox_px") or {}
    x1 = int(bbox.get("x1", image.width * 0.4))
    y1 = int(bbox.get("y1", image.height * 0.4))
    x2 = int(bbox.get("x2", image.width * 0.6))
    y2 = int(bbox.get("y2", image.height * 0.6))
    draw.rectangle([x1, y1, x2, y2], fill=(220, 38, 38, 96), outline=(185, 28, 28, 255), width=4)
    draw.text((x1 + 8, max(y1 - 24, 8)), "Landslide", fill=(185, 28, 28, 255))
    Image.alpha_composite(image, overlay).convert("RGB").save(output_path)


def mask_from_prediction(prediction: dict[str, Any], size: tuple[int, int]) -> Image.Image:
    width, height = size
    for key in ("mask_b64", "mask_base64", "pred_mask_b64", "overlay_b64"):
        if prediction.get(key):
            try:
                raw = base64.b64decode(prediction[key])
                return Image.open(io.BytesIO(raw)).convert("L").resize(size, Image.Resampling.NEAREST)
            except Exception:
                pass

    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    bbox = prediction.get("bbox_px") or {}
    x1 = int(bbox.get("x1", width * 0.4))
    y1 = int(bbox.get("y1", height * 0.4))
    x2 = int(bbox.get("x2", width * 0.6))
    y2 = int(bbox.get("y2", height * 0.6))
    draw.rectangle([x1, y1, x2, y2], fill=255)
    return mask


def normalize_binary_mask(mask_path: Path, size: tuple[int, int]) -> Image.Image:
    mask = Image.open(mask_path).convert("L").resize(size, Image.Resampling.NEAREST)
    arr = np.asarray(mask)
    threshold = 0 if arr.max() <= 1 else 127
    return Image.fromarray(np.where(arr > threshold, 255, 0).astype(np.uint8), mode="L")


def create_mask_comparison_overlay(
    image_path: Path,
    true_mask_path: Path | None,
    prediction: dict[str, Any],
    output_path: Path,
) -> Path:
    base = Image.open(image_path).convert("RGBA").resize((512, 512), Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))

    if true_mask_path and true_mask_path.exists():
        true_mask = normalize_binary_mask(true_mask_path, base.size)
        green = Image.new("RGBA", base.size, (34, 197, 94, 110))
        overlay = Image.composite(green, overlay, true_mask)

    pred_mask = mask_from_prediction(prediction, base.size)
    red = Image.new("RGBA", base.size, (239, 68, 68, 145))
    overlay = Image.alpha_composite(overlay, Image.composite(red, Image.new("RGBA", base.size, (0, 0, 0, 0)), pred_mask))

    result = Image.alpha_composite(base, overlay).convert("RGB")
    result.save(output_path, quality=92)
    return output_path


def true_mask_preview(mask_path: Path, output_path: Path) -> Path:
    mask = normalize_binary_mask(mask_path, (512, 512))
    rgba = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    green = Image.new("RGBA", (512, 512), (34, 197, 94, 170))
    Image.composite(green, rgba, mask).save(output_path)
    return output_path


def susceptibility_overlay_png(points: list[dict[str, Any]], output_path: Path) -> dict[str, float]:
    # Demo raster-like heatmap over Quang Tri bounds. Replace with ExtraTrees/raster stack later.
    west, south, east, north = 106.55, 16.30, 107.45, 17.15
    width, height = 900, 700
    grid_y, grid_x = np.mgrid[0:height, 0:width]
    heat = np.zeros((height, width), dtype=np.float32)

    for point in points:
        px = int((point["lon"] - west) / (east - west) * width)
        py = int((north - point["lat"]) / (north - south) * height)
        distance = (grid_x - px) ** 2 + (grid_y - py) ** 2
        heat += np.exp(-distance / (2 * 58**2))

    if heat.max() > 0:
        heat = heat / heat.max()

    classes = np.clip(np.floor(heat * 5), 0, 4).astype(np.uint8)
    colors = np.array(
        [
            [37, 99, 235, 45],
            [14, 165, 233, 80],
            [34, 197, 94, 120],
            [245, 158, 11, 155],
            [220, 38, 38, 190],
        ],
        dtype=np.uint8,
    )
    rgba = colors[classes]
    rgba[..., 3] = np.where(heat > 0.02, rgba[..., 3], 0)
    Image.fromarray(rgba).save(output_path)
    return {"west": west, "south": south, "east": east, "north": north}
