import csv
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from uuid import uuid4

from ai_service import predict_initial_profile
from services.trend_engine import analyze_student_state
from services.chat_service import generate_agent_response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# BKT Parameter Store
# ---------------------------------------------------------------------------
skill_params: Dict[str, Dict[str, float]] = {}

_DEFAULT_BKT_PARAMS: Dict[str, float] = {
    "p_init":    0.30,
    "p_transit": 0.10,
    "p_guess":   0.15,
    "p_slip":    0.10,
    "p_forget":  0.00,
}

_PARAM_KEY_MAP: Dict[str, str] = {
    "prior":   "p_init",
    "learns":  "p_transit",
    "guesses": "p_guess",
    "slips":   "p_slip",
    "forgets": "p_forget",
}

_CSV_PATH = os.path.join(os.path.dirname(__file__), "bkt_parameters_trained.csv")

# ---------------------------------------------------------------------------
# Skill Category Mapping (keyword-based)
# ---------------------------------------------------------------------------
_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "Algebra": ["algebra", "equation", "linear", "quadratic", "factor", "polynomial",
                "inequality", "expression", "variable", "solve", "system", "slope",
                "function", "distributive", "like terms", "combining", "proportion",
                "ratio", "percent"],
    "Geometry": ["geometry", "area", "perimeter", "triangle", "circle", "square",
                 "rectangle", "pythagorean", "angle", "polygon", "volume", "surface",
                 "distance", "midpoint", "coordinate", "parallelogram", "trapezoid",
                 "cylinder", "cone", "sphere", "scale factor", "similar"],
    "Statistics": ["mean", "median", "mode", "probability", "statistics", "data",
                   "distribution", "average", "variance", "standard deviation",
                   "sample", "population", "histogram", "box plot", "scatter"],
    "Number Sense": ["number", "fraction", "decimal", "integer", "exponent",
                     "scientific notation", "prime", "order of operations", "place value",
                     "absolute value", "rational", "irrational", "negative"],
    "Calculus": ["derivative", "integral", "limit", "calculus", "differentiation",
                 "rate of change", "slope of tangent", "antiderivative"],
}


def _classify_skill_category(skill_name: str) -> str:
    """Classifies a skill name into a category using keyword matching."""
    lower = skill_name.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return category
    return "General"


def _load_bkt_csv(path: str) -> Dict[str, Dict[str, Any]]:
    """Reads the long-format BKT CSV and pivots into a nested dict with categories."""
    params: Dict[str, Dict[str, Any]] = {}

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            skill = row["skill"].strip()
            param = row["param"].strip()
            value = float(row["value"])
            internal_key = _PARAM_KEY_MAP.get(param)
            if internal_key is None:
                continue
            if skill not in params:
                params[skill] = {"category": _classify_skill_category(skill)}
            params[skill][internal_key] = value

    return params


def get_bkt_params(skill_name: str) -> Dict[str, float]:
    params = skill_params.get(skill_name)
    if params is None:
        logger.warning("BKT skill '%s' not found — using defaults.", skill_name)
        return _DEFAULT_BKT_PARAMS.copy()
    return params


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loading BKT parameters from: %s", _CSV_PATH)
    try:
        loaded = _load_bkt_csv(_CSV_PATH)
        skill_params.update(loaded)
        logger.info("BKT parameters loaded — %d skills indexed.", len(skill_params))
    except FileNotFoundError:
        logger.error("BKT CSV not found at '%s'. All lookups will use defaults.", _CSV_PATH)
    except Exception as exc:
        logger.exception("Failed to load BKT parameters: %s", exc)

    yield

    skill_params.clear()
    logger.info("BKT parameter store cleared on shutdown.")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AI Academy Prediction & Chat API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------
class InitialProfilingRequest(BaseModel):
    educationalBackground: Dict[str, Any]
    learningPreferences: Dict[str, Any]
    culturalContext: Dict[str, Any]
    diagnosticAssessment: Optional[Dict[str, Any]] = None


class AnalyzeStateRequest(BaseModel):
    recent_frustration: List[float]   # last 5-7 frustration scores [0,1]
    recent_accuracy: List[float]      # last 5-7 accuracy values [0,1] or [0/1]
    recent_boredom: List[float]       # last 5-7 boredom scores [0,1]


class ChatRequest(BaseModel):
    agent_type: str                       # academic | wellness | social | coordinator | tutor
    message: str
    student_context: Dict[str, Any]       # profile data passed from Express
    chat_history: Optional[List[Dict[str, str]]] = None  # [{role, content}]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {
        "status": "active",
        "service": "prediction-engine",
        "bkt_skills_loaded": len(skill_params),
        "version": "2.0.0",
    }


@app.post("/api/predict/initial-profile")
async def predict_initial_profile_endpoint(payload: InitialProfilingRequest):
    """
    Receives onboarding data from Express, runs ML inference,
    and returns the full profile including bloom level, language risk, and active agents.
    """
    try:
        prediction_result = predict_initial_profile(payload.dict())
        return {
            "persistentLearnerId": str(uuid4()),
            "prediction": prediction_result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference Engine Error: {str(e)}")


@app.post("/api/analyze-state")
async def analyze_state_endpoint(payload: AnalyzeStateRequest):
    """
    Analyses recent interaction signals and returns a cognitive state label.
    Called by Express periodically per user session.

    Returns one of:
      CRITICAL_STRUGGLE | FLOW_STATE | DISENGAGED | PRODUCTIVE_STRUGGLE | NEUTRAL
    """
    try:
        state = analyze_student_state(
            recent_frustration=payload.recent_frustration,
            recent_accuracy=payload.recent_accuracy,
            recent_boredom=payload.recent_boredom,
        )
        return {
            "state": state,
            "signals": {
                "frustration_window": payload.recent_frustration,
                "accuracy_window": payload.recent_accuracy,
                "boredom_window": payload.recent_boredom,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trend Engine Error: {str(e)}")


@app.get("/api/bkt/skills")
async def get_all_bkt_skills():
    """
    Returns the full list of BKT skills with their trained parameters and categories.
    Called by Express during onboarding to seed the bkt_skill_mastery table.
    """
    if not skill_params:
        raise HTTPException(status_code=503, detail="BKT parameters not loaded yet.")

    skills = []
    for skill_name, params in skill_params.items():
        skills.append({
            "skillName": skill_name,
            "category": params.get("category", "General"),
            "pInit": params.get("p_init", _DEFAULT_BKT_PARAMS["p_init"]),
            "pTransit": params.get("p_transit", _DEFAULT_BKT_PARAMS["p_transit"]),
            "pGuess": params.get("p_guess", _DEFAULT_BKT_PARAMS["p_guess"]),
            "pSlip": params.get("p_slip", _DEFAULT_BKT_PARAMS["p_slip"]),
            "pForget": params.get("p_forget", _DEFAULT_BKT_PARAMS["p_forget"]),
        })

    return {"count": len(skills), "skills": skills}


@app.get("/api/bkt/params/{skill_name}")
async def get_bkt_params_endpoint(skill_name: str):
    """Returns BKT parameters for a single named skill."""
    params = get_bkt_params(skill_name)
    return {"skillName": skill_name, "params": params}


@app.post("/api/chat")
async def chat_endpoint(payload: ChatRequest):
    """
    LLM chat endpoint. Called by Express to generate agent responses.
    Returns the AI agent's reply string.
    """
    valid_agents = {"academic", "wellness", "social", "coordinator", "tutor"}
    if payload.agent_type not in valid_agents:
        raise HTTPException(status_code=400, detail=f"Invalid agent_type. Must be one of: {valid_agents}")

    try:
        response = generate_agent_response(
            agent_type=payload.agent_type,
            message=payload.message,
            student_context=payload.student_context,
            chat_history=payload.chat_history,
        )
        return {"agent": payload.agent_type, "response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat Engine Error: {str(e)}")