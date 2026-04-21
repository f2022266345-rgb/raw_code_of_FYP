import joblib
import numpy as np
import os

# Load the Scikit-Learn model and Encoders
try:
    model_path = os.path.join(os.path.dirname(__file__), 'student_model.pkl')
    encoder_path = os.path.join(os.path.dirname(__file__), 'encoders.pkl')
    
    student_model = joblib.load(model_path)
    encoders = joblib.load(encoder_path)
except Exception as e:
    print(f"Warning: ML Models not loaded. Using fallback logic. Error: {e}")
    student_model = None
    encoders = None


def _compute_language_barrier_risk(edu: dict, pref: dict) -> float:
    """
    Estimates language barrier risk [0.0 – 1.0] based on onboarding data.

    High risk indicators:
      - School taught in Urdu medium
      - English proficiency is beginner/elementary
      - Student's language preference is urdu-primary
      - Previous study medium was Urdu
    """
    risk = 0.2  # baseline

    school_type = edu.get("schoolType", "").lower()
    english_proficiency = edu.get("englishProficiency", "intermediate").lower()
    previous_mediums = edu.get("previousMedium", [])
    lang_preference = pref.get("languagePreference", "english-only").lower()

    if "urdu" in school_type or "religious" in school_type:
        risk += 0.35
    if english_proficiency in ("beginner", "elementary"):
        risk += 0.25
    elif english_proficiency == "intermediate":
        risk += 0.10
    if "urdu" in previous_mediums:
        risk += 0.15
    if lang_preference in ("urdu-primary", "bilingual"):
        risk += 0.10

    return round(min(risk, 1.0), 2)


def _compute_active_agents(stress_level: int, language_barrier_risk: float,
                           social_battery: str, culture: dict) -> list:
    """
    Determines which support agents should be activated for this student.
    Academic is always active. Others are triggered by risk thresholds.
    """
    agents = ["academic"]  # Always active

    # Wellness: high stress OR high language barrier
    if stress_level >= 6 or language_barrier_risk >= 0.6:
        agents.append("wellness")

    # Social: low social battery OR first-gen student
    if social_battery == "low" or culture.get("firstGenStudent", False):
        agents.append("social")

    # Coordinator always listed (it's the orchestrator)
    agents.append("coordinator")

    return agents


def predict_initial_profile(data_dict: dict) -> dict:
    edu = data_dict.get("educationalBackground", {})
    pref = data_dict.get("learningPreferences", {})
    culture = data_dict.get("culturalContext", {})
    diag = data_dict.get("diagnosticAssessment", {})

    # ── 1. Bloom Level (from diagnostic quiz) ──────────────────────────────────
    bloom_level = int(diag.get("bloomLevel", 1))
    bloom_level = max(1, min(6, bloom_level))  # clamp to valid range

    # ── 2. Language Barrier Risk ────────────────────────────────────────────────
    language_barrier_risk = _compute_language_barrier_risk(edu, pref)

    # ── 3. Map Education to Model Labels ───────────────────────────────────────
    school_type = edu.get("schoolType", "").lower()
    if "urdu" in school_type or "religious" in school_type:
        education_label = 2   # Lower qualification proxy
    elif "international" in school_type:
        education_label = 0   # A-level or equivalent
    else:
        education_label = 1   # Standard HE qualification

    # ── 4. Derive Academic Confidence (0–100) ──────────────────────────────────
    base_score = diag.get("assessmentScore", 50)
    academic_confidence = min(100, int(base_score) + (bloom_level * 5))

    # ── 5. Derive Stress Level (0–10) ──────────────────────────────────────────
    challenges = culture.get("challenges", [])
    stress_level = 3 + len(challenges)
    if culture.get("firstGenStudent"):
        stress_level += 1
    if language_barrier_risk >= 0.6:
        stress_level += 1
    stress_level = min(10, stress_level)

    # ── 6. Map Social Battery ───────────────────────────────────────────────────
    social_battery = "moderate"
    if "social" in challenges or "isolation" in challenges:
        social_battery = "low"
    elif culture.get("familySupport") == "very-strong" and stress_level < 5:
        social_battery = "full"

    # ── 7. Active Agents ────────────────────────────────────────────────────────
    active_agents = _compute_active_agents(
        stress_level, language_barrier_risk, social_battery, culture
    )

    # ── 8. Build Profile ────────────────────────────────────────────────────────
    profile = {
        "name": edu.get("fullName", "Student"),
        "major": edu.get("program", "General Studies"),
        "university": edu.get("university", "Unknown"),
        "stressLevel": stress_level,
        "currentPhase": "Foundation" if bloom_level <= 2 else "Developing" if bloom_level <= 4 else "Advanced",
        "academicConfidence": academic_confidence,
        "socialBattery": social_battery,
        "currentMood": "Determined" if stress_level < 6 else "Overwhelmed",
        "languagePreference": pref.get("languagePreference", "english-only"),
    }

    # ── 9. ML Prediction ────────────────────────────────────────────────────────
    success_probability = 0.5 + (academic_confidence / 200)  # heuristic fallback
    status = "At Risk"

    if student_model and encoders:
        try:
            gender_val = 1 if edu.get("gender", "M") == "M" else 0
            credits = edu.get("credits", 60)

            # Derive IMD band proxy (0=most deprived, 4=least)
            background = culture.get("background", "urban")
            imd_proxy = {"urban": 3, "semi-urban": 2, "rural": 1}.get(background, 2)

            # Age band proxy (0=young, 1=mature)
            age_band_proxy = 0

            # Disability proxy from challenges
            disability_proxy = 1 if "disability" in challenges else 0

            features = np.array([[
                gender_val,
                education_label,
                imd_proxy,
                age_band_proxy,
                disability_proxy,
                0,              # num_of_prev_attempts
                credits,
                academic_confidence,
                academic_confidence  # weighted_score proxy
            ]])

            success_probability = float(student_model.predict_proba(features)[0][1])
            status = "Pass" if success_probability > 0.5 else "At Risk"
        except Exception as exc:
            print(f"ML inference fallback: {exc}")

    return {
        "user_profile": profile,
        "ai_prediction": {
            "success_probability": round(success_probability, 2),
            "status": status,
        },
        "bloom_level": bloom_level,
        "language_barrier_risk": language_barrier_risk,
        "active_agents": active_agents,
    }