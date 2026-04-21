"""
services/trend_engine.py
------------------------
Heuristic Trend Analyzer for the AI Tutoring System.

Analyses a short sliding window (5-7 entries) of a student's recent interaction
signals — frustration, accuracy, and boredom — and returns a single string that
classifies their current cognitive / emotional state.

Exported API
------------
    calculate_slope(values)      -> "INCREASING" | "DECREASING" | "STABLE"
    analyze_student_state(...)   -> "CRITICAL_STRUGGLE" | "FLOW_STATE"
                                    | "DISENGAGED" | "PRODUCTIVE_STRUGGLE"
                                    | "NEUTRAL"
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Slope thresholds — tuned for a 5-7 step window normalised in [0, 1] / [0, 100]
_SLOPE_INCREASING_THRESHOLD: float = 0.05
_SLOPE_DECREASING_THRESHOLD: float = -0.05

# Minimum window size required for a meaningful linear fit
_MIN_WINDOW_SIZE: int = 3

# Cognitive state labels
STATE_CRITICAL_STRUGGLE: str = "CRITICAL_STRUGGLE"
STATE_FLOW: str = "FLOW_STATE"
STATE_DISENGAGED: str = "DISENGAGED"
STATE_PRODUCTIVE_STRUGGLE: str = "PRODUCTIVE_STRUGGLE"
STATE_NEUTRAL: str = "NEUTRAL"


# ---------------------------------------------------------------------------
# Helper: slope classifier
# ---------------------------------------------------------------------------

def calculate_slope(values: List[float]) -> str:
    """
    Fits a 1st-degree polynomial (linear regression) to *values* and classifies
    the resulting slope direction.

    Args:
        values: A list of numeric observations ordered oldest → newest.
                Typically 5-7 readings from the sliding interaction window.

    Returns:
        "INCREASING"  if slope >  _SLOPE_INCREASING_THRESHOLD
        "DECREASING"  if slope < _SLOPE_DECREASING_THRESHOLD
        "STABLE"      otherwise

    Edge cases:
        - Fewer than _MIN_WINDOW_SIZE (3) items → "STABLE" (insufficient data).
        - All identical values (zero variance) → "STABLE".
        - Any numpy error → "STABLE" (fail-safe).
    """
    if len(values) < _MIN_WINDOW_SIZE:
        logger.debug(
            "calculate_slope: only %d value(s) provided (need ≥ %d) — returning STABLE.",
            len(values),
            _MIN_WINDOW_SIZE,
        )
        return "STABLE"

    try:
        x = np.arange(len(values), dtype=float)
        y = np.array(values, dtype=float)

        # polyfit returns [slope, intercept] for degree=1
        slope, _ = np.polyfit(x, y, deg=1)

        if slope > _SLOPE_INCREASING_THRESHOLD:
            return "INCREASING"
        if slope < _SLOPE_DECREASING_THRESHOLD:
            return "DECREASING"
        return "STABLE"

    except Exception as exc:  # noqa: BLE001
        logger.warning("calculate_slope: numpy error (%s) — defaulting to STABLE.", exc)
        return "STABLE"


# ---------------------------------------------------------------------------
# Main analyser
# ---------------------------------------------------------------------------

def analyze_student_state(
    recent_frustration: List[float],
    recent_accuracy: List[int],
    recent_boredom: List[float],
) -> str:
    """
    Determines the student's overall cognitive / emotional state by applying
    priority-ordered heuristic rules to the trend of three signals.

    Signal descriptions
    -------------------
    recent_frustration : float values in [0.0, 1.0]
        Higher = more frustrated (e.g. from the student model's affective output).
    recent_accuracy    : int / float values — typically 0 (wrong) or 1 (correct),
        or a rolling accuracy percentage in [0, 100].
    recent_boredom     : float values in [0.0, 1.0]
        Higher = more bored / disengaged.

    Rules (evaluated in priority order)
    ------------------------------------
    1. CRITICAL_STRUGGLE   — Frustration INCREASING  AND Accuracy DECREASING
    2. FLOW_STATE          — Frustration STABLE/DECREASING AND Accuracy STABLE/INCREASING
    3. DISENGAGED          — Boredom INCREASING AND Accuracy DECREASING
    4. PRODUCTIVE_STRUGGLE — Frustration INCREASING AND Accuracy STABLE/INCREASING
    5. NEUTRAL             — default fallback

    Args:
        recent_frustration : Sliding window of frustration scores (5-7 entries).
        recent_accuracy    : Sliding window of accuracy scores   (5-7 entries).
        recent_boredom     : Sliding window of boredom scores    (5-7 entries).

    Returns:
        A string state label (see constants at top of file).
    """
    frustration_trend = calculate_slope(recent_frustration)
    accuracy_trend    = calculate_slope([float(a) for a in recent_accuracy])
    boredom_trend     = calculate_slope(recent_boredom)

    logger.debug(
        "Trends → frustration=%s, accuracy=%s, boredom=%s",
        frustration_trend,
        accuracy_trend,
        boredom_trend,
    )

    # ── Rule 1: CRITICAL_STRUGGLE ──────────────────────────────────────────
    # Student is getting more frustrated AND doing worse — highest priority.
    if frustration_trend == "INCREASING" and accuracy_trend == "DECREASING":
        return STATE_CRITICAL_STRUGGLE

    # ── Rule 2: FLOW_STATE ────────────────────────────────────────────────
    # Student is calm/relaxing AND holding or improving accuracy — ideal state.
    if (
        frustration_trend in ("STABLE", "DECREASING")
        and accuracy_trend in ("STABLE", "INCREASING")
    ):
        return STATE_FLOW

    # ── Rule 3: DISENGAGED ────────────────────────────────────────────────
    # Student is growing bored AND accuracy is slipping — check after flow so
    # a low-frustration, high-accuracy student isn't mislabelled as disengaged.
    if boredom_trend == "INCREASING" and accuracy_trend == "DECREASING":
        return STATE_DISENGAGED

    # ── Rule 4: PRODUCTIVE_STRUGGLE ───────────────────────────────────────
    # Student is frustrated but still performing — they are working hard.
    if (
        frustration_trend == "INCREASING"
        and accuracy_trend in ("STABLE", "INCREASING")
    ):
        return STATE_PRODUCTIVE_STRUGGLE

    # ── Rule 5: NEUTRAL (default) ─────────────────────────────────────────
    return STATE_NEUTRAL
