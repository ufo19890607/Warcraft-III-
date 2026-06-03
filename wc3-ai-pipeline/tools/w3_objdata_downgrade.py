#!/usr/bin/env python3
"""
w3_objdata_downgrade.py

Downgrade reforged-format object data files (.w3a/.w3h/.w3q/.w3u/.w3t/.w3b/.w3d)
from version 3 to version 2 (1.27 compatible).

Format diff (v3 -> v2):
  Each entry has TWO sections (original mods + custom new units).
  v2 entry: old_id | new_id | modCount | [mod_id, type, value, end_marker]*N
  v3 entry: old_id | new_id | uint32_A | uint32_B | modCount | [mod_id, type, value, end_marker]*N
  
  v3 inserts 2 extra uint32 fields between new_id and modCount.
  These are likely "version" or "set count" fields specific to reforged.
  We discard them since v2 doesn't have them.

usage: w3_objdata_downgrade.py <input> <output>
"""
import struct
import sys
import io


def read_cstr(b: io.BytesIO) -> bytes:
    out = bytearray()
    while True:
        c = b.read(1)
        if not c:
            raise EOFError()
        if c == b'\x00':
            break
        out += c
    return bytes(out)


def downgrade_section(src: io.BytesIO, dst: io.BytesIO, section_label: str):
    """Process one section (original mods or custom units), v3 -> v2."""
    n_bytes = src.read(4)
    if len(n_bytes) < 4:
        print(f"  WARN: {section_label} ran out at start", file=sys.stderr)
        return
    n = struct.unpack('<I', n_bytes)[0]
    dst.write(n_bytes)
    print(f"  {section_label}: {n} entries", file=sys.stderr)
    for i in range(n):
        # entry header: old_id (4) + new_id (4)
        old_id = src.read(4)
        new_id = src.read(4)
        if len(old_id) < 4 or len(new_id) < 4:
            print(f"  ERROR: entry #{i} truncated header", file=sys.stderr)
            raise EOFError(f"truncated at entry {i}")
        dst.write(old_id)
        dst.write(new_id)
        # v3 has 2 extra uint32 here -- DISCARD
        extra_a = src.read(4)
        extra_b = src.read(4)
        # mod count
        mod_count_bytes = src.read(4)
        if len(mod_count_bytes) < 4:
            raise EOFError(f"truncated mod count at entry {i}")
        mod_count = struct.unpack('<I', mod_count_bytes)[0]
        dst.write(mod_count_bytes)
        for j in range(mod_count):
            # mod_id (4)
            mod_id = src.read(4)
            dst.write(mod_id)
            # mod_type (4)
            mod_type_bytes = src.read(4)
            mod_type = struct.unpack('<I', mod_type_bytes)[0]
            dst.write(mod_type_bytes)
            # level (only for some object types -- abilities/upgrades have level + dataPointer)
            # For UNITS (.w3u) there is NO level/dataPointer
            # We need to know object type. Pass it separately.
            # Actually wait -- looking at v17 .w3u parsing earlier:
            # mod was: id|type|value|end_marker (no level/dataPointer)
            # OK so for .w3u this is right
            # value
            if mod_type == 0:
                v = src.read(4)
                dst.write(v)
            elif mod_type == 1 or mod_type == 2:
                v = src.read(4)
                dst.write(v)
            elif mod_type == 3:
                # cstr
                buf = bytearray()
                while True:
                    c = src.read(1)
                    if not c:
                        raise EOFError()
                    buf += c
                    if c == b'\x00':
                        break
                dst.write(bytes(buf))
            else:
                print(f"  ERROR: entry #{i} mod #{j} unknown type {mod_type}", file=sys.stderr)
                raise RuntimeError(f"bad mod_type {mod_type}")
            # end marker
            em = src.read(4)
            dst.write(em)


def downgrade_section_with_level(src: io.BytesIO, dst: io.BytesIO, section_label: str):
    """For .w3a (abilities), .w3q (upgrades), .w3d (doodads), .w3b (destructables) --
    each modification has additional level + dataPointer uint32 fields after type."""
    n_bytes = src.read(4)
    if len(n_bytes) < 4:
        return
    n = struct.unpack('<I', n_bytes)[0]
    dst.write(n_bytes)
    print(f"  {section_label}: {n} entries", file=sys.stderr)
    for i in range(n):
        old_id = src.read(4)
        new_id = src.read(4)
        dst.write(old_id)
        dst.write(new_id)
        # discard 2 v3 extras
        src.read(4)
        src.read(4)
        mc = src.read(4)
        mod_count = struct.unpack('<I', mc)[0]
        dst.write(mc)
        for j in range(mod_count):
            mod_id = src.read(4)
            dst.write(mod_id)
            mt = src.read(4)
            mod_type = struct.unpack('<I', mt)[0]
            dst.write(mt)
            # level + dataPointer (8 bytes total)
            level = src.read(4)
            dst.write(level)
            dataPtr = src.read(4)
            dst.write(dataPtr)
            if mod_type in (0, 1, 2):
                v = src.read(4)
                dst.write(v)
            elif mod_type == 3:
                buf = bytearray()
                while True:
                    c = src.read(1)
                    if not c:
                        raise EOFError()
                    buf += c
                    if c == b'\x00':
                        break
                dst.write(bytes(buf))
            else:
                raise RuntimeError(f"entry #{i} mod #{j}: bad mod_type {mod_type}")
            em = src.read(4)
            dst.write(em)


def downgrade(in_path: str, out_path: str):
    with open(in_path, "rb") as f:
        data = f.read()

    src = io.BytesIO(data)
    ver = struct.unpack('<I', src.read(4))[0]
    if ver != 3:
        print(f"WARN: not v3 (got v{ver}), copying as-is")
        with open(out_path, "wb") as f:
            f.write(data)
        return

    dst = io.BytesIO()
    dst.write(struct.pack('<I', 2))  # write version 2

    # Detect file type from extension
    ext = in_path.lower().rsplit('.', 1)[-1]
    has_level = ext in ('w3a', 'w3q', 'w3d', 'w3b')  # abilities, upgrades, doodads, destructables

    if has_level:
        # original mods section
        downgrade_section_with_level(src, dst, "original")
        # custom section (only if there are remaining bytes)
        if src.tell() < len(data):
            downgrade_section_with_level(src, dst, "custom")
    else:
        downgrade_section(src, dst, "original")
        if src.tell() < len(data):
            downgrade_section(src, dst, "custom")

    out = dst.getvalue()
    with open(out_path, "wb") as f:
        f.write(out)
    print(f"OK: {in_path} ({len(data)} bytes v3) -> {out_path} ({len(out)} bytes v2)")
    if src.tell() < len(data):
        print(f"  WARN: {len(data) - src.tell()} unconsumed bytes at end of input")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(64)
    downgrade(sys.argv[1], sys.argv[2])
