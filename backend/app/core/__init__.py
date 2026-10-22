"""DNA Twin core: pure-Python simulation library. No web or database imports allowed here.

SIMULATION ONLY — nothing in this package synthesizes or sequences real DNA.
"""
SIMULATION_LABEL = "Simulation Result"
__version__ = "0.2.0"

from . import codecs  # noqa: E402,F401  (registers codecs)
