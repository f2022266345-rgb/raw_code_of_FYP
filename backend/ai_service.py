import joblib
import numpy as np
import os

# Load the Scikit-Learn model and Encoders
# Ensure these files are in the same directory as ai_service.py
try:
    model_path = os.path.join(os.path.dirname(__file__), 'student_model.pkl')
    encoder_path = os.path.join(os.path.dirname(__file__), 'encoders.pkl')
    
    student_model = joblib.load(model_path)
    encoders = joblib.load(encoder_path)
except Exception as e:
    print(f"Warning: ML Models not loaded. Using fallback logic. Error: {e}")
    student_model = None
    encoders = None

def predict_initial_profile(data_dict: dict) -> dict:
    edu = data_dict.get("educationalBackground", {})
    pref = data_dict.get("learningPreferences", {})
    culture = data_dict.get("culturalContext", {})
    diag = data_dict.get("diagnosticAssessment", {})

    # 1. Map Education to Model Labels
    # Mapping based on your training: HE Qualification (1), A Level (0), etc.
    # We'll default to HE Qualification (1) for degree programs like BSCS
    education_label = 1 
    if "private-urdu" in edu.get("schoolType", "").lower():
        education_label = 2 # Lower Than A Level proxy
    
    # 2. Derive Academic Confidence (0-100)
    # Using the diagnostic score + bloom level as a base
    base_score = diag.get("assessmentScore", 50)
    academic_confidence = min(100, base_score + (diag.get("bloomLevel", 1) * 5))

    # 3. Derive Stress Level (0-10)
    challenges = culture.get("challenges", [])
    stress_level = 4 + len(challenges)
    if culture.get("firstGenStudent"): 
        stress_level += 1
    stress_level = min(10, stress_level)

    # 4. Map Social Battery
    social_battery = "moderate"
    if "social" in challenges:
        social_battery = "low"
    elif culture.get("familySupport") == "very-strong":
        social_battery = "full"

    profile = {
        "name": edu.get("fullName", "Student"),
        "major": edu.get("program", "General Studies"),
        "university": edu.get("university", "Unknown"),
        "stressLevel": stress_level,
        "currentPhase": "Freshman" if edu.get("yearsEnglish", 0) > 5 else "Foundation",
        "academicConfidence": academic_confidence,
        "socialBattery": social_battery,
        "currentMood": "Determined" if "tech" in culture.get("learningContext", []) else "Steady"
    }

    # 5. Run prediction using the Sklearn Model
    success_probability = 0.65
    status = "At Risk"
    
    if student_model and encoders:
        try:
            # Feature Order: [gender, education, imd_band, age_band, disability, attempts, credits, score, weighted_score]
            # Encoding Gender 'M' as 1 or 'F' as 0
            gender_val = 1 if edu.get("gender") == "M" else 0
            
            # Prepare feature array for the model
            features = np.array([[
                gender_val, 
                education_label, 
                0, 0, 0, # Placeholders for imd_band, age_band, disability
                0,       # num_of_prev_attempts
                edu.get("credits", 60), 
                academic_confidence, 
                academic_confidence # weighted_score proxy
            ]])
            
            success_probability = float(student_model.predict_proba(features)[0][1])
            status = "Pass" if success_probability > 0.5 else "At Risk"
        except Exception:
            pass

    return {
        "user_profile": profile,
        "ai_prediction": {
            "success_probability": round(success_probability, 2),
            "status": status
        }
    }