"""
Sandbox client: runs `runner.py` in a child Python process and exchanges JSON with it.

Keeping this in one small function makes the isolation boundary easy to point at during a
presentation: everything the user wrote runs on the other side of `subprocess.run`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Dict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_in_sandbox(request: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    """Execute a runner request. Always returns a dict with at least {"ok": bool}."""
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": PROJECT_ROOT, "PYTHONHASHSEED": "0"}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "backend.services.runner"],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=PROJECT_ROOT,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"The algorithm process exceeded the overall limit of {timeout:.0f}s."}

    if not proc.stdout.strip():
        detail = (proc.stderr or "").strip().splitlines()[-1:] or ["no output"]
        if proc.returncode and proc.returncode < 0:
            detail = [f"process killed by signal {-proc.returncode} (CPU/memory limit?)"]
        return {"ok": False, "error": f"The algorithm process crashed: {detail[0]}"}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "Could not decode the runner's response."}
