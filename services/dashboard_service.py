"""Dashboard aggregation service — pulls live data from stored resume, roadmap,
and chat collections so the frontend dashboard always shows real user metrics."""

import logging
from datetime import datetime

from models.chat import ChatHistory
from models.resume import Resume
from models.roadmap import Roadmap

logger = logging.getLogger(__name__)


class DashboardService:
    """Aggregates stored data for the dashboard overview."""

    @staticmethod
    def get_dashboard(user_id):
        """Return a complete dashboard payload for the authenticated user."""
        try:
            user_id = str(user_id)
        except (TypeError, ValueError):
            return None

        resume_data = DashboardService._get_resume_data(user_id)
        roadmap_data = DashboardService._get_roadmap_data(user_id)
        chat_data = DashboardService._get_chat_data(user_id)

        # Stats cards
        ats_score = resume_data.get("ats_score") or 0
        resume_count = resume_data.get("resume_count") or 0
        latest_roadmap = roadmap_data.get("latest_roadmap")
        roadmap_progress = int(latest_roadmap.get("completion_percentage", 0)) if latest_roadmap else 0
        roadmap_count = roadmap_data.get("roadmap_count") or 0
        chat_count = chat_data.get("total_messages") or 0

        resume_completeness = resume_data.get("completeness", 0)
        profile_completion = DashboardService._compute_profile_completion(
            resume_completeness, roadmap_count > 0, chat_count > 0
        )

        career_readiness = min(100, int(ats_score * 0.6 + roadmap_progress * 0.4))

        recent_activity = DashboardService._build_activity_feed(
            resume_data, roadmap_data, chat_data
        )

        recommendation = DashboardService._generate_recommendation(
            resume_data, latest_roadmap
        )

        upcoming_goals = DashboardService._extract_goals(latest_roadmap)

        welcome = {
            "resume_count": resume_count,
            "roadmap_count": roadmap_count,
            "chat_count": chat_count,
            "last_activity": DashboardService._last_activity(
                resume_data, roadmap_data, chat_data
            ),
        }

        return {
            "stats": [
                {
                    "title": "Resume Score",
                    "value": f"{ats_score}%",
                    "description": resume_data.get("score_label", "No resume uploaded yet"),
                    "icon": "FaFileAlt",
                    "accent": "#2563eb",
                },
                {
                    "title": "Profile Completion",
                    "value": f"{profile_completion}%",
                    "description": DashboardService._completion_label(profile_completion),
                    "icon": "FaUserCheck",
                    "accent": "#0ea5e9",
                },
                {
                    "title": "Roadmap Progress",
                    "value": f"{roadmap_progress}%",
                    "description": f"{roadmap_count} roadmap{'s' if roadmap_count != 1 else ''} created",
                    "icon": "FaMap",
                    "accent": "#8b5cf6",
                },
                {
                    "title": "Career Readiness",
                    "value": f"{career_readiness}%",
                    "description": DashboardService._readiness_label(career_readiness),
                    "icon": "FaBullseye",
                    "accent": "#10b981",
                },
            ],
            "quick_actions": [
                {
                    "title": "Analyze Resume",
                    "description": "Review your latest resume and improve weak areas.",
                    "icon": "FaFileAlt",
                    "link": "/resume-analyzer",
                },
                {
                    "title": "AI Career Assistant",
                    "description": "Get guidance for interviews, applications, and planning.",
                    "icon": "FaRobot",
                    "link": "/assistant",
                },
                {
                    "title": "Generate Skill Roadmap",
                    "description": "Create a personalized roadmap for your target role.",
                    "icon": "FaClipboardCheck",
                    "link": "/skill-roadmap",
                },
            ],
            "recent_activity": recent_activity,
            "recommendation": recommendation,
            "upcoming_goals": upcoming_goals,
            "welcome": welcome,
        }

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_resume_data(user_id):
        """Aggregate resume statistics."""
        try:
            latest = Resume.find_latest_by_user(user_id)
            count = Resume.count_by_user(user_id)
        except Exception:
            logger.exception("Failed to load resume data for dashboard")
            return {"ats_score": 0, "resume_count": 0, "completeness": 0}

        if not latest:
            return {
                "ats_score": 0,
                "resume_count": 0,
                "completeness": 0,
                "score_label": "Upload a resume to get started",
                "last_upload": None,
            }

        analysis = latest.get("analysis_json") or {}
        ats_score = analysis.get("ats_score") or 0
        completeness = (
            analysis.get("resume_completeness", {})
            .get("overall_completion", 0)
        ) or 0

        if ats_score >= 90:
            score_label = "Excellent — strong ATS compatibility"
        elif ats_score >= 75:
            score_label = "Good — minor improvements recommended"
        elif ats_score >= 60:
            score_label = "Average — consider optimizing key sections"
        else:
            score_label = "Needs work — review suggestions below"

        return {
            "ats_score": ats_score,
            "resume_count": count,
            "completeness": completeness,
            "score_label": score_label,
            "last_upload": latest.get("created_at").isoformat() if latest.get("created_at") else None,
            "latest_file": latest.get("original_name") if latest else None,
            "missing_sections": (
                analysis.get("resume_completeness", {})
                .get("missing_sections", [])
            ),
        }

    @staticmethod
    def _get_roadmap_data(user_id):
        """Aggregate roadmap statistics."""
        try:
            latest = Roadmap.find_latest_by_user(user_id)
            count = Roadmap.count_by_user(user_id)
        except Exception:
            logger.exception("Failed to load roadmap data for dashboard")
            return {"latest_roadmap": None, "roadmap_count": 0}

        if not latest:
            return {"latest_roadmap": None, "roadmap_count": 0}

        roadmap_json = latest.get("roadmap_json") or {}
        weeks = roadmap_json.get("weeks") or []
        completed_weeks = sum(
            1 for w in weeks if w.get("type") in ("project", "assessment")
        )
        total_weeks = roadmap_json.get("total_weeks", len(weeks)) or 1

        return {
            "latest_roadmap": {
                "id": str(latest["_id"]),
                "career_goal": latest.get("career_goal", ""),
                "current_level": latest.get("current_level", ""),
                "completion_percentage": latest.get("completion_percentage", 0),
                "total_weeks": total_weeks,
                "completed_weeks": completed_weeks,
                "created_at": latest.get("created_at").isoformat() if latest.get("created_at") else None,
            },
            "roadmap_count": count,
        }

    @staticmethod
    def _get_chat_data(user_id):
        """Aggregate chat statistics."""
        try:
            total = ChatHistory.count_by_user(user_id)
            user_messages = ChatHistory.count_user_messages(user_id)
            last_entries = ChatHistory.find_recent_by_user(user_id, 6)
        except Exception:
            logger.exception("Failed to load chat data for dashboard")
            return {"total_messages": 0, "sessions": 0, "last_activity": None, "recent_messages": []}

        last_entry = last_entries[0] if last_entries else None
        return {
            "total_messages": total,
            "sessions": user_messages,
            "last_activity": last_entry.get("created_at").isoformat() if last_entry and last_entry.get("created_at") else None,
            "recent_messages": [
                {
                    "role": m.get("role", ""),
                    "message": (m.get("message") or "")[:100],
                    "created_at": m.get("created_at").isoformat() if m.get("created_at") else None,
                }
                for m in reversed(last_entries[-6:])
            ],
        }

    @staticmethod
    def _compute_profile_completion(resume_completeness, has_roadmap, has_chat):
        """Weighted profile completion score."""
        base = resume_completeness * 0.5  # 50% weight on resume
        if has_roadmap:
            base += 25  # 25% for having a roadmap
        if has_chat:
            base += 25  # 25% for using the assistant
        return min(100, int(base))

    @staticmethod
    def _completion_label(percent):
        if percent >= 80:
            return "Strong profile — keep it up!"
        if percent >= 60:
            return "Add a roadmap or chat with the assistant"
        return "Upload a resume to get started"

    @staticmethod
    def _readiness_label(percent):
        if percent >= 80:
            return "Ready for outreach"
        if percent >= 60:
            return "Building momentum"
        return "Strengthen your foundation"

    @staticmethod
    def _last_activity(resume_data, roadmap_data, chat_data):
        """Return the most recent activity timestamp across all modules."""
        timestamps = []
        if resume_data.get("last_upload"):
            timestamps.append(resume_data["last_upload"])
        latest_roadmap = roadmap_data.get("latest_roadmap") or {}
        if latest_roadmap.get("created_at"):
            timestamps.append(latest_roadmap["created_at"])
        if chat_data.get("last_activity"):
            timestamps.append(chat_data["last_activity"])
        return max(timestamps) if timestamps else None

    # ------------------------------------------------------------------
    # Activity feed
    # ------------------------------------------------------------------

    @staticmethod
    def _build_activity_feed(resume_data, roadmap_data, chat_data):
        """Build a cross-collection timeline of recent user actions."""
        activities = []

        if resume_data.get("last_upload"):
            ats = resume_data.get("ats_score", 0)
            activities.append({
                "title": "Resume analyzed",
                "time": DashboardService._relative_time(resume_data["last_upload"]),
                "detail": f"Latest resume scored {ats}% ATS compatibility",
                "type": "resume",
                "timestamp": resume_data["last_upload"],
            })

        latest_rm = roadmap_data.get("latest_roadmap")
        if latest_rm and latest_rm.get("created_at"):
            activities.append({
                "title": "Roadmap created",
                "time": DashboardService._relative_time(latest_rm["created_at"]),
                "detail": f"{latest_rm['career_goal']} — {latest_rm['total_weeks']} weeks"
                if latest_rm.get("career_goal")
                else "New skill roadmap generated",
                "type": "roadmap",
                "timestamp": latest_rm["created_at"],
            })

        chat_msgs = chat_data.get("recent_messages") or []
        for msg in chat_msgs[-3:]:
            if msg.get("created_at") and msg.get("role") == "user":
                activities.append({
                    "title": "Career assistant used",
                    "time": DashboardService._relative_time(msg["created_at"]),
                    "detail": msg["message"][:80] + ("..." if len(msg.get("message", "")) > 80 else ""),
                    "type": "chat",
                    "timestamp": msg["created_at"],
                })

        activities.sort(key=lambda a: a["timestamp"], reverse=True)
        return activities[:5]

    @staticmethod
    def _relative_time(iso_str):
        """Convert an ISO timestamp to a human-readable relative time."""
        if not iso_str:
            return ""
        try:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            now = datetime.now(dt.tzinfo)
            delta = now - dt
            if delta.days > 7:
                return dt.strftime("%b %d")
            if delta.days > 0:
                return f"{delta.days}d ago"
            if delta.seconds >= 3600:
                return f"{delta.seconds // 3600}h ago"
            if delta.seconds >= 60:
                return f"{delta.seconds // 60}m ago"
            return "just now"
        except Exception:
            return iso_str[:10] if iso_str else ""

    # ------------------------------------------------------------------
    # AI Recommendation
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_recommendation(resume_data, latest_roadmap):
        """Generate a contextual recommendation based on user data."""
        missing = resume_data.get("missing_sections") or []

        if missing:
            section = missing[0]
            return {
                "title": f"Add your {section} section",
                "description": f"Your resume is missing the {section} section. Adding it will improve your ATS score and make your profile more complete.",
                "action": "Go to Resume",
                "link": "/resume-analyzer",
            }

        if resume_data.get("ats_score", 0) < 75 and resume_data.get("resume_count", 0) > 0:
            return {
                "title": "Optimize your resume for ATS",
                "description": "Your ATS score could be improved. Try adding more role-specific keywords and quantifying your achievements.",
                "action": "View Analysis",
                "link": "/resume-analyzer",
            }

        if latest_roadmap:
            return {
                "title": f"Continue your {latest_roadmap['career_goal']} roadmap",
                "description": f"You're {latest_roadmap['completion_percentage']:.0f}% through your roadmap. Keep progressing through the weekly plan.",
                "action": "View Roadmap",
                "link": "/skill-roadmap",
            }

        if resume_data.get("resume_count", 0) > 0:
            return {
                "title": "Generate a skill roadmap",
                "description": "You have a resume on file. Create a personalised learning roadmap to target your next career goal.",
                "action": "Create Roadmap",
                "link": "/skill-roadmap",
            }

        return {
            "title": "Upload your resume to get started",
            "description": "PrepVerse will analyse your resume and give you an ATS score, skill insights, and personalised recommendations.",
            "action": "Upload Resume",
            "link": "/resume-analyzer",
        }

    # ------------------------------------------------------------------
    # Goals extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_goals(latest_roadmap):
        """Extract upcoming goals from the roadmap weeks."""
        if not latest_roadmap:
            return [
                {"title": "Upload your first resume", "done": False},
                {"title": "Get your ATS score", "done": False},
                {"title": "Chat with PrepVerse AI", "done": False},
            ]

        roadmap_json = latest_roadmap.get("roadmap_json") or latest_roadmap
        weeks = roadmap_json.get("weeks") or []
        total = roadmap_json.get("total_weeks", len(weeks)) or 1

        completed = sum(1 for w in weeks if w.get("type") in ("project", "assessment"))
        has_roadmap = completed > 0

        goals = [
            {"title": f"Complete {latest_roadmap['career_goal']} roadmap", "done": has_roadmap},
        ]

        upcoming = [w for w in weeks if w.get("type") not in ("project", "assessment")]
        for week in upcoming[:4]:
            goals.append({
                "title": f"Week {week['week']}: {week['topic']}",
                "done": False,
            })

        if len(goals) < 3:
            goals.append({"title": "Chat with PrepVerse AI for career guidance", "done": False})
        if len(goals) < 3:
            goals.append({"title": "Review your resume analysis", "done": False})

        return goals[:5]

