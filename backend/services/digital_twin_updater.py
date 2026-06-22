"""
Real-time Digital Twin updater.
Called by the agent router after every student interaction to keep the
cognitive model in sync with observed behaviour.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bayesian Knowledge Tracing – single-step update
# ---------------------------------------------------------------------------

def _bkt_update(p_mastery: float, correct: bool,
                p_guess: float = 0.25, p_slip: float = 0.05,
                p_transit: float = 0.10) -> float:
    """One BKT posterior update; returns new p(mastery)."""
    if correct:
        p_evidence = p_mastery * (1 - p_slip) + (1 - p_mastery) * p_guess
    else:
        p_evidence = p_mastery * p_slip + (1 - p_mastery) * (1 - p_guess)

    if p_evidence < 1e-10:
        return p_mastery

    # Posterior
    if correct:
        posterior = (p_mastery * (1 - p_slip)) / p_evidence
    else:
        posterior = (p_mastery * p_slip) / p_evidence

    # Transit (learning step)
    return posterior + (1 - posterior) * p_transit


# ---------------------------------------------------------------------------
# DigitalTwinUpdater
# ---------------------------------------------------------------------------

class DigitalTwinUpdater:
    """Updates the digital twin tables after each learning interaction."""

    def __init__(self, db: Session):
        self.db = db

    # ── Public entry point ──────────────────────────────────────────────────

    def process_new_interaction(self, user_id: str, interaction: Dict[str, Any]) -> Dict[str, Any]:
        """
        Full pipeline:
          1. Log interaction
          2. Update BKT mastery
          3. Compute new cognitive state
          4. Assess affective state
          5. Run LSTM inference (if model available)
          6. Determine intervention
          7. Persist all updates
        """
        try:
            skill_id    = int(interaction.get("skill_id", 0))
            correct     = bool(interaction.get("correct", False))
            time_ms     = int(interaction.get("time_on_task_ms", 0))
            hints_used  = int(interaction.get("hints_used", 0))
            attempt_cnt = int(interaction.get("attempt_count", 1))
            mood        = interaction.get("mood")
            conf_before = float(interaction.get("confidence_before", 0.5))
            conf_after  = float(interaction.get("confidence_after", 0.5))

            self._log_interaction(user_id, interaction)
            new_mastery = self._update_bkt(user_id, skill_id, correct)
            cognitive   = self._compute_cognitive_state(user_id, correct, time_ms, hints_used)
            affective   = self._assess_affective_state(correct, conf_before, conf_after, mood)
            lstm_pred   = self._run_lstm_inference(user_id)
            intervention = self._determine_intervention(cognitive, affective, lstm_pred)
            self._persist_updates(user_id, cognitive, affective, lstm_pred, intervention)
            self.db.commit()

            return {
                "success": True,
                "new_mastery": round(new_mastery, 4),
                "cognitive_state": cognitive["state_label"],
                "intervention": intervention,
            }

        except Exception as exc:
            self.db.rollback()
            logger.error("DigitalTwinUpdater error for %s: %s", user_id, exc)
            return {"success": False, "error": str(exc)}

    # ── Step 1: Log interaction ─────────────────────────────────────────────

    def _log_interaction(self, user_id: str, interaction: Dict[str, Any]) -> None:
        self.db.execute(
            text("""
                INSERT INTO learning_interactions
                    (user_id, problem_id, skill_id, correct, time_on_task_ms,
                     hints_used, attempt_count, mood, confidence_before,
                     confidence_after, interaction_timestamp)
                VALUES (:uid, :pid, :sid, :corr, :ttms,
                        :hints, :att, :mood, :cb, :ca, NOW())
            """),
            {
                "uid":   user_id,
                "pid":   interaction.get("problem_id", 0),
                "sid":   interaction.get("skill_id", 0),
                "corr":  bool(interaction.get("correct", False)),
                "ttms":  interaction.get("time_on_task_ms", 0),
                "hints": interaction.get("hints_used", 0),
                "att":   interaction.get("attempt_count", 1),
                "mood":  interaction.get("mood"),
                "cb":    interaction.get("confidence_before", 0.5),
                "ca":    interaction.get("confidence_after", 0.5),
            },
        )

    # ── Step 2: BKT mastery update ──────────────────────────────────────────

    def _update_bkt(self, user_id: str, skill_id: int, correct: bool) -> float:
        row = self.db.execute(
            text("SELECT p_mastery, p_guess, p_slip, p_transit FROM skill_mastery "
                 "WHERE user_id = :uid AND skill_id = :sid"),
            {"uid": user_id, "sid": skill_id},
        ).fetchone()

        if row:
            p_mastery = float(row.p_mastery)
            p_guess   = float(row.p_guess)
            p_slip    = float(row.p_slip)
            p_transit = float(row.p_transit)
        else:
            p_mastery, p_guess, p_slip, p_transit = 0.2, 0.25, 0.05, 0.10

        new_mastery = _bkt_update(p_mastery, correct, p_guess, p_slip, p_transit)

        self.db.execute(
            text("""
                INSERT INTO skill_mastery
                    (user_id, skill_id, p_mastery, p_init, p_transit, p_guess, p_slip,
                     practice_count, correct_count, incorrect_count, last_practiced)
                VALUES (:uid, :sid, :pm, :p_init, :p_transit, :p_guess, :p_slip,
                     1, :cc, :ic, NOW())
                ON CONFLICT (user_id, skill_id) DO UPDATE SET
                    p_mastery       = :pm,
                    practice_count  = skill_mastery.practice_count + 1,
                    correct_count   = skill_mastery.correct_count + :cc,
                    incorrect_count = skill_mastery.incorrect_count + :ic,
                    last_practiced  = NOW()
            """),
            {
                "uid": user_id,
                "sid": skill_id,
                "pm":  new_mastery,
                # BKT priors — supplied explicitly because the columns are NOT NULL
                # and the ORM-level defaults don't apply to raw INSERTs.
                "p_init":    0.2,
                "p_transit": 0.1,
                "p_guess":   0.25,
                "p_slip":    0.05,
                "cc":  1 if correct else 0,
                "ic":  0 if correct else 1,
            },
        )
        return new_mastery

    # ── Step 3: Cognitive state ─────────────────────────────────────────────

    def _compute_cognitive_state(self, user_id: str, correct: bool,
                                 time_ms: int, hints_used: int) -> Dict[str, Any]:
        row = self.db.execute(
            text("""
                SELECT current_bloom_level, frustration_estimate,
                       motivation_index, cognitive_load_estimate, learning_velocity
                FROM cognitive_state WHERE user_id = :uid
            """),
            {"uid": user_id},
        ).fetchone()

        bloom        = int(row.current_bloom_level) if row else 1
        frustration  = float(row.frustration_estimate) if row else 0.3
        motivation   = float(row.motivation_index) if row else 0.7
        load         = float(row.cognitive_load_estimate) if row else 0.4
        velocity     = float(row.learning_velocity) if row else 0.0

        # Frustration heuristic: slow + many hints + wrong → more frustrated
        time_penalty = min(1.0, time_ms / 120_000) if time_ms > 0 else 0.0
        hint_penalty = min(1.0, hints_used * 0.15)
        frustration_delta = (0.15 * time_penalty + 0.15 * hint_penalty
                             - (0.12 if correct else 0.0))
        frustration = max(0.0, min(1.0, frustration + frustration_delta))

        # Motivation: rises on correct, falls on wrong
        motivation = max(0.1, min(1.0, motivation + (0.05 if correct else -0.03)))

        # Bloom: advance when mastery across skills is high and answer is correct
        avg_mastery_row = self.db.execute(
            text("SELECT AVG(p_mastery) FROM skill_mastery WHERE user_id = :uid"),
            {"uid": user_id},
        ).scalar() or 0.2

        if correct and float(avg_mastery_row) > 0.75 and bloom < 6:
            bloom += 1
        elif not correct and float(avg_mastery_row) < 0.25 and bloom > 1:
            bloom -= 1

        velocity = 0.6 * velocity + 0.4 * (1.0 if correct else 0.0)

        if frustration > 0.7 or motivation < 0.3:
            state_label = "critical_struggle"
        elif frustration < 0.2 and motivation > 0.75:
            state_label = "flow_state"
        elif velocity < 0.3:
            state_label = "disengaged"
        elif 0.4 < frustration < 0.7:
            state_label = "productive_struggle"
        else:
            state_label = "neutral"

        return {
            "bloom_level":      bloom,
            "frustration":      frustration,
            "motivation":       motivation,
            "cognitive_load":   load,
            "learning_velocity": velocity,
            "state_label":      state_label,
            "engagement": max(0.1, min(1.0, 0.5 + 0.3 * velocity - 0.2 * frustration)),
        }

    # ── Step 4: Affective state ─────────────────────────────────────────────

    def _assess_affective_state(self, correct: bool,
                                conf_before: float, conf_after: float,
                                mood: Optional[str]) -> Dict[str, Any]:
        stress_delta = 0.05 if not correct else -0.02
        if mood in ("stressed", "anxious", "overwhelmed"):
            stress_delta += 0.08
        elif mood in ("calm", "confident", "happy"):
            stress_delta -= 0.05

        conf_change = conf_after - conf_before
        return {
            "stress_delta":     stress_delta,
            "confidence_change": conf_change,
            "mood":             mood,
        }

    # ── Step 5: LSTM inference ──────────────────────────────────────────────

    def _run_lstm_inference(self, user_id: str) -> Dict[str, Any]:
        """Attempts LSTM prediction; returns heuristic baseline on failure."""
        try:
            import os
            import torch
            from models.cognitive_twin_lstm import CognitiveTwinLSTM

            model_path = os.path.join(os.path.dirname(__file__), "..", "safe_cognitive_twin.pth")
            if not os.path.exists(model_path):
                raise FileNotFoundError("LSTM model not found")

            interactions = self.db.execute(
                text("""
                    SELECT correct, time_on_task_ms, hints_used, attempt_count
                    FROM learning_interactions
                    WHERE user_id = :uid
                    ORDER BY interaction_timestamp DESC LIMIT 5
                """),
                {"uid": user_id},
            ).fetchall()

            if len(interactions) < 2:
                raise ValueError("Not enough interaction history for LSTM")

            rows = list(reversed(interactions))
            num_feats = torch.tensor([[
                [1.0 if r.correct else 0.0,
                 min(1.0, r.time_on_task_ms / 120_000),
                 min(1.0, r.hints_used / 5.0),
                 min(1.0, r.attempt_count / 3.0)]
                for r in rows
            ]], dtype=torch.float32)
            skill_ids = torch.zeros(1, len(rows), dtype=torch.long)

            model = CognitiveTwinLSTM(num_skills=200, skill_emb_dim=16, num_feats=4, hidden_size=64)
            model.load_state_dict(torch.load(model_path, map_location="cpu"))
            model.eval()
            with torch.no_grad():
                pred = model(num_feats, skill_ids).item()

            return {"predicted_correctness": pred, "source": "lstm"}

        except Exception as exc:
            logger.debug("LSTM inference skipped (%s); using heuristic", exc)
            return {"predicted_correctness": 0.5, "source": "heuristic"}

    # ── Step 6: Determine intervention ─────────────────────────────────────

    def _determine_intervention(self, cognitive: Dict[str, Any],
                                affective: Dict[str, Any],
                                lstm_pred: Dict[str, Any]) -> str:
        state   = cognitive["state_label"]
        pred    = lstm_pred.get("predicted_correctness", 0.5)
        frustration = cognitive["frustration"]

        if state == "critical_struggle" or frustration > 0.75:
            return "immediate_support"
        if pred < 0.35 or state == "disengaged":
            return "re_engage"
        if state == "productive_struggle":
            return "scaffold"
        if state == "flow_state" and pred > 0.75:
            return "advance_difficulty"
        return "continue"

    # ── Step 7: Persist updates ─────────────────────────────────────────────

    def _persist_updates(self, user_id: str, cognitive: Dict[str, Any],
                         affective: Dict[str, Any], lstm_pred: Dict[str, Any],
                         intervention: str) -> None:
        self.db.execute(
            text("""
                UPDATE cognitive_state SET
                    current_bloom_level    = :bloom,
                    frustration_estimate   = :frust,
                    motivation_index       = :mot,
                    engagement_level       = :eng_label,
                    cognitive_state        = :state,
                    learning_velocity      = :vel,
                    last_updated           = NOW()
                WHERE user_id = :uid
            """),
            {
                "uid":       user_id,
                "bloom":     cognitive["bloom_level"],
                "frust":     cognitive["frustration"],
                "mot":       cognitive["motivation"],
                "eng_label": "engaged" if cognitive["engagement"] > 0.5 else "disengaged",
                "state":     cognitive["state_label"],
                "vel":       cognitive["learning_velocity"],
            },
        )

        self.db.execute(
            text("""
                UPDATE wellness_state SET
                    stress_level_30d = LEAST(1.0, GREATEST(0.0,
                        stress_level_30d + :delta)),
                    updated_at = NOW()
                WHERE user_id = :uid
            """),
            {"uid": user_id, "delta": affective["stress_delta"]},
        )

        self.db.execute(
            text("""
                UPDATE digital_twin_predictions SET
                    predicted_next_problem_correctness = :pred,
                    recommended_agent_type             = :agent,
                    intervention_urgency               = :urgency,
                    prediction_timestamp               = NOW()
                WHERE user_id = :uid
            """),
            {
                "uid":     user_id,
                "pred":    lstm_pred.get("predicted_correctness", 0.5),
                "agent":   _intervention_to_agent(intervention),
                "urgency": "high" if intervention == "immediate_support" else "normal",
            },
        )


def _intervention_to_agent(intervention: str) -> str:
    return {
        "immediate_support": "wellness",
        "re_engage":         "coordinator",
        "scaffold":          "academic",
        "advance_difficulty": "academic",
    }.get(intervention, "coordinator")
