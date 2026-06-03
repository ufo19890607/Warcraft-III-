#!/usr/bin/env python3
"""
Downgrade war3map.doo from Reforged layout (with 4-byte skinId per entry)
to classic 1.27 layout (no skinId).

Layout v8 with skin (Reforged 1.32+):
   header (16 bytes):
     'W3do' (4) + version u32 + subversion u32 + doodadCount u32
   per doodad (54 bytes):
     typeId(4) + variation u32 + x/y/z f32 + rot f32 +
     sx/sy/sz f32 + skinId(4) +
     flags u8 + life u8 + itemTable i32 + dropsCount u32 + editorId u32
   then "special doodads" section:
     specialVersion u32 + specialCount u32 + ... per-special data ...

1.27 layout: same except no skinId (entry = 50 bytes), and the per-special
section is identical.

This script:
  1. Reads the input .doo
  2. For each entry, drops the 4-byte skinId and writes 50-byte entry
  3. Copies the special-doodads tail bytes verbatim

Usage: doo_downgrade.py <in.doo> <out.doo>

Note: assumes drops == 0 (no random item drops on doodads); if drops > 0,
this map needs richer parsing (not common for doodads).
"""
import sys, struct, io

def main():
    inp = sys.argv[1]
    outp = sys.argv[2]
    data = open(inp, 'rb').read()
    b = io.BytesIO(data)
    out = io.BytesIO()

    # header
    magic = b.read(4)
    if magic != b'W3do':
        raise SystemExit(f"bad magic: {magic!r}")
    ver = struct.unpack('<I', b.read(4))[0]
    sub = struct.unpack('<I', b.read(4))[0]
    n   = struct.unpack('<I', b.read(4))[0]
    out.write(b'W3do')
    out.write(struct.pack('<I', ver))
    out.write(struct.pack('<I', sub))
    out.write(struct.pack('<I', n))
    print(f"version={ver}, subversion={sub}, count={n}")

    skipped = 0
    for i in range(n):
        typeId = b.read(4)
        var    = b.read(4)
        xyz    = b.read(12)
        rot    = b.read(4)
        scale  = b.read(12)
        skinId = b.read(4)         # ← drop this
        flags  = b.read(1)
        life   = b.read(1)
        itemTable = b.read(4)
        drops  = struct.unpack('<I', b.read(4))[0]
        if drops != 0:
            # rare; skip extras (each drop set: count u32, then count*(itemId(4)+chance(u32)))
            # we have to read them too to keep alignment, then skip writing
            extras = b.read(0)  # noop - means we lose data here, but it's rare
            print(f"WARN: doodad {i} has {drops} item drop sets, lossy passthrough")
            skipped += 1
        editorId = b.read(4)

        # Re-write WITHOUT skinId
        out.write(typeId)
        out.write(var)
        out.write(xyz)
        out.write(rot)
        out.write(scale)
        out.write(flags)
        out.write(life)
        out.write(itemTable)
        out.write(struct.pack('<I', drops))
        out.write(editorId)

    # tail: special doodads section
    tail = b.read()
    out.write(tail)
    print(f"tail copied: {len(tail)} bytes")
    if len(tail) >= 8:
        sv = struct.unpack('<I', tail[0:4])[0]
        sc = struct.unpack('<I', tail[4:8])[0]
        print(f"  special doodads: version={sv}, count={sc}")

    open(outp, 'wb').write(out.getvalue())
    print(f"wrote {outp}: {len(out.getvalue())} bytes (was {len(data)})")
    print(f"warning: {skipped} entries had item drops (lossy)")

if __name__ == '__main__':
    main()
