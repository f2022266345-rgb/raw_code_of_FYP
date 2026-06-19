import joblib
import numpy as np
import os
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder

def retrain():
    print(f"Training with scikit-learn version: {sklearn.__version__}")
    
    # 9 features expected by ai_service.py:
    # [gender_val, education_label, imd_proxy, age_band_proxy, disability_proxy, 
    #  num_of_prev_attempts, credits, academic_confidence, weighted_score]
    np.random.seed(42)
    X_train = np.random.rand(100, 9) * 100
    y_train = np.random.randint(0, 2, 100)

    model = RandomForestClassifier(n_estimators=10, random_state=42)
    model.fit(X_train, y_train)

    encoders = {"dummy_encoder": LabelEncoder()}
    encoders["dummy_encoder"].fit(["A", "B", "C"])

    model_path = os.path.join(os.path.dirname(__file__), 'student_model.pkl')
    encoder_path = os.path.join(os.path.dirname(__file__), 'encoders.pkl')

    joblib.dump(model, model_path)
    joblib.dump(encoders, encoder_path)

    print("Successfully retrained and saved student_model.pkl and encoders.pkl")

if __name__ == "__main__":
    retrain()
