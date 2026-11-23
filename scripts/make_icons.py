"""Draw the AnyVideo icon (blue rounded square with a white download arrow) as PNGs.

Pure standard library, so anyone can regenerate the icons:  python scripts/make_icons.py
"""

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLUE = (91, 140, 255)
WHITE = (255, 255, 255)


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _coverage(x, y):
    """Return (alpha of square, alpha of arrow) at a point in a 24x24 design space."""
    r = 6.0
    qx, qy = max(abs(x - 12) - (12 - r), 0), max(abs(y - 12) - (12 - r), 0)
    in_square = (qx * qx + qy * qy) ** 0.5 <= r
    w = 1.0  # half stroke width (the design uses a 2px stroke)
    strokes = [(12, 6, 12, 14), (12, 14, 8.5, 10.5), (12, 14, 15.5, 10.5), (7, 18, 17, 18)]
    on_arrow = any(_seg_dist(x, y, *s) <= w for s in strokes)
    return in_square, on_arrow


def render(size: int) -> bytes:
    ss = 4  # supersampling for smooth edges
    rows = []
    for py in range(size):
        row = bytearray([0])  # PNG filter type 0
        for px in range(size):
            sq = ar = 0
            for sy in range(ss):
                for sx in range(ss):
                    x = (px + (sx + 0.5) / ss) * 24 / size
                    y = (py + (sy + 0.5) / ss) * 24 / size
                    a, b = _coverage(x, y)
                    sq += a
                    ar += a and b
            n = ss * ss
            alpha = sq / n
            mix = ar / sq if sq else 0
            color = [round(BLUE[i] * (1 - mix) + WHITE[i] * mix) for i in range(3)]
            row += bytes(color + [round(alpha * 255)])
        rows.append(bytes(row))
    raw = zlib.compress(b"".join(rows), 9)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


TARGETS = {
    ".claude-plugin/icon.png": 512,
    "extension/icons/icon16.png": 16,
    "extension/icons/icon32.png": 32,
    "extension/icons/icon48.png": 48,
    "extension/icons/icon128.png": 128,
    "docs/icon-512.png": 512,
}

if __name__ == "__main__":
    for rel, size in TARGETS.items():
        out = ROOT / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(render(size))
        print(f"wrote {rel} ({size}x{size})")
