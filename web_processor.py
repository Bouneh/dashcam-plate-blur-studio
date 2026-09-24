"""Single-video plate anonymization, independent from the legacy batch script."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Callable


MODEL_PATH = Path(os.environ.get("DASHCAM_MODEL_PATH", Path(__file__).parent / "model" / "best.pt"))


class ProcessingError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _plate_class_ids(names: dict | list) -> set[int]:
    items = names.items() if isinstance(names, dict) else enumerate(names)
    matches = {
        int(class_id)
        for class_id, name in items
        if any(word in str(name).lower() for word in ("plate", "plaque", "license", "licence"))
    }
    if not matches:
        raise ProcessingError(
            "model_incompatible", "The model has no license plate class. Check model/best.pt."
        )
    return matches


def _blur_plate(frame, box, strength: int, cv2) -> None:
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = (int(round(value)) for value in box)
    x1, x2 = max(0, x1), min(width, x2)
    y1, y2 = max(0, y1), min(height, y2)
    if x2 <= x1 or y2 <= y1:
        return

    # Downsampling first makes even small plates unreadable; Gaussian smoothing
    # hides the mosaic blocks while keeping the requested blur appearance.
    region = frame[y1:y2, x1:x2]
    divisor = 10 + 8 * strength
    small = cv2.resize(
        region,
        (max(1, (x2 - x1) // divisor), max(1, (y2 - y1) // divisor)),
        interpolation=cv2.INTER_AREA,
    )
    enlarged = cv2.resize(small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_LINEAR)
    kernel = 15 + 10 * strength
    frame[y1:y2, x1:x2] = cv2.GaussianBlur(enlarged, (kernel, kernel), 0)


def process_video(
    source: Path,
    destination: Path,
    strength: int,
    report: Callable[[int, int, int], None],
) -> dict:
    """Stream detections into ffmpeg and report (frames, estimated total, regions)."""
    try:
        import cv2
        import torch
        from ultralytics import YOLO
    except ImportError as exc:
        raise ProcessingError(
            "dependencies_missing", "Video dependencies are missing. Install requirements-web.txt."
        ) from exc

    if not MODEL_PATH.is_file():
        raise ProcessingError("model_missing", f"Model not found: {MODEL_PATH}")

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise ProcessingError("invalid_video", "Could not read this video.")
    try:
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:
        capture.release()
    if width < 1 or height < 1 or fps <= 0:
        raise ProcessingError("invalid_video", "Invalid video dimensions or frame rate.")

    model = YOLO(str(MODEL_PATH))
    plate_classes = _plate_class_ids(model.names)
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.stem + ".partial.mp4")
    log_path = destination.with_suffix(".ffmpeg.log")
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
        "-r", str(fps), "-i", "pipe:0", "-i", str(source),
        "-map", "0:v:0", "-map", "1:a?", "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-shortest",
        "-movflags", "+faststart", str(temporary),
    ]
    frames = 0
    regions = 0
    last_report = 0.0
    with log_path.open("wb") as log:
        encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=log)
        try:
            for result in model.predict(
                source=str(source), stream=True, conf=0.20,
                device=device, verbose=False,
            ):
                frame = result.orig_img
                for box, class_id in zip(result.boxes.xyxy.cpu().tolist(), result.boxes.cls.cpu().tolist()):
                    if int(class_id) in plate_classes:
                        _blur_plate(frame, box, strength, cv2)
                        regions += 1
                if frame.shape[1] != width or frame.shape[0] != height:
                    raise ProcessingError("invalid_video", "Video resolution changed during processing.")
                assert encoder.stdin is not None
                encoder.stdin.write(frame.tobytes())
                frames += 1
                now = time.monotonic()
                if now - last_report >= 0.5:
                    report(frames, total, regions)
                    last_report = now
            assert encoder.stdin is not None
            encoder.stdin.close()
            if encoder.wait() != 0:
                raise ProcessingError("encoding_failed", "Video encoding failed. Check the job FFmpeg log.")
        except Exception:
            if encoder.stdin and not encoder.stdin.closed:
                encoder.stdin.close()
            if encoder.poll() is None:
                encoder.kill()
            encoder.wait()
            temporary.unlink(missing_ok=True)
            raise

    if frames == 0 or not temporary.is_file() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        raise ProcessingError("invalid_video", "No video frames were processed.")
    temporary.replace(destination)
    log_path.unlink(missing_ok=True)
    report(frames, total, regions)
    return {"frames": frames, "regions": regions, "duration": round(frames / fps, 1)}
