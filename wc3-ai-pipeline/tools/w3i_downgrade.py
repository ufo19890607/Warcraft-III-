#!/usr/bin/env python3
"""
Parse war3map.w3i and emit a v25 (1.27-compatible) version of it.

Reference: HiveWE / mdx-m3-viewer war3map.w3i format docs
- v18 = RoC
- v25 = TFT 1.07 (1.27 still uses this, 1.31 too)
- v28+ = Reforged additions
- v31  = Reforged later

Strategy:
  Read v31 sequentially, capturing the fields v25 also has.
  Drop the trailing v28+/v31-only fields (game data set, lua flag, supported modes, ...).
  Write back as a clean v25 file.

Notes:
  - All ints are little-endian uint32 unless stated.
  - Strings are NUL-terminated UTF-8.
"""

import struct, sys, io

def read_cstr(b: io.BytesIO) -> bytes:
    out = bytearray()
    while True:
        ch = b.read(1)
        if not ch:
            raise EOFError("unexpected EOF in cstr")
        if ch == b'\x00':
            break
        out += ch
    return bytes(out)

def write_cstr(o: io.BytesIO, s: bytes):
    o.write(s)
    o.write(b'\x00')

def u32(b): return struct.unpack('<I', b.read(4))[0]
def i32(b): return struct.unpack('<i', b.read(4))[0]
def f32(b): return struct.unpack('<f', b.read(4))[0]

def wu32(o, v): o.write(struct.pack('<I', v & 0xFFFFFFFF))
def wi32(o, v): o.write(struct.pack('<i', v))
def wf32(o, v): o.write(struct.pack('<f', v))

def parse_v31(data: bytes):
    b = io.BytesIO(data)
    info = {}
    info['version']           = u32(b)
    info['mapVersion']        = u32(b)
    info['editorVersion']     = u32(b)
    # v28+ adds: gameVersionMajor, Minor, Patch, Build (4 uint32)
    if info['version'] >= 28:
        info['gameVerMajor']  = u32(b)
        info['gameVerMinor']  = u32(b)
        info['gameVerPatch']  = u32(b)
        info['gameVerBuild']  = u32(b)
    info['mapName']           = read_cstr(b)
    info['mapAuthor']         = read_cstr(b)
    info['mapDescription']    = read_cstr(b)
    info['playersRecommended']= read_cstr(b)
    info['cameraBounds']      = [f32(b) for _ in range(8)]
    info['cameraComplements'] = [u32(b) for _ in range(4)]
    info['playableW']         = u32(b)
    info['playableH']         = u32(b)
    info['flags']             = u32(b)
    info['tileset']           = b.read(1)
    info['loadingScreenBg']   = u32(b)
    info['loadingScreenPath'] = read_cstr(b)
    info['loadingScreenText'] = read_cstr(b)
    info['loadingScreenTitle']= read_cstr(b)
    info['loadingScreenSub']  = read_cstr(b)
    info['gameDataSet']       = u32(b)  # v25+ TFT
    info['prologuePath']      = read_cstr(b)
    info['prologueText']      = read_cstr(b)
    info['prologueTitle']     = read_cstr(b)
    info['prologueSub']       = read_cstr(b)
    info['fogStyle']          = u32(b)
    info['fogStart']          = f32(b)
    info['fogEnd']            = f32(b)
    info['fogDensity']        = f32(b)
    info['fogColor']          = b.read(4)  # bgra
    info['weather']           = b.read(4)  # 4-char id, e.g. 'RAlr' or 0
    info['soundEnv']          = read_cstr(b)
    info['lightTileset']      = b.read(1)
    info['waterColor']        = b.read(4)  # bgra
    if info['version'] >= 28:
        info['scriptLang']    = u32(b)  # 0=jass, 1=lua
    if info['version'] >= 29:
        info['supportedModes']= u32(b)
    if info['version'] >= 30:
        info['gameDataVersion']= u32(b)
    if info['version'] >= 31:
        # v31+/v33 reforged adds extra uint32 fields between gameDataVersion and playerCount.
        # observed: v33 has 3 extra zero uint32 here. Read them as 'extraInts' until we hit
        # something that looks like playerCount (typically 0..24).
        # Conservative approach: read up to 4 extras, stop when we'd be reading a sane playerCount next.
        extras = []
        while len(extras) < 6:
            peek = struct.unpack_from('<I', b.getvalue(), b.tell())[0]
            if peek <= 24:
                # could be playerCount - peek next-next as id (uint), then type<=4, race<=4 sanity
                save = b.tell()
                pc = u32(b)
                ok = False
                if pc > 0 and pc <= 24:
                    p_id = struct.unpack_from('<I', b.getvalue(), b.tell())[0]
                    p_type = struct.unpack_from('<I', b.getvalue(), b.tell()+4)[0]
                    p_race = struct.unpack_from('<I', b.getvalue(), b.tell()+8)[0]
                    if p_id <= 24 and p_type <= 4 and p_race <= 8:
                        ok = True
                if ok:
                    info['playerCount'] = pc
                    break
                # not playerCount, treat as another extra
                b.seek(save)
                extras.append(u32(b))
            else:
                extras.append(u32(b))
        else:
            raise RuntimeError("could not locate playerCount in v31+ extras")
        info['_v31extras'] = extras
    else:
        info['playerCount']       = u32(b)
    info['players']           = []
    for _ in range(info['playerCount']):
        p = {}
        p['id']        = u32(b)
        p['type']      = u32(b)
        p['race']      = u32(b)
        p['fixedStart']= u32(b)
        p['name']      = read_cstr(b)
        p['startX']    = f32(b)
        p['startY']    = f32(b)
        p['allyPrioLow']  = u32(b)
        p['allyPrioHigh'] = u32(b)
        if info['version'] >= 28:
            p['enemyPrioLow']  = u32(b)
            p['enemyPrioHigh'] = u32(b)
        info['players'].append(p)

    info['forceCount']        = u32(b)
    info['forces']            = []
    for _ in range(info['forceCount']):
        f = {}
        f['flags']    = u32(b)
        f['playerMask']= u32(b)
        f['name']     = read_cstr(b)
        info['forces'].append(f)

    info['upgradeCount']      = u32(b)
    info['upgrades']          = []
    for _ in range(info['upgradeCount']):
        u = {
            'playerMask': u32(b),
            'upgradeId':  b.read(4),
            'level':      u32(b),
            'avail':      u32(b),
        }
        info['upgrades'].append(u)
    info['techCount']         = u32(b)
    info['techs']             = []
    for _ in range(info['techCount']):
        info['techs'].append({
            'playerMask': u32(b),
            'techId':     b.read(4),
        })
    info['rndUnitCount']      = u32(b)
    if info['rndUnitCount'] != 0:
        raise RuntimeError("random unit tables present - need full parser")
    info['rndItemCount']      = u32(b) if (b.tell() + 4 <= len(b.getvalue())) else 0
    if info['rndItemCount'] != 0:
        raise RuntimeError("random item tables present - need full parser")

    info['_tail_offset']      = b.tell()
    info['_remaining']        = b.read()
    return info


def write_v25(info) -> bytes:
    o = io.BytesIO()
    wu32(o, 25)
    wu32(o, info['mapVersion'])
    wu32(o, info['editorVersion'])
    write_cstr(o, info['mapName'])
    write_cstr(o, info['mapAuthor'])
    write_cstr(o, info['mapDescription'])
    write_cstr(o, info['playersRecommended'])
    for v in info['cameraBounds']: wf32(o, v)
    for v in info['cameraComplements']: wu32(o, v)
    wu32(o, info['playableW'])
    wu32(o, info['playableH'])
    # Mask out Reforged-only flag bits (0x4000=item_classification,
    # 0x8000=v25/Reforged-unknown, 0x10000=accurate_rng, 0x20000=abilities_skin)
    # 1.27 understands only the lower bits.
    wu32(o, info['flags'] & 0x3FFF)
    o.write(info['tileset'])
    wu32(o, info['loadingScreenBg'])
    write_cstr(o, info['loadingScreenPath'])
    write_cstr(o, info['loadingScreenText'])
    write_cstr(o, info['loadingScreenTitle'])
    write_cstr(o, info['loadingScreenSub'])
    wu32(o, info['gameDataSet'])
    write_cstr(o, info['prologuePath'])
    write_cstr(o, info['prologueText'])
    write_cstr(o, info['prologueTitle'])
    write_cstr(o, info['prologueSub'])
    wu32(o, info['fogStyle'])
    wf32(o, info['fogStart'])
    wf32(o, info['fogEnd'])
    wf32(o, info['fogDensity'])
    o.write(info['fogColor'])
    o.write(info['weather'])
    write_cstr(o, info['soundEnv'])
    o.write(info['lightTileset'])
    o.write(info['waterColor'])
    # NO scriptLang / supportedModes / gameDataVersion in v25

    wu32(o, info['playerCount'])
    for p in info['players']:
        wu32(o, p['id'])
        wu32(o, p['type'])
        wu32(o, p['race'])
        wu32(o, p['fixedStart'])
        write_cstr(o, p['name'])
        wf32(o, p['startX'])
        wf32(o, p['startY'])
        wu32(o, p['allyPrioLow'])
        wu32(o, p['allyPrioHigh'])
        # NO enemyPrio in v25

    wu32(o, info['forceCount'])
    for f in info['forces']:
        wu32(o, f['flags'])
        wu32(o, f['playerMask'])
        write_cstr(o, f['name'])

    wu32(o, info['upgradeCount'])
    for u in info['upgrades']:
        wu32(o, u['playerMask'])
        o.write(u['upgradeId'])
        wu32(o, u['level'])
        wu32(o, u['avail'])

    wu32(o, info['techCount'])
    for t in info['techs']:
        wu32(o, t['playerMask'])
        o.write(t['techId'])

    wu32(o, info['rndUnitCount'])  # 0
    wu32(o, info['rndItemCount'])  # 0

    return o.getvalue()


def main():
    inp = sys.argv[1]
    outp = sys.argv[2]
    data = open(inp, 'rb').read()
    info = parse_v31(data)
    print(f"Parsed w3i v{info['version']}, players={info['playerCount']}, forces={info['forceCount']}, upgrades={info['upgradeCount']}, techs={info['techCount']}")
    print(f"  tail consumed at offset {info['_tail_offset']}, remaining bytes = {len(info['_remaining'])}")
    print(f"  mapName={info['mapName']!r}")
    print(f"  tileset={info['tileset']!r}")
    out = write_v25(info)
    open(outp, 'wb').write(out)
    print(f"Wrote {outp} ({len(out)} bytes, original {len(data)})")

if __name__ == '__main__':
    main()
