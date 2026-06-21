const FASTAPI_BASE = process.env.FASTAPI_BASE_URL || "http://localhost:8080";

async function fastapiGet(path) {
  const res = await fetch(`${FASTAPI_BASE}${path}`);
  const data = await res.json();
  if (!res.ok) throw Object.assign(new Error(data.detail || "FastAPI error"), { status: res.status });
  return data;
}

async function fastapiPost(path, body) {
  const res = await fetch(`${FASTAPI_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw Object.assign(new Error(data.detail || "FastAPI error"), { status: res.status });
  return data;
}

class DigitalTwinController {
  /**
   * GET /api/digital-twin/student
   * Returns the complete digital twin for the authenticated user.
   */
  async getStudentTwin(req, res) {
    try {
      const userId = req.user.userId;
      const data = await fastapiGet(`/api/digital-twin/student/${userId}`);
      res.json(data);
    } catch (error) {
      if (error.status === 404) {
        return res.status(404).json({ error: "Digital twin not found. Complete onboarding first." });
      }
      console.error("getStudentTwin error:", error.message);
      res.status(error.status || 500).json({ error: error.message });
    }
  }

  /**
   * POST /api/digital-twin/update
   * Records a new interaction and updates the twin in FastAPI.
   */
  async updateTwin(req, res) {
    const userId = req.user.userId;
    const {
      problem_id,
      skill_id,
      correct,
      time_on_task_ms,
      mood,
      hints_used,
      attempt_count,
      cognitive_weight,
    } = req.body;

    try {
      const data = await fastapiPost("/api/digital-twin/update", {
        user_id: userId,
        interaction: {
          problem_id: Number(problem_id),
          skill_id: Number(skill_id),
          correct: Boolean(correct),
          time_on_task_ms: Number(time_on_task_ms),
          hints_used: Number(hints_used ?? 0),
          attempt_count: Number(attempt_count ?? 1),
          cognitive_weight: Number(cognitive_weight ?? 1.5),
          mood: mood || "neutral",
        },
      });
      res.json({ success: true, data });
    } catch (error) {
      console.error("updateTwin error:", error.message);
      res.status(error.status || 500).json({ error: error.message });
    }
  }

  /**
   * GET /api/digital-twin/analytics?period=7d|30d|90d
   * Returns learning analytics trend data.
   */
  async getAnalytics(req, res) {
    try {
      const userId = req.user.userId;
      const period = req.query.period || "7d";
      const data = await fastapiGet(
        `/api/digital-twin/analytics/${userId}?period=${period}`
      );
      res.json(data);
    } catch (error) {
      console.error("getAnalytics error:", error.message);
      res.status(error.status || 500).json({ error: error.message });
    }
  }

  /**
   * POST /api/digital-twin/initialize
   * Called from onboarding to seed the twin for a new student.
   */
  async initializeTwin(req, res) {
    const userId = req.user.userId;
    const { initial_predictions, bloom_level, language_barrier_risk } = req.body;

    try {
      const data = await fastapiPost("/api/digital-twin/initialize", {
        user_id: userId,
        initial_predictions: initial_predictions || {},
        bloom_level: bloom_level || 1,
        language_barrier_risk: language_barrier_risk || 0.5,
      });
      res.json(data);
    } catch (error) {
      console.error("initializeTwin error:", error.message);
      // Non-fatal — don't fail onboarding if twin init fails
      res.status(200).json({ success: false, warning: error.message });
    }
  }
}

export default new DigitalTwinController();
