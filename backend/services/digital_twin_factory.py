"""
Digital Twin Factory Service
Creates and updates student digital twins from interaction data.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class DigitalTwinFactory:
    """Creates and updates Digital Twins from interaction data."""

    def __init__(self, db_session: Session, lstm_model_path: str):
        self.db = db_session
        self.lstm_model = self._load_lstm_model(lstm_model_path)

    def _load_lstm_model(self, path: str):
        try:
            import torch
            from models.cognitive_twin_lstm import CognitiveTwinLSTM

            model = CognitiveTwinLSTM(
                num_skills=1005, skill_embed_dim=16, num_features=4, hidden_dim=64
            )
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            state = torch.load(path, map_location=device, weights_only=True)
            model.load_state_dict(state)
            model.to(device)
            model.eval()
            self._device = device
            logger.info("LSTM model loaded from %s", path)
            return model
        except Exception as exc:
            logger.warning("Could not load LSTM model (%s) — predictions will be heuristic.", exc)
            self._device = None
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_twin_from_interaction_data(
        self, user_id: str, interactions: List[Dict]
    ) -> Dict:
        """Create or refresh a Digital Twin from interaction records."""
        if len(interactions) < 5:
            return self._create_baseline_twin(user_id)

        cognitive = self._calculate_cognitive_state(interactions)
        bkt = self._estimate_bkt_mastery(interactions)
        affective = self._estimate_affective_state(interactions)
        lstm_preds = self._run_lstm_inference(interactions) if self.lstm_model else {}

        self._persist_twin_to_db(user_id, cognitive, bkt, affective, lstm_preds)
        return {
            "user_id": user_id,
            "cognitive_state": cognitive,
            "bkt_mastery": bkt,
            "affective_state": affective,
            "lstm_predictions": lstm_preds,
        }

    def create_twin_from_assistments_dataset(
        self, student_id: str, interactions_df: pd.DataFrame
    ) -> Optional[Dict]:
        """Create a Digital Twin from an ASSISTments parquet DataFrame."""
        interactions = interactions_df.to_dict("records")
        return self.create_twin_from_interaction_data(student_id, interactions)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_baseline_twin(self, user_id: str) -> Dict:
        try:
            self.db.execute(
                text("""
                    INSERT INTO cognitive_state
                        (user_id, current_bloom_level, cognitive_state, engagement_level,
                         frustration_estimate, motivation_index)
                    VALUES (:uid, 1, 'developing', 'engaged', 0.3, 0.7)
                    ON CONFLICT (user_id) DO NOTHING
                """),
                {"uid": user_id},
            )
            self.db.execute(
                text("""
                    INSERT INTO wellness_state (user_id, stress_level_30d)
                    VALUES (:uid, 0.3)
                    ON CONFLICT (user_id) DO NOTHING
                """),
                {"uid": user_id},
            )
            self.db.execute(
                text("""
                    INSERT INTO digital_twin_predictions
                        (user_id, predicted_next_problem_correctness, at_risk_probability)
                    VALUES (:uid, 0.5, 0.3)
                    ON CONFLICT (user_id) DO NOTHING
                """),
                {"uid": user_id},
            )
            self.db.commit()
            return {"user_id": user_id, "status": "baseline_created"}
        except Exception as exc:
            self.db.rollback()
            logger.error("Error creating baseline twin for %s: %s", user_id, exc)
            raise

    def _calculate_cognitive_state(self, interactions: List[Dict]) -> Dict:
        df = pd.DataFrame(interactions)
        recent = df.tail(20)

        accuracy = float(recent["correct"].mean()) if "correct" in recent.columns else 0.5
        avg_time = float(recent["time_on_task"].astype(float).mean()) if "time_on_task" in recent.columns else 120.0

        if accuracy > 0.75:
            state, engagement = "intelligent", "flow"
        elif accuracy < 0.4:
            state, engagement = "struggling", "frustrated"
        else:
            state, engagement = "developing", "engaged"

        bloom_level = min(6, max(1, int(2 + accuracy * 4)))
        hint_avg = float(df["hints_used"].mean()) if "hints_used" in df.columns else 0.0

        return {
            "current_bloom_level": bloom_level,
            "cognitive_state": state,
            "engagement_level": engagement,
            "accuracy_recent": accuracy,
            "frustration_estimate": round(1.0 - accuracy, 4),
            "motivation_index": round(1.0 - (0.2 if hint_avg > 0.5 else 0.0), 4),
            "cognitive_load_estimate": float(avg_time > 180),
        }

    def _estimate_bkt_mastery(self, interactions: List[Dict]) -> Dict:
        df = pd.DataFrame(interactions)
        if "skill_id" not in df.columns:
            return {}

        bkt: Dict[int, Dict] = {}
        for skill_id, grp in df.groupby("skill_id"):
            correct = int(grp["correct"].sum()) if "correct" in grp.columns else 0
            total = len(grp)
            bkt[int(skill_id)] = {
                "p_mastery": round(min(correct / total if total else 0.2, 0.95), 4),
                "correct_count": correct,
                "incorrect_count": total - correct,
                "practice_count": total,
            }
        return bkt

    def _estimate_affective_state(self, interactions: List[Dict]) -> Dict:
        df = pd.DataFrame(interactions)
        accuracy = float(df["correct"].mean()) if "correct" in df.columns else 0.5
        stress = round(min(1.0 - accuracy, 1.0), 4)
        return {
            "stress_level": stress,
            "anxiety_markers": [],
            "motivation": round(1.0 - stress, 4),
            "needs_intervention": stress > 0.5,
        }

    def _run_lstm_inference(self, interactions: List[Dict]) -> Dict:
        if not self.lstm_model:
            return {}

        import torch

        try:
            df = pd.DataFrame(interactions)
            if len(df) < 5:
                return {}

            required = ["time_on_task", "hints_used", "attempt_count", "cognitive_weight"]
            for col in required:
                if col not in df.columns:
                    df[col] = 0.0

            num_feats = df[required].values.astype(float)
            skills = df["skill_id"].values.astype(int) if "skill_id" in df.columns else np.zeros(len(df), dtype=int)

            max_len = 50
            if len(num_feats) < max_len:
                pad = max_len - len(num_feats)
                num_feats = np.pad(num_feats, ((0, pad), (0, 0)))
                skills = np.pad(skills, (0, pad))
            else:
                num_feats = num_feats[-max_len:]
                skills = skills[-max_len:]

            skills = np.clip(skills, 0, 1004)

            num_t = torch.tensor(num_feats, dtype=torch.float32).unsqueeze(0).to(self._device)
            sk_t = torch.tensor(skills, dtype=torch.int64).unsqueeze(0).to(self._device)

            with torch.no_grad():
                output = self.lstm_model(num_t, sk_t)
                probs = torch.sigmoid(output).cpu().numpy().flatten()

            last5 = probs[-5:]
            return {
                "predicted_correctness": float(np.mean(last5)),
                "trend": "improving" if probs[-1] > probs[0] else "declining",
                "confidence": 0.75,
                "at_risk": float(max(0.0, 0.6 - float(np.mean(last5)))),
            }
        except Exception as exc:
            logger.error("LSTM inference error: %s", exc)
            return {}

    def _persist_twin_to_db(
        self,
        user_id: str,
        cognitive: Dict,
        bkt: Dict,
        affective: Dict,
        lstm: Dict,
    ) -> None:
        try:
            self.db.execute(
                text("""
                    INSERT INTO cognitive_state
                        (user_id, current_bloom_level, cognitive_state, engagement_level,
                         frustration_estimate, motivation_index, last_updated)
                    VALUES (:uid, :bloom, :state, :eng, :frust, :motiv, NOW())
                    ON CONFLICT (user_id) DO UPDATE SET
                        current_bloom_level  = :bloom,
                        cognitive_state      = :state,
                        engagement_level     = :eng,
                        frustration_estimate = :frust,
                        motivation_index     = :motiv,
                        last_updated         = NOW()
                """),
                {
                    "uid": user_id,
                    "bloom": cognitive.get("current_bloom_level", 1),
                    "state": cognitive.get("cognitive_state", "developing"),
                    "eng": cognitive.get("engagement_level", "engaged"),
                    "frust": cognitive.get("frustration_estimate", 0.3),
                    "motiv": cognitive.get("motivation_index", 0.7),
                },
            )

            for skill_id, params in bkt.items():
                self.db.execute(
                    text("""
                        INSERT INTO skill_mastery
                            (user_id, skill_id, p_mastery, correct_count,
                             incorrect_count, practice_count, last_practiced)
                        VALUES (:uid, :sid, :pm, :cc, :ic, :pc, NOW())
                        ON CONFLICT (user_id, skill_id) DO UPDATE SET
                            p_mastery      = :pm,
                            correct_count  = :cc,
                            incorrect_count = :ic,
                            practice_count = :pc,
                            last_practiced = NOW()
                    """),
                    {
                        "uid": user_id,
                        "sid": skill_id,
                        "pm": params.get("p_mastery", 0.2),
                        "cc": params.get("correct_count", 0),
                        "ic": params.get("incorrect_count", 0),
                        "pc": params.get("practice_count", 0),
                    },
                )

            self.db.execute(
                text("""
                    INSERT INTO wellness_state (user_id, stress_level_30d, updated_at)
                    VALUES (:uid, :stress, NOW())
                    ON CONFLICT (user_id) DO UPDATE SET
                        stress_level_30d = :stress,
                        updated_at       = NOW()
                """),
                {"uid": user_id, "stress": affective.get("stress_level", 0.3)},
            )

            self.db.execute(
                text("""
                    INSERT INTO digital_twin_predictions
                        (user_id, predicted_next_problem_correctness,
                         at_risk_probability, confidence_score, prediction_timestamp)
                    VALUES (:uid, :corr, :risk, :conf, NOW())
                    ON CONFLICT (user_id) DO UPDATE SET
                        predicted_next_problem_correctness = :corr,
                        at_risk_probability                = :risk,
                        confidence_score                   = :conf,
                        prediction_timestamp               = NOW()
                """),
                {
                    "uid": user_id,
                    "corr": lstm.get("predicted_correctness", 0.5),
                    "risk": lstm.get("at_risk", 0.3),
                    "conf": lstm.get("confidence", 0.6),
                },
            )

            self.db.commit()
            logger.info("Digital twin persisted for %s", user_id)
        except Exception as exc:
            self.db.rollback()
            logger.error("Error persisting twin for %s: %s", user_id, exc)
            raise


# ------------------------------------------------------------------
# Pipeline helper for bulk ASSISTments processing
# ------------------------------------------------------------------

class AssistmentsDigitalTwinPipeline:
    """Bulk-creates Digital Twins from ASSISTments parquet files."""

    def __init__(self, db_session: Session, lstm_model_path: str):
        self.factory = DigitalTwinFactory(db_session, lstm_model_path)

    def process_all_assistments_files(
        self,
        input_folder: str,
        output_log: str = "failed_students.csv",
    ) -> Dict:
        folder = Path(input_folder)
        parquet_files = sorted(folder.glob("*.parquet"))

        if not parquet_files:
            logger.error("No parquet files found in %s", input_folder)
            return {"total_created": 0, "total_failed": 0, "success_rate": 0.0}

        created, failed = 0, []

        for idx, file_path in enumerate(parquet_files, 1):
            logger.info("[%d/%d] Processing %s", idx, len(parquet_files), file_path.name)
            try:
                df = pd.read_parquet(file_path)
                for student_id, student_df in df.groupby("student_id"):
                    try:
                        self.factory.create_twin_from_assistments_dataset(
                            str(student_id), student_df
                        )
                        created += 1
                        if created % 100 == 0:
                            logger.info("  Created %d twins so far", created)
                    except Exception as exc:
                        failed.append({"student_id": student_id, "error": str(exc)})
            except Exception as exc:
                logger.error("Error reading %s: %s", file_path.name, exc)

        if failed and output_log:
            pd.DataFrame(failed).to_csv(output_log, index=False)
            logger.info("Failed students written to %s", output_log)

        total = created + len(failed)
        return {
            "total_created": created,
            "total_failed": len(failed),
            "success_rate": created / total if total else 0.0,
        }
