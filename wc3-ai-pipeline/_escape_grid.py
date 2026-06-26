#!/usr/bin/env python3
"""
_escape_grid.py - Tree grid generation helper for inject_ai_escape.py
Reads war3map.doo, builds boolean grid, generates JASS init code.
"""
import struct, io, math

CELL = 128
X_MIN = -5600.0
Y_MIN = -3000.0
X_MAX = 5600.0
Y_MAX = 2500.0
COLS = math.ceil((X_MAX - X_MIN) / CELL)  # 88
ROWS = math.ceil((Y_MAX - Y_MIN) / CELL)  # 43


def read_trees_from_doo(doo_path):
    """Read tree positions from war3map.doo (Reforged v8 format)."""
    data = open(doo_path, "rb").read()
    b = io.BytesIO(data)
    b.read(4)  # W3do
    b.read(4)  # version
    b.read(4)  # subversion
    n = struct.unpack("<I", b.read(4))[0]
    trees = []
    for i in range(n):
        typeId = b.read(4).decode("ascii", errors="replace")
        b.read(4)  # variation
        x, y, z = struct.unpack("<3f", b.read(12))
        b.read(4)   # rotation
        b.read(12)  # scale
        b.read(4)   # skinId
        b.read(1)   # flags
        b.read(1)   # life
        b.read(4)   # itemTable
        b.read(4)   # dropsCount
        b.read(4)   # editorId
        if typeId == "LTlt":
            trees.append((x, y))
    return trees


def build_grid(trees):
    """Build boolean grid marking tree cells (with 1-cell margin)."""
    grid = set()
    for tx, ty in trees:
        col = int((tx - X_MIN) / CELL)
        row = int((ty - Y_MIN) / CELL)
        for dc in range(-1, 2):
            for dr in range(-1, 2):
                c = col + dc
                r = row + dr
                if 0 <= c < COLS and 0 <= r < ROWS:
                    grid.add(c * ROWS + r)
    return sorted(grid)


def gen_grid_init_jass(grid_cells):
    """Generate chunked JASS functions to initialize tree grid."""
    CHUNK = 200
    chunks = []
    for ci in range(0, len(grid_cells), CHUNK):
        chunk = grid_cells[ci:ci+CHUNK]
        fn_name = f"Trig_AIML_GridInit_{ci // CHUNK}"
        lines = [f"function {fn_name} takes nothing returns nothing"]
        for idx in chunk:
            lines.append(f"    set udg_esc_TreeGrid[{idx}] = true")
        lines.append("endfunction")
        chunks.append("\n".join(lines))

    num_chunks = len(chunks)
    master = ["function Trig_AIML_TreeGridInit takes nothing returns nothing"]
    for ci in range(num_chunks):
        master.append(f"    call Trig_AIML_GridInit_{ci}()")
    master.append("endfunction")

    return "\n\n".join(chunks) + "\n\n" + "\n".join(master)
