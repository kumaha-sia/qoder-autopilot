"""
Captcha module — Slider puzzle CAPTCHA solver.
"""

from .slider import SliderSolver, ManualSolver
from .manual import wait_for_manual_solve

__all__ = ["SliderSolver", "ManualSolver", "wait_for_manual_solve"]
