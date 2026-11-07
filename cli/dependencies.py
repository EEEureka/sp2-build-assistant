"""Explicit CPU-worker installation and stdlib-only, isolated JSON transport.

Importing this module, discovery, doctor and worker_call never install or download.
Only setup() is an installation action. The product does not use host-site packages,
Blender Python, or Codex's dependency runtimes.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent
PROTOCOL_VERSION = 1


class DependencyError(ValueError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def manifest():
    return json.loads((HERE / "reference-worker-wheels.json").read_text(encoding="utf-8"))


def worker_root():
    # USERPROFILE is intentionally preferred to redirected application caches.
    return Path(os.environ.get("SP2BUILD_HOME") or
                (Path(os.environ.get("USERPROFILE") or Path.home()) / ".sp2build")).resolve()


def worker_python():
    override = os.environ.get("SP2BUILD_REFERENCE_PYTHON")
    if override:
        path = Path(override)
        if not path.is_absolute():
            raise DependencyError("worker_path_not_absolute", "Worker Python must be an absolute path.")
        return path
    return worker_root() / "workers" / "reference-cpu" / manifest()["bundleVersion"] / "Scripts" / "python.exe"


def _run_json(python, args, value=None, timeout=120):
    python = Path(python)
    if not python.is_absolute():
        raise DependencyError("worker_path_not_absolute", "Worker Python must be an absolute path.")
    if not python.is_file():
        raise DependencyError("worker_not_installed", "CPU reference worker is not installed. Run sp2build feature setup.", {"python": str(python)})
    env = os.environ.copy()
    # -I isolates imports and ignores PYTHONPATH/PYTHONHOME. -X utf8 also sets
    # stdio on Windows where -I intentionally ignores PYTHONUTF8.
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    try:
        run = subprocess.run([str(python), "-I", "-X", "utf8", *map(str, args)],
                             input=json.dumps(value, ensure_ascii=False, allow_nan=False) if value is not None else None,
                             capture_output=True, text=True, encoding="utf-8", errors="strict",
                             timeout=timeout, env=env, **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
    except subprocess.TimeoutExpired as error:
        raise DependencyError("worker_timeout", "CPU worker exceeded its time budget.", {"timeoutSeconds": timeout}) from error
    except (OSError, UnicodeError) as error:
        raise DependencyError("worker_start_failed", str(error)) from error
    try:
        result = json.loads(run.stdout)
    except (ValueError, TypeError) as error:
        raise DependencyError("worker_invalid_response", "CPU worker did not return one UTF-8 JSON value.", {"exitCode": run.returncode, "stderr": run.stderr[-2000:]}) from error
    if not isinstance(result, dict):
        raise DependencyError("worker_invalid_response", "CPU worker response must be an object.")
    if run.returncode and result.get("success") is not False:
        raise DependencyError("worker_failed", "CPU worker exited unsuccessfully.", {"exitCode": run.returncode, "stderr": run.stderr[-2000:]})
    return result


def worker_call(command, payload, timeout=120, worker_python=None, entrypoint=None):
    program = Path(entrypoint or (HERE / "reference_worker" / "main.py"))
    if not program.is_absolute() or not program.is_file():
        raise DependencyError("worker_code_missing", "CPU worker entrypoint is missing.", {"entrypoint": str(program)})
    interpreter = worker_python or globals()["worker_python"]()
    result = _run_json(interpreter, [program], {"protocolVersion": PROTOCOL_VERSION, "command": command, "payload": payload}, timeout)
    if not result.get("success"):
        error = result.get("error") or {}
        raise DependencyError(error.get("code", "worker_failed"), error.get("message", "CPU worker failed."), error.get("details"))
    if "result" not in result:
        raise DependencyError("worker_invalid_response", "Successful CPU worker response has no result field.")
    return result["result"]


_PROBE = """
import json, platform, struct, sys
from importlib.metadata import version, PackageNotFoundError
names=['numpy','pillow','opencv-python-headless','scipy']
versions={}
for name in names:
    try: versions[name]=version(name)
    except PackageNotFoundError: versions[name]=None
print(json.dumps({'python':sys.version.split()[0],'implementation':platform.python_implementation(),'major':sys.version_info.major,'minor':sys.version_info.minor,'bits':struct.calcsize('P')*8,'platform':sys.platform,'packages':versions,'isolated':bool(sys.flags.isolated)}))
"""


def doctor(payload=None):
    payload = payload or {}
    expected = manifest()
    interpreter = Path(payload.get("workerPython") or worker_python())
    result = {"available": False, "requiresGame": False, "downloadsAttempted": False,
              "bundleVersion": expected["bundleVersion"], "python": str(interpreter),
              "missingDependencies": [], "minimumBridgeProtocol": None, "validatedGameVersions": []}
    try:
        probe = _run_json(interpreter, ["-c", _PROBE], timeout=30)
        result["environment"] = probe
        abi = expected["python"]
        if any(probe.get(key) != value for key, value in abi.items()):
            result.update(reasonCode="worker_abi_mismatch", expectedPython=abi)
            return result
        result["missingDependencies"] = [f"{p['name']}=={p['version']}" for p in expected["packages"] if probe.get("packages", {}).get(p["name"]) != p["version"]]
        if result["missingDependencies"]:
            result["reasonCode"] = "worker_dependencies_missing_or_mismatched"
            return result
        entrypoint = HERE / "reference_worker" / "main.py"
        if not entrypoint.is_file():
            result.update(reasonCode="worker_code_missing", details={"entrypoint": str(entrypoint)})
            return result
        if payload.get("selfTest", True):
            result["selfTest"] = worker_call("doctor", {}, worker_python=interpreter, timeout=30)
            if result["selfTest"].get("available") is not True or result["selfTest"].get("numericSelftest") != "pass":
                result["reasonCode"] = "worker_selftest_failed"
                return result
        result.update(available=True, reasonCode="available")
    except DependencyError as error:
        result.update(reasonCode=error.code, message=str(error), details=error.details)
    return result


def _checked_wheel(path, package):
    if not path.is_file() or path.stat().st_size != package["size"]:
        return False
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else _file_hash(stream)
    return digest == package["sha256"]


def _file_hash(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def _installer_run(args, timeout=300):
    try:
        run = subprocess.run(list(map(str, args)), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                             **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
    except subprocess.TimeoutExpired as error:
        raise DependencyError("worker_install_timeout", "Worker installation subprocess exceeded its time budget.", {"timeoutSeconds": timeout}) from error
    except OSError as error:
        raise DependencyError("worker_install_failed", str(error)) from error
    if run.returncode:
        raise DependencyError("worker_install_failed", "Worker installation subprocess failed.", {"exitCode": run.returncode, "output": (run.stdout + run.stderr)[-6000:]})


def _find_python(explicit=None):
    candidates = [explicit] if explicit else []
    if not explicit:
        candidates.append(sys.executable)
        try:
            found = subprocess.run(["py.exe", "-3.12", "-c", "import sys;print(sys.executable)"], capture_output=True, text=True, timeout=15,
                                   **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
            if found.returncode == 0:
                candidates.append(found.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            pass
    abi = manifest()["python"]
    for candidate in candidates:
        if not candidate or not Path(candidate).is_absolute():
            continue
        try:
            probe = _run_json(candidate, ["-c", _PROBE], timeout=15)
            if all(probe.get(key) == value for key, value in abi.items()):
                # Do not silently choose a product runtime owned by Codex.
                if any(marker in str(candidate).lower() for marker in (".codex", "openai-bundled", "workspace_dependencies")):
                    continue
                return str(Path(candidate).resolve())
        except DependencyError:
            continue
    raise DependencyError("worker_python_required", "Install ordinary 64-bit CPython 3.12, or provide its absolute path as python. Core editing remains available.", {"expectedPython": abi})


def setup(payload=None):
    """Explicit full-reference install; offline=True forbids network access."""
    payload = payload or {}
    expected = manifest()
    current = doctor({"selfTest": False})
    if current["available"] and not payload.get("force", False):
        checked = doctor()
        if not checked["available"]:
            raise DependencyError("worker_install_verification_failed", "Installed CPU worker failed its numerical self-test.", checked)
        return {"installed": True, "alreadyCurrent": True, "doctor": checked}
    base_python = _find_python(payload.get("python"))
    target_python = worker_python()
    if os.environ.get("SP2BUILD_REFERENCE_PYTHON"):
        raise DependencyError("worker_override_active", "Unset SP2BUILD_REFERENCE_PYTHON before installing the managed worker.")
    target = target_python.parent.parent
    wheelhouse = Path(payload.get("wheelhouse") or (worker_root() / "workers" / "wheelhouse" / expected["bundleVersion"])).resolve()
    offline = bool(payload.get("offline", False))
    wheelhouse.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = target.with_name(target.name + ".install.lock")
    try:
        lock_file = lock.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise DependencyError("worker_install_busy", "Another installation is running, or its installation lock needs inspection.", {"lock": str(lock)}) from error
    downloaded = []
    try:
        with lock_file:
            lock_file.write(json.dumps({"pid": os.getpid(), "started": time.time()}))
        for package in expected["packages"]:
            path = wheelhouse / package["filename"]
            if _checked_wheel(path, package):
                continue
            if path.exists():
                raise DependencyError("wheel_hash_mismatch", "Cached wheel does not match the locked artifact.", {"path": str(path), "expectedSha256": package["sha256"]})
            if offline:
                raise DependencyError("offline_wheel_missing", "Offline installation requires every locked Windows wheel.", {"path": str(path)})
            temporary = path.with_suffix(path.suffix + ".part")
            try:
                download_url = package["url"]
                if payload.get("downloadBase"):
                    base = str(payload["downloadBase"]).rstrip("/")
                    if not base.startswith("https://"):
                        raise DependencyError("invalid_download_base", "Wheel downloadBase must use HTTPS.")
                    download_url = base + "/packages/" + package["url"].split("/packages/", 1)[1]
                download_started = time.monotonic()
                with urllib.request.urlopen(download_url, timeout=30) as response, temporary.open("wb") as output:
                    downloaded_bytes = 0
                    for block in iter(lambda: response.read1(64 * 1024), b""):
                        if time.monotonic() - download_started > 180:
                            raise TimeoutError("Wheel download exceeded the 180 second artifact budget. Supply a prepopulated wheelhouse for offline installation.")
                        downloaded_bytes += len(block)
                        if downloaded_bytes > package["size"]:
                            raise DependencyError("wheel_hash_mismatch", "Downloaded artifact exceeds its locked size.", {"filename": package["filename"]})
                        output.write(block)
                if not _checked_wheel(temporary, package):
                    raise DependencyError("wheel_hash_mismatch", "Downloaded wheel failed locked SHA256/size validation.", {"filename": package["filename"]})
                temporary.replace(path)
                downloaded.append(package["filename"])
            except (OSError, TimeoutError) as error:
                raise DependencyError("wheel_download_failed", str(error), {"filename": package["filename"]}) from error
            finally:
                temporary.unlink(missing_ok=True)
        # Create at the final path. Relocating a venv breaks scripts on Windows.
        _installer_run([base_python, "-I", "-X", "utf8", "-m", "venv", str(target)])
        args = [target_python, "-I", "-X", "utf8", "-m", "pip", "--isolated", "install", "--no-index", "--only-binary=:all:", "--require-hashes", "--no-deps", "--find-links", wheelhouse, "-r", HERE / "reference-worker-requirements.lock"]
        if payload.get("force"):
            args.append("--force-reinstall")
        _installer_run(args)
        checked = doctor({"selfTest": False})
        if not checked["available"]:
            raise DependencyError("worker_install_verification_failed", "Installed CPU worker does not match the lock.", checked)
        receipt = {"schemaVersion": 1, "bundleVersion": expected["bundleVersion"], "python": str(target_python), "basePython": base_python,
                   "installedAtUnix": time.time(), "packages": expected["packages"]}
        (target / "sp2build-worker.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        checked = doctor()
        if not checked["available"]:
            raise DependencyError("worker_install_verification_failed", "Installed CPU worker failed its numerical self-test.", checked)
        return {"installed": True, "alreadyCurrent": False, "downloaded": downloaded, "offline": offline, "python": str(target_python), "doctor": checked}
    finally:
        lock.unlink(missing_ok=True)


def dispatch(action, payload=None):
    if action in ("reference.doctor", "feature.doctor", "doctor"):
        return doctor(payload)
    if action in ("feature.setup", "setup"):
        return setup(payload)
    raise DependencyError("unknown_local_action", f"Unknown dependency action: {action}")
