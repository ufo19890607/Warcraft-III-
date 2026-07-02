#!/usr/bin/env python3
"""
Analyze WC3 Body-Block CSV Logs

Usage:
  python3 analyze_block_log.py <log_directory> [output_directory]

  <log_directory>    Path containing data_*.txt files (Preload logs)
  [output_directory] Output directory for the chart (default: same as input)

Output:
  <output>/block_analysis.png — 6-panel analysis chart
"""

import sys, os, re, glob
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from collections import defaultdict

# ─── Parse ────────────────────────────────────────────────────────────────

def parse_log_dir(directory):
    """Parse all data_*.txt files from a Preload log directory.
    Returns list of (tick, bx, by, tx, ty, facing, dist, blockX, blockY, side, result)
    """
    rows = []
    files = sorted(glob.glob(os.path.join(directory, "data_*.txt")),
                   key=lambda x: int(re.search(r'data_(\d+)', x).group(1)))
    for fpath in files:
        with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
            raw = f.read()
        for m in re.finditer(r'call Preload\(\s*"(.+?)"\s*\)', raw):
            parts = m.group(1).strip().split(',')
            if len(parts) < 6:
                continue
            try:
                tick   = int(parts[0])
                bx     = float(parts[1])
                by     = float(parts[2])
                tx     = float(parts[3])
                ty     = float(parts[4])
                facing = float(parts[5])
                dist   = float(parts[6])
            except (ValueError, IndexError):
                continue
            result = parts[10] if len(parts) >= 11 else "UNK"
            if result in ("MOVE", "HOLD") and len(parts) >= 10:
                blockX = float(parts[7])
                blockY = float(parts[8])
                side   = float(parts[9])
            else:
                blockX = blockY = side = 0.0
            rows.append((tick, bx, by, tx, ty, facing, dist, blockX, blockY, side, result))
    return rows, len(files)


def compute_stats(rows):
    """Compute summary statistics."""
    move_rows = [r for r in rows if r[10] in ("MOVE", "HOLD")]
    far_rows  = [r for r in rows if r[10] == "FAR"]
    hold_rows = [r for r in rows if r[10] == "HOLD"]

    dists = [r[6] for r in move_rows]
    n = len(move_rows)

    far = len(far_rows)
    move = len(move_rows) - len(hold_rows)
    hold = len(hold_rows)
    total = len(rows)

    if not dists:
        return None

    avg_dist       = sum(dists) / len(dists)
    min_dist       = min(dists)
    max_dist       = max(dists)
    under_100      = sum(1 for d in dists if d < 100)
    under_150      = sum(1 for d in dists if d < 150)
    pct_150        = under_150 / len(dists) * 100

    # L20: skip first 20 MOVE ticks
    l20_dists = [r[6] for r in move_rows[20:]] if len(move_rows) > 20 else dists
    l20 = sum(l20_dists) / len(l20_dists)

    # Stuck ticks (blocker barely moved between consecutive MOVE ticks)
    stuck = 0
    for i in range(1, len(move_rows)):
        dx = abs(move_rows[i][1] - move_rows[i-1][1])
        dy = abs(move_rows[i][2] - move_rows[i-1][2])
        if dx < 2 and dy < 2:
            stuck += 1

    # Segment stability
    segments = []
    for s in range(0, len(move_rows), 20):
        seg = move_rows[s:s+20]
        if seg:
            segments.append(sum(r[6] for r in seg) / len(seg))
    seg_std = (sum((x - sum(segments)/len(segments))**2 for x in segments) / len(segments)) ** 0.5 if len(segments) > 1 else 0

    # Duration
    duration_s = (rows[-1][0] - rows[0][0]) * 0.15

    far_to_move_tick = None
    for i, r in enumerate(rows):
        if i > 0 and rows[i-1][10] == "FAR" and r[10] in ("MOVE", "HOLD"):
            far_to_move_tick = r[0]
            break

    return {
        "total": total, "far": far, "move": move, "hold": hold,
        "tick_range": (rows[0][0], rows[-1][0]),
        "duration_s": duration_s,
        "avg_dist": avg_dist, "min_dist": min_dist, "max_dist": max_dist,
        "under_100": under_100, "under_150": under_150, "pct_150": pct_150,
        "l20": l20, "stuck": stuck, "seg_std": seg_std,
        "far_to_move_tick": far_to_move_tick,
        "n_files": None,  # filled by caller
    }


# ─── Chart ─────────────────────────────────────────────────────────────────

def make_chart(rows, stats_obj, output_path, title_label=None):
    """Generate 6-panel analysis chart."""
    move_rows = [r for r in rows if r[10] in ("MOVE", "HOLD")]
    dists     = [r[6] for r in move_rows]

    ticks   = [r[0] for r in move_rows]
    bx_vals = [r[1] for r in move_rows]
    by_vals = [r[2] for r in move_rows]
    tx_vals = [r[3] for r in move_rows]
    ty_vals = [r[4] for r in move_rows]
    facing  = [r[5] for r in move_rows]
    bX_vals = [r[7] for r in move_rows]
    bY_vals = [r[8] for r in move_rows]
    side    = [r[9] for r in move_rows]

    s = stats_obj

    fig, axes = plt.subplots(2, 3, figsize=(20, 12))
    title_str = f"WC3 Body-Block Analysis"
    if title_label:
        title_str += f" — {title_label}"
    fig.suptitle(title_str, fontsize=14, fontweight='bold')

    # ── Panel 1: Distance Over Time ──
    ax = axes[0][0]
    ax.plot(range(len(dists)), dists, 'b-', linewidth=0.6)
    ax.axhline(y=100, color='green', linestyle='--', alpha=0.5, label='dist=100')
    ax.axhline(y=200, color='orange', linestyle='--', alpha=0.5, label='dist=200')
    ax.axhline(y=s['avg_dist'], color='red', linestyle=':', alpha=0.6,
               label=f'avg={s["avg_dist"]:.0f}')
    ax.set_xlabel('MOVE Tick Index')
    ax.set_ylabel('Distance (units)')
    ax.set_title(f'Distance Over Time\n'
                 f'total={s["total"]} ticks, MOVE={s["move"]}, HOLD={s["hold"]}, '
                 f'avg={s["avg_dist"]:.0f}, <%150={s["pct_150"]:.0f}%')
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    # ── Panel 2: Movement Trajectory ──
    ax = axes[0][1]
    ax.plot(tx_vals, ty_vals, 'r-', linewidth=0.8, alpha=0.6)
    ax.plot(bx_vals, by_vals, 'b-', linewidth=0.8, alpha=0.6)
    # Block points every 15 ticks
    ax.scatter(bX_vals[::15], bY_vals[::15], c='purple', s=4, alpha=0.3,
               label='Block Point')
    # Mark start points
    ax.scatter(tx_vals[0], ty_vals[0], c='darkred', s=50, marker='o', zorder=5)
    ax.scatter(bx_vals[0], by_vals[0], c='darkblue', s=50, marker='o', zorder=5)
    ax.text(tx_vals[0], ty_vals[0], ' DK start', fontsize=7, color='darkred', va='bottom')
    ax.text(bx_vals[0], by_vals[0], ' FS start', fontsize=7, color='darkblue', va='bottom')

    ax.set_title('Movement Trajectory')
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.grid(True, alpha=0.3)
    ax.set_aspect('equal')
    # Color legend — red=Target(DK), blue=Blocker(FS), purple=Block Point
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    custom_lines = [
        Line2D([0], [0], color='red',   lw=2, label='Target (DK)'),
        Line2D([0], [0], color='blue',  lw=2, label='Blocker (FS)'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='purple',
               markersize=6, label='Move Order (Block Point)'),
    ]
    ax.legend(handles=custom_lines, fontsize=8, loc='upper right')

    # ── Panel 3: Distance Distribution Histogram ──
    ax = axes[0][2]
    counts, bins, patches = ax.hist(dists, bins=30, color='steelblue',
                                     edgecolor='white', alpha=0.8)
    # Color bars by threshold
    for i, patch in enumerate(patches):
        bin_center = (bins[i] + bins[i+1]) / 2
        if bin_center < 100:
            patch.set_facecolor('green')
            patch.set_alpha(0.6)
        elif bin_center < 200:
            patch.set_facecolor('orange')
            patch.set_alpha(0.6)
        else:
            patch.set_facecolor('red')
            patch.set_alpha(0.5)
    ax.axvline(x=100, color='green', linestyle='--', alpha=0.7, label='dist=100')
    ax.axvline(x=200, color='orange', linestyle='--', alpha=0.7, label='dist=200')
    ax.axvline(x=s['avg_dist'], color='red', linestyle=':', alpha=0.8,
               label=f'avg={s["avg_dist"]:.0f}')
    ax.set_xlabel('Distance (units)')
    ax.set_ylabel('Frequency')
    ax.set_title(f'Distance Distribution\n'
                 f'<100: {s["under_100"]} ({s["under_100"]/len(dists)*100:.0f}%)  '
                 f'<150: {s["under_150"]} ({s["pct_150"]:.0f}%)')
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3, axis='y')

    # ── Panel 4: DK Facing ──
    ax = axes[1][0]
    ax.plot(range(len(facing)), facing, 'g-', linewidth=0.4)
    ax.set_xlabel('MOVE Tick Index')
    ax.set_ylabel('Facing (degrees)')
    ax.set_title('DK Facing Over Time')
    ax.grid(True, alpha=0.3)

    # ── Panel 5: S-Turn Side Toggle Pattern ──
    ax = axes[1][1]
    show_n = min(200, len(side))
    ax.plot(range(show_n), side[:show_n], 'm-', linewidth=0.7)
    ax.axhline(y=0, color='gray', linestyle='-', alpha=0.3)
    ax.set_xlabel('MOVE Tick Index')
    ax.set_ylabel('Side (+1 left / -1 right)')
    ax.set_title(f'S-Turn Pattern (first {show_n} ticks)')
    ax.grid(True, alpha=0.3)

    # ── Panel 6: Segment Distance Stability ──
    ax = axes[1][2]
    seg_avgs = []
    seg_labels = []
    for s_idx in range(0, len(move_rows), 20):
        seg = move_rows[s_idx:s_idx+20]
        if seg:
            seg_avgs.append(sum(r[6] for r in seg) / len(seg))
            seg_labels.append(f'{seg[0][0]}')

    if seg_avgs:
        ax.bar(range(len(seg_avgs)), seg_avgs,
               color=['green' if v < 150 else 'orange' if v < 200 else 'red'
                      for v in seg_avgs],
               alpha=0.7, edgecolor='white')
        ax.axhline(y=150, color='green', linestyle='--', alpha=0.5)
        ax.axhline(y=200, color='orange', linestyle='--', alpha=0.5)
        ax.set_xlabel('Segment (20-tick blocks, labeled by start tick)')
        ax.set_ylabel('Avg Distance')
        ax.set_title(f'Segment Stability (std={s["seg_std"]:.0f})')
        ax.grid(True, alpha=0.3, axis='y')

    # ── Top banner: key metrics (below title) ──
    banner = (f"AvgD: {s['avg_dist']:.0f}  |  L20: {s['l20']:.0f}  |  min: {s['min_dist']:.0f}  max: {s['max_dist']:.0f}  |  "
              f"<150: {s['under_150']}/{s['move']+s['hold']} ({s['pct_150']:.0f}%)  |  "
              f"Duration: {s['duration_s']:.1f}s  |  FAR→MOVE: tick {s['far_to_move_tick']}")
    fig.text(0.5, 0.95, banner, ha='center', va='top', fontsize=9,
             family='monospace', fontweight='bold',
             bbox=dict(boxstyle='round,pad=0.4', facecolor='#2c3e50',
                       edgecolor='#1a252f', alpha=0.9),
             color='white')

    # ── Bottom summary text ──
    summary_lines = [
        f"Ticks: {s['tick_range'][0]} → {s['tick_range'][1]}  |  Files: {s['n_files']}  |  FAR: {s['far']}  MOVE: {s['move']}  HOLD: {s['hold']}  |  stuck: {s['stuck']}  seg_std: {s['seg_std']:.0f}",
    ]
    summary = "\n".join(summary_lines)
    fig.text(0.5, 0.005, summary, ha='center', va='bottom', fontsize=7,
             family='monospace', color='#666')

    plt.tight_layout(rect=[0, 0.04, 1, 0.96])
    # Save both SVG (vector) and PNG
    svg_path = output_path.replace('.png', '.svg')
    plt.savefig(svg_path, format='svg', bbox_inches='tight')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Chart saved → {svg_path}")
    print(f"Chart saved → {output_path}")


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    log_dir = sys.argv[1]
    if not os.path.isdir(log_dir):
        print(f"ERROR: not a directory: {log_dir}")
        sys.exit(1)

    out_dir = sys.argv[2] if len(sys.argv) >= 3 else log_dir
    os.makedirs(out_dir, exist_ok=True)

    rows, n_files = parse_log_dir(log_dir)
    if not rows:
        print("ERROR: no data found in", log_dir)
        sys.exit(1)

    stats_obj = compute_stats(rows)
    if stats_obj is None:
        print("ERROR: no MOVE data found")
        sys.exit(1)

    stats_obj['n_files'] = n_files

    # Print summary
    s = stats_obj
    print(f"╔═════════════════════════════╗")
    print(f"║  WC3 Body-Block Analysis   ║")
    print(f"╠═════════════════════════════╣")
    print(f"║ Ticks: {s['tick_range'][0]} → {s['tick_range'][1]}  ({s['duration_s']:.1f}s)")
    print(f"║ Files: {s['n_files']}  FAR: {s['far']}  MOVE: {s['move']}  HOLD: {s['hold']}")
    print(f"║ avg dist: {s['avg_dist']:.0f}  min: {s['min_dist']:.0f}  max: {s['max_dist']:.0f}")
    print(f"║ L20: {s['l20']:.0f}  <100: {s['under_100']}  <150: {s['under_150']} ({s['pct_150']:.0f}%)")
    print(f"║ stuck: {s['stuck']}  seg_std: {s['seg_std']:.0f}")
    print(f"╚═════════════════════════════╝")

    title = os.path.basename(os.path.abspath(log_dir))
    out_path = os.path.join(out_dir, "block_analysis.png")
    make_chart(rows, stats_obj, out_path, title_label=title)


if __name__ == "__main__":
    main()
