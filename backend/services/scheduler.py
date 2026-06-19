import logging
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from db import SessionLocal, InitialProfileORM, InteractionLogORM, BktSkillMasteryORM
from app.graph.workflow import workflow
from services.trend_engine import analyze_student_state

logger = logging.getLogger(__name__)

async def run_2_week_assessment():
    logger.info("Running 2-Week Background Assessment Loop...")
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        fourteen_days_ago = now - timedelta(days=14)
        
        # 1. Fetch profiles needing assessment
        # Condition: last_assessment_date is older than 14 days 
        # (or NULL but created_at is older than 14 days)
        profiles = db.query(InitialProfileORM).filter(
            (InitialProfileORM.last_assessment_date == None) | (InitialProfileORM.last_assessment_date <= fourteen_days_ago)
        ).all()
        
        for profile in profiles:
            if profile.last_assessment_date is None and profile.created_at and profile.created_at > fourteen_days_ago:
                continue
                
            user_id = profile.user_id
            logger.info(f"Assessing student {user_id}")
            
            # 2. Recalculate BKT and time trend slopes
            logs = db.query(InteractionLogORM).filter(
                InteractionLogORM.user_id == user_id
            ).order_by(InteractionLogORM.occurred_at.desc()).limit(10).all()
            
            recent_frustration = [log.sentiment_score for log in logs if log.sentiment_score is not None]
            recent_accuracy = [1.0 if log.correct else 0.0 for log in logs if log.correct is not None]
            recent_boredom = [0.5] * len(logs) # Proxy for boredom if unavailable
            
            if len(recent_accuracy) >= 3:
                state_label = analyze_student_state(
                    recent_frustration=recent_frustration,
                    recent_accuracy=recent_accuracy,
                    recent_boredom=recent_boredom
                )
            else:
                state_label = "NEUTRAL"
                
            # 3. Gateway Decision (via LangGraph)
            bkt_skills = db.query(BktSkillMasteryORM).filter(BktSkillMasteryORM.user_id == user_id).all()
            bkt_summary = {b.skill_name: b.p_mastery for b in bkt_skills}
            
            state_input = {
                "messages": [],
                "student_context": {"bkt_mastery": bkt_summary, "cognitive_state": state_label, "assessment_trigger": "2-week-loop"},
                "student_profile": {"requires_human_override": profile.requires_human_override},
                "active_agent": "coordinator",
                "risk_level": "Critical" if state_label == "CRITICAL_STRUGGLE" else "Standard",
                "user_id": str(user_id),
                "thread_id": f"assessment-{now.timestamp()}",
            }
            
            # This passes the state through the Coordinator and generates new plans
            result = await workflow.ainvoke(state_input)
            logger.info(f"LangGraph Assessment Result for {user_id} generated. Final Plan Length: {len(result.get('final_plan', ''))}")
            
            # 4. Update assessment date to prevent looping
            profile.last_assessment_date = now
            
        db.commit()
    except Exception as e:
        logger.error(f"Error in 2-week assessment loop: {e}")
    finally:
        db.close()

scheduler = AsyncIOScheduler()
scheduler.add_job(
    run_2_week_assessment,
    trigger=IntervalTrigger(hours=24), # Check daily
    id="2_week_assessment_job",
    replace_existing=True
)

def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started: 2-Week Background Loop initialized.")
