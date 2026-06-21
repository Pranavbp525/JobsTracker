#!/usr/bin/env python3
"""Syntax-check the inline JavaScript in the static frontend.

The frontend is a single hand-written `frontend/index.html` with no build step,
so a typo in the embedded <script> can ship a blank page that no test would
otherwise catch. This pulls every inline <script> (skipping CDN tags with a
`src` and non-JS types like application/json) and runs `node --check` on each,
which validates syntax without executing anything.

Usage: python3 scripts/check_inline_js.py [path/to/index.html]
Exit code is non-zero if any block fails to parse.
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(HERE, os.pardir, "frontend", "index.html")

SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.IGNORECASE | re.DOTALL)


def is_checkable(attrs: str) -> bool:
    """Skip external scripts (src=...) and non-JS script types."""
    if re.search(r"\bsrc\s*=", attrs, re.IGNORECASE):
        return False
    m = re.search(r"""\btype\s*=\s*['"]?([^'"\s>]+)""", attrs, re.IGNORECASE)
    if m:
        t = m.group(1).lower()
        if t not in ("text/javascript", "application/javascript", "module"):
            return False
    return True


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    with open(path, encoding="utf-8") as f:
        html = f.read()

    blocks = [(a, b) for a, b in SCRIPT_RE.findall(html) if is_checkable(a) and b.strip()]
    if not blocks:
        print(f"No inline JS blocks found in {path}")
        return 0

    failures = 0
    for i, (_attrs, body) in enumerate(blocks, 1):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
            tmp.write(body)
            tmp_path = tmp.name
        try:
            proc = subprocess.run(
                ["node", "--check", tmp_path],
                capture_output=True, text=True,
            )
        finally:
            os.unlink(tmp_path)
        if proc.returncode == 0:
            print(f"  block {i}: OK ({body.count(chr(10)) + 1} lines)")
        else:
            failures += 1
            print(f"  block {i}: SYNTAX ERROR\n{proc.stderr}", file=sys.stderr)

    print(f"\nChecked {len(blocks)} inline JS block(s) in {path}: "
          f"{len(blocks) - failures} OK, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
