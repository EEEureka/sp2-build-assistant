import importlib.util
import unittest
import io
import json
import os
import tempfile
from urllib.error import HTTPError
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("sp2build", Path(__file__).parents[1] / "cli" / "sp2build.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class RecoveryContractTests(unittest.TestCase):
    def test_selected_instance_does_not_probe_other_games(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/"SP2BuildAssistant"/"instances";folder.mkdir(parents=True)
            for pid in (123,456):
                (folder/f"{pid}.json").write_text(json.dumps({"pid":pid,"instanceId":f"i{pid}","baseUrl":"http://127.0.0.1:24730/"}))
            with patch.dict(os.environ,{"LOCALAPPDATA":tmp}), patch.object(cli,"is_running",return_value=True), patch.object(cli,"instance_responds",return_value=True) as probe:
                self.assertEqual([i["pid"] for i in cli.instances("i123")],[123])
                self.assertEqual(probe.call_count,1)
                self.assertEqual(probe.call_args.args[0]["pid"],123)

    def test_discovery_requires_authenticated_operation_lookup(self):
        item={"baseUrl":"http://127.0.0.1:24730/","token":"test-token"}
        for code,expected in (("operation_not_found",True),("unauthorized",False),("route_not_found",False)):
            body=json.dumps({"success":False,"error":{"code":code}}).encode()
            error=HTTPError(item["baseUrl"],400,"test",{},io.BytesIO(body))
            with patch.object(cli,"build_opener") as opener:
                opener.return_value.open.side_effect=error
                self.assertEqual(cli.instance_responds(item),expected)
                args,kwargs=opener.return_value.open.call_args
                self.assertEqual(args[0].get_method(),"GET")
                self.assertIn("/v1/operations/discovery-",args[0].full_url)
                self.assertEqual(args[0].get_header("X-sp2build-token"),"test-token")

    def test_stale_reused_pid_and_port_do_not_count_as_an_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/"SP2BuildAssistant"/"instances";folder.mkdir(parents=True)
            for pid,token in ((123,"current"),(456,"stale")):
                (folder/f"{pid}.json").write_text(json.dumps({"pid":pid,"token":token,"baseUrl":"http://127.0.0.1:24730/"}))
            with patch.dict(os.environ,{"LOCALAPPDATA":tmp}),patch.object(cli,"is_running",return_value=True),patch.object(cli,"instance_responds",side_effect=lambda i:i["token"]=="current"):
                self.assertEqual([i["pid"] for i in cli.instances()],[123])

    def test_fixed_camera_replay_rejects_older_loaded_bridge(self):
        with patch.object(cli, "select_instance", return_value={"pid":1,"pluginVersion":"0.4.11"}), patch.object(cli, "http") as http, patch.object(cli,"load_args",return_value={"craftSessionId":"s","views":[{"name":"front","view":"fixed"}]}):
            with self.assertRaises(cli.CliError) as ctx:
                cli.execute(["designer", "capture"])
        self.assertEqual(ctx.exception.code,"unsupported_bridge_feature")
        http.assert_not_called()
    def test_properties_output_describes_real_nested_shape(self):
        output = cli.contracts_module().output_schema("properties.get")
        part = output["properties"]["data"]["properties"]["parts"]["items"]
        self.assertIn("fields", part["properties"])
        descriptor = output["$defs"]["EffectiveProperty"]
        self.assertIn("editability", descriptor["required"])
        self.assertIn("valueSource", descriptor["required"])
        prerequisite = descriptor["properties"]["currentCondition"]
        self.assertIn("satisfied", prerequisite["required"])
        self.assertIn({"type":"null"}, prerequisite["properties"]["satisfied"]["anyOf"])

    def test_properties_reads_and_batch_reject_older_bridge_before_submission(self):
        calls = [(["properties", "get", "--id", "76"], None),
                 (["batch", "apply"], {"craftSessionId":"s", "expectedRevision":1, "requestId":"key", "operations":[{"kind":"properties.set", "partId":76,"patch":{"ProceduralWindow[0].topWidth":0.5}}]})]
        for argv, args in calls:
            with self.subTest(argv=argv), patch.object(cli, "select_instance", return_value={"pid":1,"pluginVersion":"0.4.11"}), patch.object(cli,"http") as http:
                if args is None:
                    with self.assertRaises(cli.CliError) as ctx:
                        cli.execute(argv)
                else:
                    with patch.object(cli,"load_args",return_value=args), self.assertRaises(cli.CliError) as ctx:
                        cli.execute(argv)
                self.assertEqual(ctx.exception.code,"unsupported_bridge_feature")
                http.assert_not_called()

    def test_designer_capture_help_and_output_directory(self):
        command, options = cli.parse(["designer", "capture", "--craft-session-id", "session", "--views", '["front"]', "--output-dir", "captures"])
        self.assertEqual(command, "designer.capture")
        args = cli.load_args(command, options)
        self.assertEqual(args, {"craftSessionId": "session", "views": ["front"]})
        self.assertIn(command, cli.command_names())
        self.assertIsNotNone(cli.contracts_module().output_schema(command))

    def test_designer_capture_rejects_older_loaded_bridge(self):
        with patch.object(cli, "select_instance", return_value={"pid": 1, "pluginVersion": "0.4.10"}), patch.object(cli, "http") as http:
            with self.assertRaises(cli.CliError) as ctx:
                cli.execute(["designer", "capture", "--craft-session-id", "session"])
        self.assertEqual(ctx.exception.code, "unsupported_bridge_feature")
        http.assert_not_called()

    def test_designer_capture_routes_native_job_and_download(self):
        result = cli.ok({"captureId": "capture"})
        with patch.object(cli, "select_instance", return_value={"pid": 1, "pluginVersion": "0.4.11"}), patch.object(cli, "http", return_value={"operationId": "operation"}) as http, patch.object(cli, "wait", return_value=result), patch.object(cli, "visual_download", return_value=result) as download:
            actual, options = cli.execute(["designer", "capture", "--craft-session-id", "session", "--output-dir", "captures"])
        self.assertEqual(http.call_args.args[2]["command"], "designer.capture")
        self.assertEqual(download.call_args.args[2]["output-dir"], "captures")
        self.assertEqual(actual, result)

    def test_unknown_flag_has_same_diagnostic_with_or_without_value(self):
        messages = []
        for tail in (["--include-disconnected"], ["--include-disconnected", "true"], ["--include-disconnected", "--metric", "mass"]):
            with self.subTest(tail=tail), patch.object(cli, "select_instance", side_effect=AssertionError("invalid CLI input contacted game")):
                with self.assertRaises(cli.CliError) as ctx:
                    cli.execute(["craft", "centers", *tail])
                self.assertEqual(ctx.exception.code, "invalid_input")
                messages.append(str(ctx.exception))
        self.assertEqual(len(set(messages)), 1)
        self.assertIn("Unknown option --include-disconnected for craft.centers", messages[0])

    def test_known_missing_flag_value_retains_specific_diagnostic(self):
        for words, flag in ((["parts", "get"], "id"), (["craft", "centers"], "baseline"), (["version"], "output"), (["commands", "schema"], "operation")):
            with self.subTest(flag=flag), patch.object(cli, "select_instance", side_effect=AssertionError("missing CLI input contacted game")):
                with self.assertRaises(cli.CliError) as ctx:
                    cli.execute([*words, "--" + flag])
                self.assertEqual(str(ctx.exception), "--" + flag + " requires a value")

    def test_valueless_images_switch_is_still_accepted(self):
        self.assertEqual(cli.parse(["craft", "centers", "--images", "--metric", "lift"]), ("craft.centers", {"images": True, "metric": "lift"}))

    def test_structured_views_are_discoverable_without_changing_legacy_default(self):
        for command in ("connections.list", "variables.list", "outputs.list"):
            request = cli.schema(command)
            self.assertEqual(request["properties"]["view"]["default"], "legacy")
            self.assertIn("structured", request["properties"]["view"]["enum"])
            self.assertEqual(cli.load_args(command, {"view": "structured"}), {"view": "structured"})

    def test_reorder_contract_is_shared_by_batch_and_shortcut(self):
        operation = cli.schema("variable.reorder", operation_only=True)["properties"]["order"]
        shortcut = cli.schema("variables.reorder")["properties"]["operation"]["properties"]["order"]
        self.assertEqual(operation, shortcut)
        self.assertEqual(operation["items"], {"type": "integer", "minimum": 0})
        self.assertTrue(operation["uniqueItems"])
        self.assertIn("NEW sequence", operation["description"])

    def test_old_bridge_cannot_silently_claim_a_structured_view(self):
        with patch.object(cli, "select_instance", return_value={"pid": 123}), patch.object(cli, "http", return_value={"operationId": "test"}), patch.object(cli, "wait", return_value=cli.ok({"connections": None})):
            with self.assertRaises(cli.CliError) as ctx:
                cli.execute(["connections", "list", "--view", "structured"])
        self.assertEqual(ctx.exception.code, "unsupported_bridge_feature")

    def test_global_help_discovers_output_and_capture_destinations_offline(self):
        with patch.object(cli, "select_instance", side_effect=AssertionError("help accessed game")):
            result, _ = cli.execute(["--help"])
        self.assertTrue({"--output", "--instance", "--input"} <= result["data"]["globalOptions"].keys())
        self.assertIn("operation.result", result["data"]["contextOptions"]["--output-dir"]["commands"])

    def test_capture_help_exposes_current_detail_policy_offline(self):
        with patch.object(cli, "select_instance", side_effect=AssertionError("help accessed game")):
            result, _ = cli.execute(["visual", "capture", "--help"])
        args = {arg["flag"]: arg for arg in result["data"]["arguments"]}
        self.assertEqual(args["--details"]["default"], "auto")
        self.assertTrue(args["--craft-session-id"]["required"])

    def test_shortcut_help_does_not_advertise_unsupported_operation_flags(self):
        result, _ = cli.execute(["connections", "connect", "--help"])
        self.assertEqual(result["data"]["inputMode"], "guarded_operation_file")
        self.assertEqual(result["data"]["operationKind"], "connection.connect")
        self.assertIn("operation", result["data"]["requiredInputFields"])
        self.assertEqual(result["data"]["arguments"], [])

    def test_group_help_filters_commands_and_unknown_help_fails(self):
        result, _ = cli.execute(["parts", "--help"])
        self.assertTrue(all(name.startswith("parts.") for name in result["data"]["commands"]))
        result, _ = cli.execute(["operation", "status", "--help"])
        self.assertIn({"flag": "--id", "field": "id", "required": True, "type": "string"}, result["data"]["arguments"])
        with self.assertRaises(cli.CliError):
            cli.execute(["not-a-command", "--help"])

    def test_command_operation_mapping_is_discoverable(self):
        result, _ = cli.execute(["commands", "list"])
        link = next(x for x in result["data"]["commandDetails"] if x["name"] == "connections.connect")
        self.assertEqual(link["operationKind"], "connection.connect")
        self.assertNotIn("connection.connect", result["data"]["commands"])

    def test_explicit_operation_schema_disambiguates_self_alias(self):
        operation, _ = cli.execute(["commands", "schema", "--operation", "shape.update"])
        command, _ = cli.execute(["commands", "schema", "--command", "shape.update"])
        self.assertEqual(operation["data"]["entityKind"], "operation")
        self.assertIn("kind", operation["data"]["inputSchema"]["required"])
        self.assertEqual(command["data"]["entityKind"], "command")
        self.assertIn("operation", command["data"]["inputSchema"]["required"])

    def test_legacy_operation_query_remains_explicit_and_compatible(self):
        result, _ = cli.execute(["commands", "schema", "--command", "connection.connect"])
        self.assertTrue(result["data"]["legacyQuery"])
        self.assertEqual(result["data"]["entityKind"], "operation")
        self.assertNotIn("outputSchema", result["data"])

    def test_output_schema_has_real_part_path_and_attach_point_fields(self):
        result, _ = cli.execute(["commands", "schema", "--command", "parts.get"])
        output = result["data"]["outputSchema"]
        self.assertEqual(output["properties"]["data"]["properties"]["part"]["$ref"], "#/$defs/PartDetail")
        self.assertTrue({"id", "normal", "localPosition", "jointAxisLocal"} <= output["$defs"]["AttachPoint"]["properties"].keys())
        # Piston's native driven point is distinct from a rotator's rotor.
        self.assertIn("moving_end", output["$defs"]["AttachPoint"]["properties"]["role"]["enum"])
        self.assertNotIn("CatalogTemplate", output["$defs"])

    def test_attach_point_extensions_preserve_legacy_dll_contract(self):
        for command in ("parts.get", "connections.points"):
            result, _ = cli.execute(["commands", "schema", "--command", command])
            point = result["data"]["outputSchema"]["$defs"]["AttachPoint"]
            extensions = {"seekTypes", "receiveTypes", "excludeTypes",
                          "seekTypeMask", "receiveTypeMask", "excludeTypeMask"}
            self.assertTrue(extensions <= point["properties"].keys())
            self.assertFalse(extensions & set(point["required"]))
            self.assertTrue({"id", "localPosition", "normal", "jointAxisLocal",
                             "seekType", "receiveType", "role"} <= set(point["required"]))
            for field in extensions:
                self.assertIn("older DLLs", point["properties"][field]["description"])

    def test_schema_target_must_be_unambiguous(self):
        with self.assertRaises(cli.CliError):
            cli.execute(["commands", "schema", "--operation", "part.add", "--command", "parts.add"])

    def test_assembly_preview_accepts_explicit_symmetry(self):
        self.assertEqual(cli.load_args("parts.assembly", {"id":"229", "symmetric":"true"}), {"id":229,"symmetric":True})

    def test_assembly_delete_preserves_single_part_default(self):
        schema = cli.schema("parts.delete")
        operation = schema["properties"]["operation"]
        self.assertEqual(operation["properties"]["assembly"], {"type":"boolean"})
        self.assertNotIn("assembly", operation["required"])

    def test_new_shortcut_schema_uses_guarded_operation(self):
        schema = cli.schema("shape.update")
        self.assertIn("craftSessionId", schema["required"])
        self.assertIn("operation", schema["required"])
        self.assertEqual(schema["properties"]["operation"]["properties"]["kind"]["const"], "shape.update")
        self.assertNotIn("kind", schema["properties"]["operation"]["required"])

    def test_batch_schema_preserves_operation_kinds(self):
        choices = cli.schema("batch.apply")["properties"]["operations"]["items"]["oneOf"]
        kinds = {s["properties"]["kind"]["const"] for s in choices}
        self.assertTrue({"shape.update", "wing.control.add", "craft.refresh", "symmetry.link"} <= kinds)
        self.assertTrue(all("kind" in s["required"] for s in choices))

    def test_geometry_raycast_parses_numeric_distance(self):
        args = cli.load_args("designer.raycast", {"origin": "[0,2,0]", "direction": "[0,-1,0]", "distance": "3.5"})
        self.assertEqual(args, {"origin": [0,2,0], "direction": [0,-1,0], "distance": 3.5})

    def test_complex_inventory_available_without_game(self):
        with patch.object(cli, "select_instance", side_effect=AssertionError("offline query accessed game")):
            result, _ = cli.execute(["knowledge", "complex", "--family", "wing"])
        families = result["data"]["knowledge"]["families"]
        self.assertEqual([f["id"] for f in families], ["wing"])
        self.assertTrue(families[0]["nativeTemplates"])

    def test_timeout_keeps_operation_id_and_instance(self):
        with patch.object(cli, "http", return_value={"state": "running"}), patch.object(cli.time, "monotonic", side_effect=[0.0, 1.0]):
            with self.assertRaises(cli.CliError) as ctx:
                cli.wait({"pid": 123}, "real-operation", 0.1)
        self.assertEqual(ctx.exception.code, "wait_timeout")
        self.assertEqual(ctx.exception.details["operationId"], "real-operation")
        self.assertEqual(ctx.exception.details["instancePid"], 123)

    def test_failed_batch_keeps_rollback_evidence(self):
        native = {"success": False, "schemaVersion": "1", "error": {"code": "execution_failed"}, "rollbackResult": {"restored": True}}
        with patch.object(cli, "http", return_value={"state": "failed", "result": native}):
            result = cli.wait({"pid": 123}, "real-operation", 1)
        self.assertFalse(result["success"])
        self.assertTrue(result["rollbackResult"]["restored"])
        self.assertEqual(result["operationId"], "real-operation")

    def test_expired_result_is_not_treated_as_unexecuted(self):
        with patch.object(cli, "http", return_value={"state": "result_expired", "result": None, "completionState":"succeeded", "resultRetention":"age_or_capacity_limit"}):
            with self.assertRaises(cli.CliError) as ctx:
                cli.wait({"pid": 123}, "real-operation", 1)
        self.assertEqual(ctx.exception.code, "result_expired")
        self.assertEqual(ctx.exception.details["operationId"], "real-operation")
        self.assertEqual(ctx.exception.details["completionState"], "succeeded")
        self.assertEqual(ctx.exception.details["resultRetention"], "age_or_capacity_limit")
        self.assertIn("do not resubmit", str(ctx.exception))

    def test_saved_aircraft_path_is_rejected(self):
        with self.assertRaises(cli.CliError):
            cli.load_args("craft.snapshot", {"file": "other-aircraft.xml"})

    def test_json_schema_accepts_documented_request_id(self):
        schema = cli.schema("batch.apply")
        self.assertIn("requestId", schema["properties"])
        self.assertFalse(schema["additionalProperties"])

    def test_missing_request_id_cannot_submit_write(self):
        with patch.object(cli, "select_instance", return_value={"pid": 123}), patch.object(cli, "load_args", return_value={"craftSessionId": "current", "expectedRevision": 1, "operations": []}), patch.object(cli, "http") as http:
            with self.assertRaises(cli.CliError) as ctx:
                cli.execute(["batch", "apply"])
        self.assertEqual(ctx.exception.code, "invalid_input")
        http.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
