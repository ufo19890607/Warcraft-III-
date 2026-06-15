"""
ai_config.py - Global AI configuration for wc3-ai-pipeline.

All tick intervals and shared parameters in one place.
Modify values here to tune all AI modules.
"""

# Tick intervals (seconds)
TICK_SALVO          = 0.50    # Ranged salvo + focus retreat (shared SalvoTick)
TICK_HERO_MAGIC     = 0.10    # Hero magic (TC stomp, Shadow Hunter hex/heal)
TICK_CREEP_CONTROL  = 0.10    # Creep last-hit (independent timer)
TICK_SURROUND       = 0.10    # Surround / encircle (independent timer)

# Surround still-detection parameters (must match TICK_SURROUND)
# DK speed ~270 units/sec, per-tick move at 0.1s = 27 units, 27^2 = 729
# Use threshold < per-tick-move^2 so moving target is not still
# 10 yard threshold: 10^2 = 100 (target must move < 10 yards to be still)
# Total still time = SURROUND_STILL_TICKS * TICK_SURROUND = 30 * 0.1 = 3.0s
SURROUND_STILL_THRESHOLD = 100.0    # squared distance per tick
SURROUND_STILL_TICKS     = 30       # ticks before attack mode
