#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: ppm_to_bmp.py input.ppm output.bmp", file=sys.stderr)
        return 2
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    data = src.read_bytes()
    idx = 0

    def token() -> bytes:
        nonlocal idx
        while data[idx : idx + 1].isspace():
            idx += 1
        if data[idx : idx + 1] == b"#":
            while data[idx : idx + 1] not in (b"\n", b""):
                idx += 1
            return token()
        start = idx
        while idx < len(data) and not data[idx : idx + 1].isspace():
            idx += 1
        return data[start:idx]

    magic = token()
    width = int(token())
    height = int(token())
    max_value = int(token())
    while data[idx : idx + 1].isspace():
        idx += 1
    pixels = data[idx : idx + width * height * 3]
    if magic != b"P6" or max_value != 255 or len(pixels) < width * height * 3:
        raise SystemExit("unsupported PPM")

    row_size = ((width * 3 + 3) // 4) * 4
    pad = b"\0" * (row_size - width * 3)
    rows = []
    for y in range(height - 1, -1, -1):
        row = pixels[y * width * 3 : (y + 1) * width * 3]
        bgr = bytearray()
        for x in range(0, len(row), 3):
            bgr += bytes((row[x + 2], row[x + 1], row[x]))
        rows.append(bytes(bgr) + pad)
    body = b"".join(rows)

    header = bytearray()
    header += b"BM"
    header += (54 + len(body)).to_bytes(4, "little")
    header += (0).to_bytes(4, "little")
    header += (54).to_bytes(4, "little")
    header += (40).to_bytes(4, "little")
    header += width.to_bytes(4, "little")
    header += height.to_bytes(4, "little")
    header += (1).to_bytes(2, "little")
    header += (24).to_bytes(2, "little")
    header += (0).to_bytes(4, "little")
    header += len(body).to_bytes(4, "little")
    header += (2835).to_bytes(4, "little")
    header += (2835).to_bytes(4, "little")
    header += (0).to_bytes(4, "little")
    header += (0).to_bytes(4, "little")

    dst.write_bytes(header + body)
    print(f"{dst} {width}x{height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
