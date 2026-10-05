"""Developer helper for the user's explicitly authorized DSH feedback session.

DSH_FEEDBACK_URL is the user-provided localhost URL with its login token.
The token is used only in memory and is never written to evidence files.
"""
import argparse
import http.cookiejar
import json
import os
import sys
from pathlib import Path
import urllib.parse
import urllib.request
import uuid


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument("--prompt", type=Path, help="UTF-8 request to send; omitted for a status read")
    parser.add_argument("--mode", choices=("queue", "steer"), default="queue")
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--text-limit", type=int, default=6000)
    parser.add_argument("--diagnostics", action="store_true", help="Show event types and session field names when diagnosing stalled progress")
    args = parser.parse_args()
    login_url = os.environ["DSH_FEEDBACK_URL"]
    parsed = urllib.parse.urlsplit(login_url)
    if parsed.hostname not in ("127.0.0.1", "localhost") or parsed.scheme != "http":
        raise ValueError("This helper expects the authorized local DSH endpoint")
    base = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    with opener.open(login_url, timeout=10) as response:
        response.read()

    def rpc(method, fields):
        envelope = {"type": "client-request", "rpcId": uuid.uuid4().hex, "method": method, "payload": {"args": fields}}
        request = urllib.request.Request(base + "/api/" + method, data=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
                                         headers={"Content-Type": "application/json", "Origin": base})
        with opener.open(request, timeout=30) as response:
            result = json.load(response)["result"]
        if not result["ok"]:
            raise RuntimeError("DSH RPC failed: " + json.dumps(result, ensure_ascii=False))
        return result["value"]

    if args.prompt:
        request = {"requestId": "sp2-feedback-" + uuid.uuid4().hex, "sessionId": args.session, "mode": args.mode, "clientTimeZone": "Asia/Shanghai",
                   "content": [{"type": "text", "text": args.prompt.read_text(encoding="utf-8-sig")}]}
        report = {"request": request, "response": rpc("session/prompt", {"request": request})}
        print(json.dumps(report["response"], ensure_ascii=False))
    else:
        items = rpc("session/list", {"_request": {}})["items"]
        session = next(item for item in items if item["sessionId"] == args.session)
        sequence = session["projections"]["asOfSeq"]
        page = rpc("session/page", {"request": {"address": {"kind": "session", "sessionId": args.session}, "throughSeq": sequence, "maxMessages": 4}})
        texts = []
        for record in page["records"]:
            event = record.get("event", {})
            if event.get("type") == "assistant/message":
                blocks = event.get("data", {}).get("message", {}).get("content", [])
                texts.extend(block["text"] for block in blocks if block.get("type") == "text")
        report = {"sessionId": args.session, "running": session["running"], "throughSeq": sequence, "texts": texts}
        if args.diagnostics:
            report["diagnostics"] = {"sessionFields": list(session), "projectionFields": list(session["projections"]),
                "recentEvents": [{"type": record.get("event", {}).get("type"), "recordFields": list(record),
                                  "dataFields": list(record.get("event", {}).get("data", {}))} for record in page["records"]]}
            calls = [record["event"]["data"] for record in page["records"] if record.get("event", {}).get("type") == "tool/call"]
            report["diagnostics"]["lastToolCall"] = calls[-1] if calls else None
        print(json.dumps({key: value for key, value in report.items() if key != "texts"}, ensure_ascii=False))
        print("\n".join(texts)[-args.text_limit:])
    args.record.parent.mkdir(parents=True, exist_ok=True)
    args.record.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
