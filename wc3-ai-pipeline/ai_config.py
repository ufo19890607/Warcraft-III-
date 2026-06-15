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
