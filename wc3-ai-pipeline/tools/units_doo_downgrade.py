#!/usr/bin/env python3
"""
Downgrade war3mapUnits.doo from Reforged layout to 1.27 layout.

Two changes per unit:
  1. Drop the 4-byte skinId that Reforged adds after scaleZ.
  2. If randomFlag == 0xFFFFFFFF (-1, "no random unit", Reforged sentinel),
     rewrite as randomFlag = 0 (use map-default) followed by 4 zero bytes
     (1.27 expects 4 trailing bytes after rf=0: 3 bytes level + 1 byte class).

Layout being read (Reforged sub=11, with skin):
  typeId(4) variation u32 pos(12 f) rot f
  scale(12 f) skinId(4)
  flags u8 owner u32 unk u8 unk u8
  hp i32 mp i32 itemTblId i32 itemSets u32
  per-set: count u32, count*(itemId(4)+chance u32)
  gold u32 targetAcq f heroLvl u32 hStr/Agi/Int u32
  inv u32, inv*(slot u32 + itemId(4))
  abi u32, abi*(abilityId(4) + autocast u32 + level u32)
  randomFlag u32 + variable trailing:
    0xFFFFFFFF -> 0 trailing bytes  (Reforged: no random)
    0           -> 4 trailing bytes (level/class)
    1           -> 8 trailing bytes
    2           -> u32 count + count*(typeId(4)+chance u32)
  customColor i32 waygate i32 creationNumber u32
"""
import sys, struct, io

def main():
    inp = sys.argv[1]; outp = sys.argv[2]
    data = open(inp, 'rb').read()
    b = io.BytesIO(data)
    out = io.BytesIO()
    magic = b.read(4); ver = struct.unpack('<I', b.read(4))[0]
    sub = struct.unpack('<I', b.read(4))[0]; n = struct.unpack('<I', b.read(4))[0]
    out.write(magic); out.write(struct.pack('<I', ver))
    out.write(struct.pack('<I', sub)); out.write(struct.pack('<I', n))
    print(f"version={ver} sub={sub} units={n}")

    fixed_rf_count = 0
    for i in range(n):
        # Read fixed prefix
        typeId = b.read(4)
        var = b.read(4)
        pos = b.read(12)
        rot = b.read(4)
        scale = b.read(12)
        skinId = b.read(4)   # drop on write

        # mid-section
        flags = b.read(1)
        owner = b.read(4)
        unk = b.read(2)
        hp = b.read(4); mp = b.read(4); itemTbl = b.read(4)
        sets_n = struct.unpack('<I', b.read(4))[0]
        sets_buf = bytearray()
        for _ in range(sets_n):
            cnt_b = b.read(4); cnt = struct.unpack('<I', cnt_b)[0]
            sets_buf += cnt_b
            sets_buf += b.read(8 * cnt)

        gold = b.read(4); ta = b.read(4); heroLvl = b.read(4)
        hAttr = b.read(12)
        inv_n = struct.unpack('<I', b.read(4))[0]
        inv_buf = b.read(8 * inv_n)
        abi_n = struct.unpack('<I', b.read(4))[0]
        abi_buf = b.read(12 * abi_n)
        rf = struct.unpack('<I', b.read(4))[0]

        # rewrite rf
        if rf == 0xFFFFFFFF:
            new_rf = 0
            new_rf_data = b'\x00\x00\x00\x00'  # default (no random pick)
            fixed_rf_count += 1
        elif rf == 0:
            new_rf = 0
            new_rf_data = b.read(4)
        elif rf == 1:
            new_rf = 1
            new_rf_data = b.read(8)
        elif rf == 2:
            cnt = struct.unpack('<I', b.read(4))[0]
            payload = b.read(8 * cnt)
            new_rf = 2
            new_rf_data = struct.pack('<I', cnt) + payload
        else:
            raise SystemExit(f"unit {i}: unknown rf {rf}")

        cc = b.read(4); wg = b.read(4); cr = b.read(4)

        # Write WITHOUT skinId
        out.write(typeId); out.write(var); out.write(pos); out.write(rot); out.write(scale)
        out.write(flags); out.write(owner); out.write(unk)
        out.write(hp); out.write(mp); out.write(itemTbl)
        out.write(struct.pack('<I', sets_n)); out.write(bytes(sets_buf))
        out.write(gold); out.write(ta); out.write(heroLvl); out.write(hAttr)
        out.write(struct.pack('<I', inv_n)); out.write(inv_buf)
        out.write(struct.pack('<I', abi_n)); out.write(abi_buf)
        out.write(struct.pack('<I', new_rf)); out.write(new_rf_data)
        out.write(cc); out.write(wg); out.write(cr)

    open(outp, 'wb').write(out.getvalue())
    print(f"wrote {outp}: {len(out.getvalue())} bytes (was {len(data)})")
    print(f"fixed {fixed_rf_count} 'no-random' sentinels (-1 -> 0+default)")

if __name__ == '__main__':
    main()
