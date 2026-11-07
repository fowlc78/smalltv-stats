"""Empaquette theme.json en .stheme (format STH1 de smalltv-mod, sans image)."""
import json
import struct
import sys
from pathlib import Path

src = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("theme.json"))
out = Path(sys.argv[2] if len(sys.argv) > 2 else src.with_name("avinathan-stats.stheme"))
manifest = json.loads(src.read_text(encoding="utf-8"))
payload = json.dumps(manifest, separators=(",", ":"), ensure_ascii=True).encode()
assert len(payload) <= 16384 and len(manifest["layers"]) <= 32
path = b"theme.json"
data = b"STH1" + struct.pack("<HH", 1, 0) + struct.pack("<HI", len(path), len(payload)) + path + payload
out.write_bytes(data)
print(out, len(data), "octets")
