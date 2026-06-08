"""AirLine — gesture-directed, scene-aware cinematography layer on top of SideLine.

Day 1 scope: prove the validated SideLine CV core is reachable, intact, and
isolated. AirLine *imports and calls* SideLine code through a single seam
(`core_bridge`); it never edits the CV core.
"""

__version__ = "0.1.0"
