"""
ai_config.py - Global AI configuration for wc3-ai-pipeline.

All tick intervals and shared parameters in one place.
Modify values here to tune all AI modules.
"""

# Tick intervals (seconds)
TICK_SALVO          = 0.10    # Ranged salvo (concentrated fire)
TICK_HERO_MAGIC     = 0.10    # Hero magic (TC stomp, Shadow Hunter hex/heal)
TICK_FOCUS_RETREAT  = 0.10    # Focus-fire retreat (HP drop detection)
TICK_CREEP_CONTROL  = 0.10    # Creep last-hit / approach
TICK_SURROUND       = 0.10    # Surround / encircle

# Surround parameters (scale with TICK_SALVO since surround runs inside SalvoTick)
# DK speed ~270 units/sec, per-tick move = 270 * TICK_SALVO
# Still threshold: (per-tick-move)^2 = (270*0.1)^2 = 729 -> use ~100 (10 yard margin)
# Still ticks: 3 seconds / TICK_SALVO = 30
SURROUND_STILL_THRESHOLD = 100.0   # squared distance to consider target still
SURROUND_STILL_TICKS     = 30      # consecutive still ticks before switching to attack
