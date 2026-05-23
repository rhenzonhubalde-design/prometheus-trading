"""
Write a Plotus brief drop to local disk and push it to Google Drive via rclone.

Per-drop folder layout:

    gdrive:AI Trading/Plotus/Briefs/{YYYY-MM-DD}/
        brief.md     # narrative for Hermes
        data.json    # sanitized percentages-only payload

Local mirror lives under data/plotus_briefs/ (gitignored alongside data/snapshots).
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Mapping, Tuple


BASE_DIR        = os.path.expanduser('~/prometheus')
LOCAL_DROP_ROOT = os.path.join(BASE_DIR, 'data', 'plotus_briefs')
GDRIVE_ROOT     = 'gdrive:AI Trading/Plotus/Briefs'


def write_drop_locally(date_iso: str, brief_md: str, payload: Mapping) -> Tuple[str, str]:
    """
    Write the drop under data/plotus_briefs/{date}/. Returns (folder, brief_path).
    """
    folder = os.path.join(LOCAL_DROP_ROOT, date_iso)
    os.makedirs(folder, exist_ok=True)

    brief_path = os.path.join(folder, 'brief.md')
    data_path  = os.path.join(folder, 'data.json')

    with open(brief_path, 'w') as f:
        f.write(brief_md.rstrip() + '\n')
    with open(data_path, 'w') as f:
        json.dump(payload, f, indent=2, default=str)

    return folder, brief_path


def push_to_gdrive(local_folder: str, date_iso: str, timeout: int = 90) -> bool:
    """
    rclone copy `local_folder` → `GDRIVE_ROOT/{date}/`. Returns True on success.
    No-op (returns False with a printed warning) if rclone isn't on PATH.
    """
    remote = f"{GDRIVE_ROOT}/{date_iso}"
    try:
        result = subprocess.run(
            ['rclone', 'copy', local_folder, remote],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        print("  [plotus] rclone not installed — skipped Google Drive push")
        return False
    except subprocess.TimeoutExpired:
        print(f"  [plotus] rclone timed out after {timeout}s — drop saved locally only")
        return False

    if result.returncode != 0:
        print(f"  [plotus] rclone failed (exit {result.returncode}): {result.stderr.strip()}")
        return False

    print(f"  [plotus] pushed {local_folder} → {remote}")
    return True


def publish(date_iso: str, brief_md: str, payload: Mapping) -> bool:
    """Convenience: write the drop locally and push to Drive."""
    folder, _ = write_drop_locally(date_iso, brief_md, payload)
    return push_to_gdrive(folder, date_iso)
