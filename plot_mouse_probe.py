import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt


def load_events(path: Path):
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("events", [])


def main():
    parser = argparse.ArgumentParser(description="Plot dx/dy curves from a mouse probe JSON.")
    parser.add_argument("json_path", help="Path to mouse_path_probe_*.json")
    parser.add_argument("--out", help="Output PNG path")
    parser.add_argument("--max-points", type=int, default=0, help="Limit points for large files")
    args = parser.parse_args()

    json_path = Path(args.json_path)
    events = load_events(json_path)
    if not events:
        raise SystemExit("No events found in JSON.")

    dx = [ev.get("dx", 0) for ev in events]
    dy = [ev.get("dy", 0) for ev in events]
    ts = [ev.get("ts", idx) for idx, ev in enumerate(events)]

    if args.max_points and len(ts) > args.max_points:
        step = max(1, len(ts) // args.max_points)
        ts = ts[::step]
        dx = dx[::step]
        dy = dy[::step]

    out_path = Path(args.out) if args.out else json_path.with_suffix("")
    if out_path.suffix.lower() != ".png":
        out_path = out_path.with_suffix(".png")

    plt.figure(figsize=(12, 5))
    plt.plot(ts, dx, label="dx")
    plt.plot(ts, dy, label="dy")
    plt.title("Mouse dx/dy over time")
    plt.xlabel("timestamp")
    plt.ylabel("delta")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    print(f"Saved plot to {out_path}")


if __name__ == "__main__":
    main()
