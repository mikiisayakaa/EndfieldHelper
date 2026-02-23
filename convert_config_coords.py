from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_WIDTH = 2560
BASE_HEIGHT = 1600
CONFIG_DIR = Path("configs")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _convert_coord(value: Any, max_value: int) -> tuple[Any, bool]:
    if not _is_number(value):
        return value, False
    numeric = float(value)
    if numeric <= 1.0:
        return value, False
    return round(numeric / max_value, 6), True


def _convert_event(event: dict) -> bool:
    changed = False
    event_type = event.get("type")
    if event_type in {"click", "hold"}:
        new_x, changed_x = _convert_coord(event.get("x"), BASE_WIDTH)
        new_y, changed_y = _convert_coord(event.get("y"), BASE_HEIGHT)
        if changed_x:
            event["x"] = new_x
        if changed_y:
            event["y"] = new_y
        changed = changed or changed_x or changed_y
    elif event_type == "drag":
        new_start_x, changed_start_x = _convert_coord(event.get("start_x"), BASE_WIDTH)
        new_start_y, changed_start_y = _convert_coord(event.get("start_y"), BASE_HEIGHT)
        new_end_x, changed_end_x = _convert_coord(event.get("end_x"), BASE_WIDTH)
        new_end_y, changed_end_y = _convert_coord(event.get("end_y"), BASE_HEIGHT)
        if changed_start_x:
            event["start_x"] = new_start_x
        if changed_start_y:
            event["start_y"] = new_start_y
        if changed_end_x:
            event["end_x"] = new_end_x
        if changed_end_y:
            event["end_y"] = new_end_y
        changed = changed or changed_start_x or changed_start_y or changed_end_x or changed_end_y
    return changed


def _walk_node(node: Any) -> bool:
    changed = False
    if isinstance(node, dict):
        changed = _convert_event(node) or changed
        for value in node.values():
            changed = _walk_node(value) or changed
    elif isinstance(node, list):
        for item in node:
            changed = _walk_node(item) or changed
    return changed


def _process_file(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Skip {path}: {exc}")
        return False

    changed = _walk_node(data)
    if changed:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return changed


def main() -> int:
    if not CONFIG_DIR.exists():
        print(f"Config directory not found: {CONFIG_DIR}")
        return 1

    changed_files = 0
    total_files = 0
    for path in CONFIG_DIR.rglob("*.json"):
        total_files += 1
        if _process_file(path):
            changed_files += 1

    print(f"Processed {total_files} JSON files, updated {changed_files} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
