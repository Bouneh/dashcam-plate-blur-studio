"""Download the original project's model when it is not already present."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from web_processor import MODEL_PATH


# File ID from the upstream project's setup.sh.
MODEL_FILE_ID = "1uV8IMuGDbmDabdjyeSy4SUKV9OS-ULbe"
MODEL_SHA256 = "c941613a63a2e54f1b4f4f1bc7dba3d2b42f905daf4513b3aeaed25b02a72236"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_model(path: Path = MODEL_PATH, file_id: str = MODEL_FILE_ID,
                 expected_sha256: str = MODEL_SHA256) -> Path:
    if path.is_file():
        print(f"Using existing model: {path}", flush=True)
        return path

    try:
        import gdown
    except ImportError as exc:
        raise RuntimeError("Install requirements-model.txt to download the model.") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".download-{uuid.uuid4().hex}.part"
    print("Downloading the upstream YOLO model…", flush=True)
    try:
        downloaded = gdown.download(id=file_id, output=str(temporary), quiet=False)
        if not downloaded or not temporary.is_file():
            raise RuntimeError("The upstream model download failed.")
        if sha256_file(temporary) != expected_sha256:
            raise RuntimeError("The downloaded model did not match the expected SHA-256 checksum.")
        temporary.replace(path)
        print(f"Model ready: {path}", flush=True)
        return path
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    ensure_model()
