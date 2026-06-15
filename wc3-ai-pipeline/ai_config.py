"""
ai_config.py - Global AI configuration for wc3-ai-pipeline.

All tick intervals and shared parameters in one place.
Modify values here to tune all AI modules.
"""

# Tick intervals (seconds)
# SalvoTick drives: salvo + creep control + focus retreat + surround
TICK_SALVO          = 0.50    # Ranged salvo — 0.5s avoids interrupting attack animations
TICK_HERO_MAGIC     = 0.10    # Hero magic (TC stomp, Shadow Hunter hex/heal) — fast response

# Surround still-detection (scaled to TICK_SALVO)
# DK speed ~270 units/sec, per-tick move = 270 * 0.5 = 135
# Still threshold: 50 yards -> 50^2 = 2500
# Still ticks: 3 seconds / 0.5 = 6
SURROUND_STILL_THRESHOLD = 2500.0   # squared distance to consider target still
SURROUND_STILL_TICKS     = 6        # consecutive still ticks before switching to attack
