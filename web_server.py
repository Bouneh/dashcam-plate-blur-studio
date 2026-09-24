"""Local web UI and one-at-a-time background queue for the YOLO video worker."""

from __future__ import annotations

import argparse
import importlib.util
import json
import mimetypes
import os
import queue
import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from web_processor import MODEL_PATH, process_video


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "web"
DATA = Path(os.environ.get("DASHCAM_DATA_DIR", ROOT / "web_data")).resolve()
MAX_UPLOAD = int(os.environ.get("DASHCAM_MAX_UPLOAD_GB", "4")) * 1024**3
EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".wmv", ".flv", ".m4v"}
ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
ERROR_MESSAGES = {
    "not_found": "Job not found.",
    "resource_not_found": "Resource not found.",
    "video_not_ready": "The video is not ready yet.",
    "file_missing": "File not found.",
    "invalid_format": "Unsupported video format.",
    "invalid_params": "Invalid request parameters.",
    "invalid_strength": "Invalid blur strength.",
    "file_size": "The video is empty or too large.",
    "model_missing": "The model is missing from model/best.pt.",
    "ffmpeg_missing": "FFmpeg and FFprobe must be installed.",
    "dependencies_missing": "Install requirements-web.txt in this Python environment.",
    "invalid_video": "This file does not contain a readable video.",
}


class JobStore:
    def __init__(self) -> None:
        self.root = DATA / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, dict] = {}
        self.lock = threading.RLock()
        self.pending: queue.Queue[str] = queue.Queue()
        for path in self.root.glob("*/job.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                if not ID_PATTERN.fullmatch(job.get("id", "")):
                    continue
                if job["status"] in {"queued", "processing"}:
                    job["status"] = "queued"
                    job["stage"] = "queued"
                    job["progress"] = 0
                    self._save(job)
                    self.pending.put(job["id"])
                self.jobs[job["id"]] = job
            except (OSError, ValueError, KeyError):
                continue
        threading.Thread(target=self._work, daemon=True, name="video-worker").start()

    def _save(self, job: dict) -> None:
        path = self.root / job["id"] / "job.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        temp.replace(path)

    def update(self, job_id: str, **fields) -> None:
        with self.lock:
            job = self.jobs[job_id]
            job.update(fields)
            self._save(job)

    def get(self, job_id: str) -> dict | None:
        with self.lock:
            job = self.jobs.get(job_id)
            return dict(job) if job else None

    def list(self) -> list[dict]:
        with self.lock:
            return sorted((dict(job) for job in self.jobs.values()), key=lambda j: j["created_at"], reverse=True)

    def _work(self) -> None:
        while True:
            job_id = self.pending.get()
            try:
                job = self.get(job_id)
                if not job:
                    continue
                self.update(job_id, status="processing", stage="loading_model", progress=2)
                directory = self.root / job_id
                source = directory / job["source_file"]
                destination = directory / "result.mp4"

                def report(frames: int, total: int, regions: int) -> None:
                    progress = min(98, max(3, round(frames / total * 98))) if total > 0 else 3
                    self.update(job_id, stage="processing", progress=progress,
                                frames=frames, regions=regions)

                stats = process_video(source, destination, job["strength"], report)
                self.update(job_id, status="done", stage="done", progress=100, **stats)
            except Exception as exc:
                print(f"[job {job_id}] {exc}", flush=True)
                self.update(job_id, status="error", stage="error", error=str(exc),
                            error_code=getattr(exc, "code", "processing_failed"))
            finally:
                self.pending.task_done()


STORE: JobStore


class Handler(BaseHTTPRequestHandler):
    server_version = "PlaqueStudio/1.0"

    def _json(self, status: HTTPStatus, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, code: str) -> None:
        self._json(status, {"code": code, "error": ERROR_MESSAGES[code]})

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/health":
            self._json(HTTPStatus.OK, {"model_ready": MODEL_PATH.is_file(),
                                       "ffmpeg_ready": shutil.which("ffmpeg") is not None,
                                       "ffprobe_ready": shutil.which("ffprobe") is not None,
                                       "python_ready": all(importlib.util.find_spec(name) is not None
                                                           for name in ("cv2", "torch", "ultralytics"))})
        elif path == "/api/jobs":
            self._json(HTTPStatus.OK, STORE.list())
        elif path.startswith("/api/jobs/"):
            parts = path.split("/")
            if len(parts) < 4 or not ID_PATTERN.fullmatch(parts[3]):
                return self._error(HTTPStatus.NOT_FOUND, "not_found")
            job = STORE.get(parts[3])
            if not job:
                return self._error(HTTPStatus.NOT_FOUND, "not_found")
            if len(parts) == 4:
                return self._json(HTTPStatus.OK, job)
            if len(parts) == 5 and parts[4] in {"source", "video"}:
                if parts[4] == "video" and job["status"] != "done":
                    return self._error(HTTPStatus.CONFLICT, "video_not_ready")
                file = STORE.root / job["id"] / (job["source_file"] if parts[4] == "source" else "result.mp4")
                return self._send_file(file, "video/mp4" if parts[4] == "video" else
                                       mimetypes.guess_type(file.name)[0] or "application/octet-stream",
                                       download=self._query_download())
            self._error(HTTPStatus.NOT_FOUND, "resource_not_found")
        elif path in {"/", "/index.html", "/app.css", "/i18n.css", "/i18n.js", "/app.js", "/favicon.svg"}:
            file = STATIC / ("index.html" if path == "/" else path.lstrip("/"))
            self._send_file(file, mimetypes.guess_type(file.name)[0] or "text/plain")
        else:
            self._error(HTTPStatus.NOT_FOUND, "resource_not_found")

    def _query_download(self) -> bool:
        return parse_qs(urlsplit(self.path).query).get("download") == ["1"]

    def _send_file(self, file: Path, content_type: str, download: bool = False) -> None:
        if not file.is_file():
            return self._error(HTTPStatus.NOT_FOUND, "file_missing")
        size = file.stat().st_size
        start, end = 0, size - 1
        range_header = self.headers.get("Range")
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not match or (not match[1] and not match[2]):
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                return
            if match[1]:
                start = int(match[1])
                end = min(int(match[2]), size - 1) if match[2] else size - 1
            else:
                start = max(0, size - int(match[2]))
            if start > end or start >= size:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
        self.send_response(HTTPStatus.PARTIAL_CONTENT if range_header else HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("X-Content-Type-Options", "nosniff")
        if range_header:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download:
            self.send_header("Content-Disposition", 'attachment; filename="video-floutee.mp4"')
        self.end_headers()
        with file.open("rb") as stream:
            stream.seek(start)
            remaining = end - start + 1
            while remaining:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path != "/api/jobs":
            return self._error(HTTPStatus.NOT_FOUND, "resource_not_found")
        params = parse_qs(parsed.query)
        filename = Path(unquote(params.get("filename", [""])[0]).replace("\\", "/")).name
        suffix = Path(filename).suffix.lower()
        if not filename or suffix not in EXTENSIONS:
            return self._error(HTTPStatus.BAD_REQUEST, "invalid_format")
        try:
            strength = int(params.get("strength", ["2"])[0])
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._error(HTTPStatus.BAD_REQUEST, "invalid_params")
        if strength not in {1, 2, 3}:
            return self._error(HTTPStatus.BAD_REQUEST, "invalid_strength")
        if length <= 0 or length > MAX_UPLOAD:
            return self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "file_size")
        if not MODEL_PATH.is_file():
            return self._error(HTTPStatus.SERVICE_UNAVAILABLE, "model_missing")
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            return self._error(HTTPStatus.SERVICE_UNAVAILABLE, "ffmpeg_missing")
        if not all(importlib.util.find_spec(name) is not None for name in ("cv2", "torch", "ultralytics")):
            return self._error(HTTPStatus.SERVICE_UNAVAILABLE, "dependencies_missing")

        job_id = uuid.uuid4().hex
        directory = STORE.root / job_id
        directory.mkdir()
        source_name = "source" + suffix
        source = directory / source_name
        try:
            remaining = length
            with source.open("wb") as stream:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ConnectionError("Envoi interrompu.")
                    stream.write(chunk)
                    remaining -= len(chunk)
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=codec_type", "-of", "default=nw=1", str(source)],
                capture_output=True, text=True, timeout=20,
            )
            if probe.returncode != 0 or "codec_type=video" not in probe.stdout:
                raise ValueError("Ce fichier ne contient pas de vidéo lisible.")
        except (OSError, ValueError, ConnectionError, subprocess.TimeoutExpired):
            shutil.rmtree(directory, ignore_errors=True)
            return self._error(HTTPStatus.BAD_REQUEST, "invalid_video")

        job = {"id": job_id, "filename": filename, "source_file": source_name,
               "size": length, "strength": strength, "status": "queued",
               "stage": "queued", "progress": 0, "regions": 0, "frames": 0,
               "created_at": datetime.now(timezone.utc).isoformat(), "error": None,
               "error_code": None}
        with STORE.lock:
            STORE.jobs[job_id] = job
            STORE._save(job)
        STORE.pending.put(job_id)
        self._json(HTTPStatus.CREATED, job)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local license plate anonymization web app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    global STORE
    STORE = JobStore()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Plaque Studio : http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
