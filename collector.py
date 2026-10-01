#!/usr/bin/python3
"""PowerTOP CLI adapter. The popup consumes JSON, never raw command lines."""
import csv
from datetime import datetime
import io
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time


def number(raw, unit=""):
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Zµ/%]*)\s*", raw)
    if not match:
        return None
    value = float(match[1])
    suffix = match[2]
    if unit == "W":
        factor = {"W": 1, "mW": 0.001, "uW": 0.000001, "µW": 0.000001}.get(suffix)
        if factor is None:
            return None
        value *= factor
    return value if math.isfinite(value) else None


def app_name(description):
    command = re.sub(r"^\[PID \d+\]\s*", "", description).strip()
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    if not words:
        return "Unknown"
    name = Path(words[0]).name.strip("[]")
    # Attribute interpreter-launched services to their script, when available.
    if name.startswith(("python", "bash")) and len(words) > 1 and not words[1].startswith("-"):
        name = Path(words[1]).name
    return name


def parse_report(raw):
    start = raw.find("PowerTOP\n")
    if start < 0:
        raise ValueError("PowerTOP returned no report")
    rows = list(csv.reader(io.StringIO(raw[start:])))
    section = ""
    header = None
    apps = {}
    discharge = None
    found_overview = False
    has_power = False
    sampled_at = int(time.time())
    for row in rows:
        if not row:
            continue
        if row[0].startswith("# "):
            section = row[0][2:].strip()
            header = None
            continue
        if row[0] == "PowerTOP Version" and len(row) > 1 and " ran at " in row[1]:
            try:
                sampled_at = int(datetime.strptime(row[1].split(" ran at ", 1)[1],
                                                   "%a %b %d %H:%M:%S %Y").timestamp())
            except ValueError:
                pass
        if row[0].startswith("The battery reports a discharge rate") and len(row) > 1:
            discharge = number(row[1], "W")
        if section != "Overview of Software Power Consumers":
            continue
        if "Category" in row and "Description" in row:
            header = [item.strip() for item in row]
            found_overview = True
            has_power = any(item.lower().startswith("power") for item in header)
            continue
        if not header or len(row) != len(header):
            continue
        data = dict(zip(header, row))
        if data["Category"].strip() != "Process":
            continue
        name = app_name(data["Description"])
        # Keep device/interrupt/kernel bookkeeping out of the app list.
        if data["Description"].strip().endswith("]"):
            continue
        wakeups = number(data.get("Wakeups/s", ""))
        power_text = next((v for k, v in data.items() if k.lower().startswith("power")), "")
        watts = number(power_text, "W")
        entry = apps.setdefault(name, {"name": name, "watts": 0.0, "wakeups": 0.0,
                                       "processes": 0})
        entry["processes"] += 1
        entry["wakeups"] += wakeups or 0.0
        if watts is None or entry["watts"] is None:
            entry["watts"] = None
        else:
            entry["watts"] += watts
    if not found_overview:
        raise ValueError("PowerTOP report is missing its process table")
    mode = "power" if has_power and any(a["watts"] is not None for a in apps.values()) else "activity"
    ordered = sorted(apps.values(), key=lambda a: (
        -(a["watts"] if mode == "power" and a["watts"] is not None else
          a["wakeups"] if mode == "activity" else -1), a["name"]))[:10]
    return {"schemaVersion": 1, "source": "powertop", "mode": mode,
            "sampledAt": sampled_at, "dischargeWatts": discharge, "apps": ordered}


def cache_path():
    return Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "omavolt" / "sample.json"


def collect():
    # Root only runs the installed binary with fixed arguments; Python and QML
    # remain unprivileged. /dev/stdout avoids privileged writes to user paths.
    result = subprocess.run(["/usr/bin/pkexec", "/usr/bin/powertop", "--csv=/dev/stdout",
                             "--time=10", "--iteration=1"],
                            capture_output=True, text=True, timeout=120,
                            env={**os.environ, "LC_ALL": "C"})
    if result.returncode:
        raise RuntimeError("PowerTOP measurement failed or authentication was cancelled")
    sample = parse_report(result.stdout)
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
            temporary = Path(f.name)
            json.dump(sample, f)
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return sample


def main():
    try:
        action = sys.argv[1] if len(sys.argv) > 1 else "read"
        if action == "capture":
            result = collect()
        elif action == "read":
            path = cache_path()
            result = json.loads(path.read_text()) if path.exists() else {"apps": [], "mode": "empty"}
        elif action == "parse" and len(sys.argv) == 3:
            result = parse_report(Path(sys.argv[2]).read_text())
        else:
            raise ValueError("Usage: collector.py [read|capture|parse REPORT.csv]")
        print(json.dumps(result))
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"error": str(error)}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
