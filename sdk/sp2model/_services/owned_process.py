"""Bounded subprocesses owned by numerical worker installation/execution."""
import os
import subprocess


def run_owned(args, *, input=None, timeout, env=None, errors='strict'):
    flags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == 'nt' else 0
    process = subprocess.Popen(list(map(str, args)), stdin=subprocess.PIPE if input is not None else None,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               encoding='utf-8', errors=errors, env=env, creationflags=flags)
    try:
        stdout, stderr = process.communicate(input, timeout=timeout)
    except (subprocess.TimeoutExpired, UnicodeError):
        # Windows venv Python may be a redirector with a real Python child.
        # Terminating only the redirector leaves the numerical task running.
        if process.poll() is None:
            if os.name == 'nt':
                try:
                    subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                except (OSError, subprocess.TimeoutExpired): pass
            if process.poll() is None: process.kill()
        process.communicate(timeout=10)
        raise
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
