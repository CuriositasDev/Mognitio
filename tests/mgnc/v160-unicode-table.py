#!/usr/bin/env python3
"""Independently decode and check the compiler's complete Unicode table."""
import argparse
import hashlib
import re
from pathlib import Path

def verify(path):
    source = path.read_text(encoding="ascii")
    body = re.search(r"let pages:List<String>=List<String>\[\n(.*?)\];", source, re.S).group(1)
    literals = re.findall(r'"(?:\\.|[^"\\])*"', body)
    assert re.sub(r'"(?:\\.|[^"\\])*"', "", body).replace(",", "").strip() == ""
    assert len(literals) == 272
    value = 0
    digest = hashlib.sha256()
    count = 0
    for page, literal in enumerate(literals):
        def escape(match):
            spelling = match.group(0)
            if spelling.startswith("\\u{"):
                return chr(int(spelling[3:-1], 16))
            return {'\\"': '"', "\\\\": "\\"}[spelling]
        text = re.sub(r"\\u\{[0-9a-f]+\}|\\.", escape, literal[1:-1])
        assert len(text) == (2048 if page == 13 else 4096)
        for scalar in text:
            if value == 0xD800:
                value = 0xE000
            assert ord(scalar) == value, (page, count, value, ord(scalar))
            value += 1
            count += 1
        digest.update(text.encode("utf-8"))
    assert value == 0x110000 and count == 1112064
    print(f"V160_UNICODE_TABLE_OK pages=272 scalars={count} utf8_sha256={digest.hexdigest()}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    verify(parser.parse_args().path)
