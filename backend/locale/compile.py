"""Compile locale/*/LC_MESSAGES/django.po to .mo without GNU gettext (stdlib only).

Handles the subset our override catalogue uses: single-line msgid/msgstr, plurals and the header.
Run from backend/: python locale/compile.py
"""
import ast
import struct
import sys
from pathlib import Path


def parse(path):
    entries, current, key = {}, {}, None
    for raw in [*path.read_text(encoding="utf-8").splitlines(), ""]:
        line = raw.strip()
        if not line or line.startswith("#"):
            if "msgid" in current:
                singular = current["msgid"]
                if "msgid_plural" in current:
                    msgid = f"{singular}\0{current['msgid_plural']}"
                    forms = [current[k] for k in sorted(k for k in current if k.startswith("msgstr["))]
                    entries[msgid] = "\0".join(forms)
                else:
                    entries[singular] = current.get("msgstr", "")
            current, key = {}, None
            continue
        if line.startswith('"'):
            current[key] += ast.literal_eval(line)
            continue
        key, _, value = line.partition(" ")
        current[key] = ast.literal_eval(value)
    return entries


def write_mo(entries, path):
    keys = sorted(entries)
    ids = b"".join(key.encode() + b"\0" for key in keys)
    strs = b"".join(entries[key].encode() + b"\0" for key in keys)
    start = 7 * 4 + 16 * len(keys)
    offsets, offset = [], 0
    for key in keys:
        offsets.append((len(key.encode()), start + offset))
        offset += len(key.encode()) + 1
    value_start, value_offsets, offset = start + len(ids), [], 0
    for key in keys:
        value_offsets.append((len(entries[key].encode()), value_start + offset))
        offset += len(entries[key].encode()) + 1
    header = struct.pack("Iiiiiii", 0x950412DE, 0, len(keys), 7 * 4, 7 * 4 + 8 * len(keys), 0, 0)
    table = b"".join(struct.pack("ii", *pair) for pair in offsets + value_offsets)
    path.write_bytes(header + table + ids + strs)


def compiled(po_path):
    out = po_path.with_suffix(".mo")
    write_mo(parse(po_path), out)
    return out


if __name__ == "__main__":
    for po in sorted(Path(__file__).parent.glob("*/LC_MESSAGES/*.po")):
        print("compiled", compiled(po))
    sys.exit(0)
