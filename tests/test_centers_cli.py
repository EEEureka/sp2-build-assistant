import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("centers_test_cli", ROOT / "cli/sp2build.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class CentersCliTests(unittest.TestCase):
    def fixture(self):
        return json.loads((ROOT / "tests/artifacts/centers-0.4.0/summary.json").read_text(encoding="utf-8-sig"))

    def load(self, report):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "before.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            return cli.centers_module().load_baseline(str(path), cli.CliError)

    def test_images_presence_and_output_directory(self):
        command, options = cli.parse(["craft", "centers", "--images", "--output-dir", "test"])
        self.assertEqual(cli.load_args(command, options), {"images": True})

    def test_help_and_discovery_are_offline(self):
        with patch.object(cli, "select_instance", side_effect=AssertionError("contacted game")):
            help_data, _ = cli.execute(["craft", "centers", "--help"])
            listing, _ = cli.execute(["commands", "list"])
        self.assertIn("--images", [item["flag"] for item in help_data["data"]["arguments"]])
        entry = next(x for x in listing["data"]["commandDetails"] if x["name"] == "craft.centers")
        self.assertFalse(entry["mutates"])
        self.assertEqual(entry["minimumPluginVersion"], "0.4.0")

    def test_output_contract_has_centers_contributors_and_relations(self):
        result, _ = cli.execute(["commands", "schema", "--command", "craft.centers"])
        defs = result["data"]["outputSchema"]["$defs"]
        self.assertIn("massMomentAboutComKgM", defs["CenterContributor"]["properties"])
        self.assertIn("cotFromCol", defs["CentersReport"]["properties"]["relations"]["properties"])
        self.assertIn("CenterComparison", defs)

    def test_old_bridge_rejected_before_queue(self):
        with patch.object(cli, "select_instance", return_value={"pid": 1, "pluginVersion": "0.3.2"}), patch.object(cli, "http", side_effect=AssertionError("submitted")):
            with self.assertRaises(cli.CliError) as caught:
                cli.execute(["craft", "centers", "--async"])
        self.assertEqual(caught.exception.code, "unsupported_bridge_feature")

    def test_overlay_requires_new_bridge_before_queue(self):
        with patch.object(cli, "select_instance", return_value={"pid": 1, "pluginVersion": "0.3.2"}), patch.object(cli, "http", side_effect=AssertionError("submitted")):
            with self.assertRaises(cli.CliError):
                cli.execute(["visual", "capture", "--craft-session-id", "s", "--overlays", '{"centers":true}'])

    def test_baseline_load_keeps_data_drops_images_contributors(self):
        report = self.fixture()
        report["data"]["visual"] = {"localPath": "untrusted"}
        result = self.load(report)
        self.assertNotIn("visual", result)
        self.assertNotIn("contributors", result)
        self.assertEqual(result["identity"], report["data"]["identity"])

    def test_baseline_receipt_is_rejected(self):
        with self.assertRaises(cli.CliError):
            self.load(cli.ok({"path": "before.json", "resultSuccess": True}))

    def test_baseline_wrong_success_type_is_rejected(self):
        report = self.fixture()
        report["success"] = 1
        with self.assertRaises(cli.CliError):
            self.load(report)

    def test_baseline_boolean_vector_is_rejected(self):
        report = self.fixture()
        report["data"]["centers"]["com"]["positionFrameMeters"][0] = True
        with self.assertRaises(cli.CliError):
            self.load(report)

    def test_baseline_nonfinite_is_rejected(self):
        report = self.fixture()
        report["data"]["centers"]["com"]["positionFrameMeters"][0] = float("inf")
        with self.assertRaises(cli.CliError):
            self.load(report)

    def test_part_reference_needs_identity_token(self):
        report = self.fixture()
        report["data"]["frame"].update(kind="part", partId=1, referenceToken=None)
        with self.assertRaises(cli.CliError):
            self.load(report)

    def test_unavailable_null_centers_baseline_is_accepted(self):
        report = json.loads((ROOT / "tests/artifacts/centers-0.4.0/empty.json").read_text(encoding="utf-8-sig"))
        self.assertIsNone(self.load(report)["centers"]["com"]["positionFrameMeters"])

    def test_async_carries_loaded_baseline_not_file_path(self):
        path = ROOT / "tests/artifacts/centers-0.4.0/summary.json"
        with patch.object(cli, "select_instance", return_value={"pid": 1, "pluginVersion": "0.4.0"}), patch.object(cli, "http", return_value={"operationId": "test", "state": "queued"}) as http, patch.object(cli, "wait", side_effect=AssertionError("waited")):
            result, _ = cli.execute(["craft", "centers", "--baseline", str(path), "--async"])
        self.assertEqual(http.call_args.args[2]["args"]["baseline"]["calculationVersion"], "native-designer-centers-v1")
        self.assertEqual(result["data"]["state"], "queued")

    def test_nested_capture_download_and_operation_result(self):
        result = cli.ok({"visual": {"artifactBase": "v1/visual/test/", "captureId": "test"}})
        fake_module = type("Download", (), {"download": staticmethod(lambda instance, wrapped, directory, error: cli.ok({**wrapped["data"], "manifestPath": str(directory) + "/manifest.json"}))})
        with patch.object(cli, "visual_module", return_value=fake_module):
            actual = cli.visual_download({}, result, {"output-dir": "custom"})
        self.assertEqual(actual["data"]["visual"]["manifestPath"], "custom/manifest.json")

    def test_no_images_does_not_load_downloader(self):
        with patch.object(cli, "visual_module", side_effect=AssertionError("loaded downloader")):
            self.assertEqual(cli.visual_download({}, cli.ok({"visual": None}), {}), cli.ok({"visual": None}))


if __name__ == "__main__":
    unittest.main()
