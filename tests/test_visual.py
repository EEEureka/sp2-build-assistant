import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

spec = importlib.util.spec_from_file_location("sp2build", Path(__file__).parents[1] / "cli" / "sp2build.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
visual = cli.visual_module()


class VisualContractTests(unittest.TestCase):
    def test_schema_requires_current_session(self):
        self.assertEqual(cli.schema("visual.capture")["required"], ["craftSessionId"])
        self.assertIn("views", cli.schema("visual.capture")["properties"])
        self.assertNotIn("views", cli.schema("visual.resolve")["properties"])

    def test_capture_parses_nested_objects_and_download_option(self):
        args = cli.load_args("visual.capture", {"craft-session-id": "session", "resolution": '{"width":256}', "output-dir": "target"})
        self.assertEqual(args, {"craftSessionId": "session", "resolution": {"width": 256}})

    def test_missing_session_does_not_capture(self):
        with self.assertRaises(cli.CliError):
            cli.load_args("visual.capture", {})

    def test_png_roundtrip_and_exact_ids(self):
        root = Path(__file__).parent / "artifacts" / "visual-unit"
        if not root.exists():
            self.skipTest("run run-unit-tests.ps1 to create renderer fixture")
        for path in root.glob("*.png"):
            blob = path.read_bytes()
            self.assertEqual(blob[:8], b"\x89PNG\r\n\x1a\n")
            position, compressed = 8, b""
            while position < len(blob):
                size = struct.unpack_from(">I", blob, position)[0]
                kind, data = blob[position+4:position+8], blob[position+8:position+8+size]
                self.assertEqual(zlib.crc32(kind + data), struct.unpack_from(">I", blob, position+8+size)[0])
                if kind == b"IHDR":
                    width, height = struct.unpack_from(">II", data)
                if kind == b"IDAT":
                    compressed += data
                position += size + 12
            raw = zlib.decompress(compressed)
            self.assertEqual(len(raw), (width*4+1)*height)
            self.assertTrue(all(raw[y*(width*4+1)] == 0 for y in range(height)))
            if path.name.endswith(".ids.png"):
                rgb = {raw[y*(width*4+1)+1+x*4:y*(width*4+1)+4+x*4] for y in range(height) for x in range(width)}
                self.assertTrue(rgb <= {b"\0\0\0", b"\1\0\0", b"\2\0\0"})

    def artifact(self):
        capture = "a" * 32
        blobs = {"manifest.json": b'{"captureId":"example"}', "overview.png": b"png test fixture"}
        result = cli.ok({"captureId": capture, "artifactBase": f"v1/visual/{capture}/", "recommendedImages": ["overview.png"],
                         "files": [{"name": k, "bytes": len(v), "sha256": hashlib.sha256(v).hexdigest()} for k, v in blobs.items()]})
        return result, blobs

    def test_download_checks_hash_and_returns_absolute_paths(self):
        result, blobs = self.artifact()
        instance = {"baseUrl": "http://127.0.0.1:24730/", "token": "test"}
        with tempfile.TemporaryDirectory() as directory, patch.object(visual, "build_opener") as opener:
            opener.return_value.open.side_effect = lambda req, **kw: io.BytesIO(blobs[req.full_url.rsplit("/", 1)[-1]])
            output = visual.download(instance, result, directory, cli.CliError)
            self.assertEqual(Path(output["data"]["recommendedImages"][0]).read_bytes(), blobs["overview.png"])
            self.assertTrue(Path(output["data"]["manifestPath"]).is_absolute())
            self.assertEqual(opener.return_value.open.call_count, 2)

    def test_bad_hash_is_not_success(self):
        result, _ = self.artifact()
        with tempfile.TemporaryDirectory() as directory, patch.object(visual, "build_opener") as opener:
            opener.return_value.open.return_value = io.BytesIO(b"wrong")
            with self.assertRaises(cli.CliError) as ctx:
                visual.download({"baseUrl": "http://127.0.0.1/", "token": "test"}, result, directory, cli.CliError)
            self.assertEqual(ctx.exception.code, "artifact_integrity")

    def test_traversal_rejected_before_network(self):
        result, _ = self.artifact()
        result["data"]["files"][0]["name"] = "../escape.json"
        with tempfile.TemporaryDirectory() as directory, patch.object(visual, "build_opener") as opener:
            with self.assertRaises(cli.CliError):
                visual.download({}, result, directory, cli.CliError)
            opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
