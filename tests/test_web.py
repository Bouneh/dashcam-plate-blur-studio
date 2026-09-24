"""Focused integration checks for upload, queue, playback and class filtering."""

from __future__ import annotations

import http.client
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import web_processor
import web_server
import model_setup


class WebTests(unittest.TestCase):
    def test_model_download_verifies_hash_and_cleans_failed_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = b"test-model"

            def download(*, id, output, quiet):
                self.assertEqual(id, "sample-id")
                Path(output).write_bytes(payload)
                return output

            with patch.dict(sys.modules, {"gdown": types.SimpleNamespace(download=download)}):
                target = root / "model" / "best.pt"
                result = model_setup.ensure_model(
                    target, "sample-id", hashlib.sha256(payload).hexdigest()
                )
                self.assertEqual(result.read_bytes(), payload)
                self.assertEqual(list(target.parent.glob("*.part")), [])
                bad_target = root / "other" / "best.pt"
                with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                    model_setup.ensure_model(bad_target, "sample-id", "0" * 64)
                self.assertFalse(bad_target.exists())
                self.assertEqual(list(bad_target.parent.glob("*.part")), [])

    def test_plate_classes_exclude_faces(self):
        self.assertEqual(web_processor._plate_class_ids({0: "license", 1: "face"}), {0})
        self.assertEqual(web_processor._plate_class_ids({0: "license plate", 1: "face"}), {0})
        with self.assertRaises(RuntimeError):
            web_processor._plate_class_ids({0: "face"})

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_upload_queue_and_video_range(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sample = root / "sample.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                "color=c=blue:s=160x90:d=1", "-c:v", "mpeg4", str(sample),
            ], check=True)
            original_data = sample.read_bytes()

            def fake_process(source, destination, strength, report):
                self.assertEqual(strength, 2)
                shutil.copyfile(source, destination)
                report(25, 25, 2)
                return {"frames": 25, "regions": 2, "duration": 1.0}

            with patch.object(web_server, "DATA", root), \
                 patch.object(web_server, "MODEL_PATH", sample), \
                 patch.object(web_server, "process_video", fake_process), \
                 patch.object(web_server.importlib.util, "find_spec", return_value=object()):
                web_server.STORE = web_server.JobStore()
                server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
                    connection.request("POST", "/api/jobs?filename=sample.mp4&strength=2",
                                       body=original_data,
                                       headers={"Content-Type": "application/octet-stream"})
                    response = connection.getresponse()
                    self.assertEqual(response.status, 201)
                    job = json.loads(response.read())
                    for _ in range(50):
                        connection.request("GET", f"/api/jobs/{job['id']}")
                        status = json.loads(connection.getresponse().read())
                        if status["status"] == "done":
                            break
                        time.sleep(.05)
                    self.assertEqual(status["status"], "done")
                    self.assertEqual(status["regions"], 2)
                    connection.request("GET", f"/api/jobs/{job['id']}/video",
                                       headers={"Range": "bytes=0-15"})
                    playback = connection.getresponse()
                    self.assertEqual(playback.status, 206)
                    self.assertEqual(playback.getheader("Content-Range"), f"bytes 0-15/{len(original_data)}")
                    self.assertEqual(playback.read(), original_data[:16])
                    connection.close()
                finally:
                    server.shutdown()
                    server.server_close()


if __name__ == "__main__":
    unittest.main()
