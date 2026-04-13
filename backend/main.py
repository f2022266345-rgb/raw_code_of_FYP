from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from uuid import uuid4

from ai_service import predict_initial_profile

app = FastAPI(
    title="AI Academy Prediction API",
    version="1.0.0",
)

# Standard CORS setup to allow communication from your Express backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Adjust this to your specific Express URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Request Schemas ---

class InitialProfilingRequest(BaseModel):
    educationalBackground: Dict[str, Any]
    learningPreferences: Dict[str, Any]
    culturalContext: Dict[str, Any]
    diagnosticAssessment: Optional[Dict[str, Any]] = None

@app.get("/health")
async def health():
    return {"status": "active", "service": "prediction-engine"}

@app.post("/api/predict/initial-profile")
async def predict_initial_profile_endpoint(payload: InitialProfilingRequest):
    """
    Receives onboarding data from Express, runs ML inference,
    and returns the profile and session context.
    """
    try:
        # Process the raw data through the AI Service mapping
        prediction_result = predict_initial_profile(payload.dict())
        
        # Return the results along with a unique identifier
        return {
            "persistentLearnerId": str(uuid4()),
            "prediction": prediction_result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference Engine Error: {str(e)}")