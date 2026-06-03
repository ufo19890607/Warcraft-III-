#!/usr/bin/env python3
"""
w3e_downgrade.py

Downgrade reforged .w3e (terrain) v12 -> v11 (1.27 compatible).

Format diff:
  v11 (1.27): 7 bytes per cell
      [B0..B3 = height/water] [B4 = flags(1 byte, has high bit 0x40 in low nibble)] [B5 = ground] [B6 = cliff/layer]
  v12 (reforged): 8 bytes per cell (flags expanded from 1 byte to 2 bytes)
      [B0..B3 = height/water] [B4 = flagsLow] [B5 = flagsHigh] [B6 = ground] [B7 = cliff/layer]

  Mapping: v11_B4 = (v12_B5 << 6) | v12_B4
  (verified empirically: v11 B4 distinct == set of (v12_B5<<6)|v12_B4 combos)

We rewrite each cell from 8 bytes (v12) to 7 bytes (v11) using the formula above
and rewrite the version field to 11.

usage: w3e_downgrade.py <input.w3e> <output.w3e>
"""
import struct
import sys


def downgrade_w3e(in_path: str, out_path: str):
    with open(in_path, 'rb') as f:
        d = f.read()

    if d[:4] != b'W3E!':
        raise SystemExit("not a w3e file")

    ver = struct.unpack_from('<I', d, 4)[0]
    if ver == 11:
        print(f"Already v11, copy as-is")
        with open(out_path, 'wb') as f:
            f.write(d)
        return
    if ver != 12:
        raise SystemExit(f"unsupported version {ver}")

    # parse header to find cells_offset
    nGround = struct.unpack_from('<I', d, 13)[0]
    pos = 17 + nGround * 4
    nCliff = struct.unpack_from('<I', d, pos)[0]
    pos += 4 + nCliff * 4
    w = struct.unpack_from('<I', d, pos)[0]
    h = struct.unpack_from('<I', d, pos + 4)[0]
    cells_offset = pos + 16
    n_cells = w * h

    out = bytearray()
    out += d[:4]                          # magic
    out += struct.pack('<I', 11)          # version = 11
    out += d[8:cells_offset]              # rest of header

    src_pos = cells_offset
    for i in range(n_cells):
        cell8 = d[src_pos:src_pos + 8]
        if len(cell8) < 8:
            print(f"WARN: truncated at cell #{i}", file=sys.stderr)
            break
        # v12 -> v11: combine flags low (B4) + high (B5) into v11 B4
        b4_lo = cell8[4]
        b5_hi = cell8[5]
        v11_b4 = ((b5_hi << 6) | b4_lo) & 0xFF
        out += bytes(cell8[0:4]) + bytes([v11_b4]) + bytes(cell8[6:8])
        src_pos += 8

    if src_pos < len(d):
        out += d[src_pos:]                # any trailing bytes (rare)

    with open(out_path, 'wb') as f:
        f.write(bytes(out))
    print(f"V12->V11: {in_path} ({len(d)} bytes) -> {out_path} ({len(out)} bytes), {n_cells} cells")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(64)
    downgrade_w3e(sys.argv[1], sys.argv[2])
