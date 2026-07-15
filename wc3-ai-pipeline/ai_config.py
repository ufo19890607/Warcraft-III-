"""
ai_config.py - Global AI configuration for wc3-ai-pipeline.

All tick intervals and shared parameters in one place.
Modify values here to tune all AI modules.
"""

# Tick intervals (seconds)
TICK_SALVO          = 0.50    # Ranged salvo + focus retreat + Spirit Walker spells (shared SalvoTick)
TICK_HERO_MAGIC     = 0.10    # Hero magic (TC stomp, Shadow Hunter hex/heal)
TICK_CREEP_CONTROL  = 0.30    # Creep last-hit (independent timer)
TICK_SURROUND       = 0.30    # Surround / encircle (independent timer)

# Surround still-detection parameters (must match TICK_SURROUND)
# DK speed ~270 units/sec, per-tick move at 0.3s = 81 units, 81^2 = 6561
# Still threshold: 30 yards -> 30^2 = 900 (target must move < 30 yards to be 'still')
# Total still time = SURROUND_STILL_TICKS * TICK_SURROUND = 10 * 0.3 = 3.0s
SURROUND_STILL_THRESHOLD = 900.0    # squared distance per tick
SURROUND_STILL_TICKS     = 10       # ticks before attack mode
