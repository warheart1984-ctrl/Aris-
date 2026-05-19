#!/usr/bin/env python3
"""Extract plain text from a .docx file."""
from __future__ import annotations

import re
import sys
import zipfile
import xml.etree.ElementTree as ET


def docx_text(path: str) -> str:
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    parts: list[str] = []
    for node in root.iter(w + "t"):
        if node.text:
            parts.append(node.text)
        if node.tail:
            parts.append(node.tail)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def main() -> None:
    path = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    text = docx_text(path)
    if limit > 0:
        print(text[:limit])
        if len(text) > limit:
            print(f"\n...[truncated, total {len(text)} chars]")
    else:
        print(text)


if __name__ == "__main__":
    main()
