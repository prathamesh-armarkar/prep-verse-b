"""AI-powered skill roadmap generation using Groq's Llama 3.1 8B Instant model."""

import json
import logging
import re

from flask import current_app

from models.roadmap import Roadmap, serialize_roadmap

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are PrepVerse AI, an expert career and learning advisor. "
    "Generate a structured, week-by-week skill development roadmap for the "
    "user's target career goal and current experience level.\n\n"
    "Guidelines:\n"
    "- Create a roadmap that is realistic and achievable in 8-12 weeks.\n"
    "- Each week should have a clear topic, 2-4 specific learning objectives, "
    "and 1-2 recommended resources (free or widely available).\n"
    "- Include at least 2 milestone projects that the user can build to "
    "demonstrate their skills.\n"
    "- Suggest relevant certifications or assessments where appropriate.\n"
    "- NEVER invent fake courses, certifications, or institutions. Only "
    "recommend well-known platforms (Coursera, Udemy, freeCodeCamp, "
    "LeetCode, HackerRank, GitHub, official documentation).\n\n"
    "Return a JSON object. No markdown, no code fences, no extra text:\n"
    "{\n"
    '  "title": str (roadmap title, e.g. "Java Full Stack Developer — 12-Week Roadmap"),\n'
    '  "total_weeks": int (8-12),\n'
    '  "weeks": [\n'
    "    {\n"
    '      "week": int,\n'
    '      "topic": str,\n'
    '      "objectives": [str],\n'
    '      "resources": [str],\n'
    '      "type": "learning"|"project"|"assessment"\n'
    "    }\n"
    "  ],\n"
    '  "milestones": [str] (2-3 key projects or achievements),\n'
    '  "certifications": [str] (optional, recommended certs),\n'
    '  "estimated_hours_per_week": int,\n'
    '  "difficulty": "beginner"|"intermediate"|"advanced"\n'
    "}\n"
    "Base the difficulty and pace only on the user's stated current level."
)


class RoadmapGenerationError(Exception):
    """Raised when roadmap generation fails."""


class RoadmapService:
    """Coordinates Groq-powered roadmap generation and persistence."""

    @staticmethod
    def is_enabled():
        try:
            return bool(current_app.config.get("GROQ_API_KEY"))
        except RuntimeError:
            return False

    @classmethod
    def generate(cls, user_id, career_goal, current_level):
        """Generate a new roadmap for the user."""
        api_key = current_app.config.get("GROQ_API_KEY")
        if not api_key:
            raise RoadmapGenerationError("GROQ_API_KEY is not configured.")

        base_url = current_app.config.get("GROQ_BASE_URL")
        model = current_app.config.get("GROQ_MODEL")
        temperature = current_app.config.get("GROQ_TEMPERATURE", 0.2)
        max_tokens = current_app.config.get("GROQ_MAX_TOKENS", 2048)

        user_prompt = (
            f"Career goal: {career_goal}\n"
            f"Current level: {current_level}\n\n"
            "Generate a detailed week-by-week roadmap following the schema in the system instructions."
        )

        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=base_url)
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            logger.warning("Roadmap generation API call failed: %s", exc)
            raise RoadmapGenerationError(str(exc)) from exc

        content = (
            completion.choices[0].message.content or ""
        ).strip() if completion.choices else ""
        if not content:
            raise RoadmapGenerationError("Roadmap generation returned an empty response.")

        try:
            payload = cls._extract_json(content)
        except (json.JSONDecodeError, ValueError) as exc:
            raise RoadmapGenerationError(
                f"Could not parse roadmap response: {exc}"
            ) from exc

        roadmap_data = cls._normalise(payload, career_goal, current_level)

        roadmap_id = Roadmap.create({
            "user_id": user_id,
            "career_goal": career_goal,
            "current_level": current_level,
            "roadmap_json": roadmap_data,
            "completion_percentage": 0.0,
        })

        roadmap_data["id"] = roadmap_id
        roadmap_doc = Roadmap.find_by_id_and_user(roadmap_id, user_id)
        if roadmap_doc:
            roadmap_data["created_at"] = roadmap_doc["created_at"].isoformat()
        return roadmap_data

    @staticmethod
    def _extract_json(content):
        """Return the JSON object from the model response."""
        cleaned = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            raise ValueError("Response is not a JSON object.")
        return data

    @classmethod
    def _normalise(cls, payload, career_goal, current_level):
        """Validate and normalise the roadmap payload."""
        result = {
            "title": str(payload.get("title") or f"{career_goal} — Roadmap"),
            "total_weeks": max(4, min(16, int(payload.get("total_weeks", 8)))),
            "weeks": [],
            "milestones": [],
            "certifications": [],
            "estimated_hours_per_week": max(2, min(40, int(payload.get("estimated_hours_per_week", 10)))),
            "difficulty": current_level if current_level in ("beginner", "intermediate", "advanced") else "intermediate",
        }

        for week in (payload.get("weeks") or []):
            if not isinstance(week, dict):
                continue
            week_num = int(week.get("week", 0))
            if week_num < 1 or week_num > result["total_weeks"]:
                continue
            result["weeks"].append({
                "week": week_num,
                "topic": str(week.get("topic") or f"Week {week_num}"),
                "objectives": [str(o) for o in (week.get("objectives") or []) if o][:4],
                "resources": [str(r) for r in (week.get("resources") or []) if r][:3],
                "type": week.get("type", "learning") if week.get("type") in ("learning", "project", "assessment") else "learning",
            })

        result["weeks"].sort(key=lambda w: w["week"])
        result["milestones"] = [str(m) for m in (payload.get("milestones") or []) if m][:5]
        result["certifications"] = [str(c) for c in (payload.get("certifications") or []) if c][:5]

        return result

    @staticmethod
    def get_latest(user_id):
        """Return the user's most recent roadmap."""
        try:
            roadmap = Roadmap.find_latest_by_user(str(user_id))
            if not roadmap:
                return None
            return serialize_roadmap(roadmap)
        except Exception:
            logger.exception("Failed to load latest roadmap")
            return None

    @staticmethod
    def get_all(user_id):
        """Return all roadmaps for the user."""
        try:
            roadmaps = Roadmap.find_all_by_user(str(user_id))
            return [serialize_roadmap(r) for r in roadmaps]
        except Exception:
            logger.exception("Failed to load roadmaps")
            return []

    @staticmethod
    def update_progress(user_id, roadmap_id, completion_percentage):
        """Update the completion percentage for a roadmap."""
        try:
            return Roadmap.update_progress(roadmap_id, str(user_id), completion_percentage)
        except Exception:
            logger.exception("Failed to update roadmap progress")
            return False

    @staticmethod
    def delete(user_id, roadmap_id):
        """Delete a roadmap."""
        try:
            return Roadmap.delete(roadmap_id, str(user_id))
        except Exception:
            logger.exception("Failed to delete roadmap")
            return False

