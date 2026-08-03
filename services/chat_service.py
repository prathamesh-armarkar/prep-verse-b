"""AI-powered career assistant using Groq's Llama 3.1 8B Instant model."""

import json
import logging
import re

from flask import current_app

from models.chat import ChatHistory

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are PrepVerse AI, an expert career mentor for students "
    "and early-career professionals. "
    "You specialise in: resume writing, ATS optimisation, "
    "interview preparation, career planning, skill roadmaps, "
    "job search strategy, and professional development.\n\n"
    "Behaviour rules:\n"
    "- Answer ONLY on the topics above. Politely decline "
    "off-topic questions.\n"
    "- Keep responses concise (under 150 words) and actionable.\n"
    "- When relevant, suggest 2-4 follow-up actions the user can "
    "take next.\n"
    "- Be encouraging but honest — give specific, practical advice.\n"
    "- NEVER generate fake credentials, degrees, or experience.\n\n"
    "Return a JSON object. No markdown, no code fences, "
    "no extra text:\n"
    "{\n"
    "  \"message\": str (your response to the user),\n"
    "  \"actions\": [str] (optional, 2-4 brief follow-up "
    "suggestions the user can ask about)\n"
    "}\n"
    "If you cannot help with the request, set message to a polite "
    "explanation and actions to []."
)

class CareerAssistantError(Exception):
    """Raised when the career assistant cannot produce a response."""



class CareerAssistantService:
    """Coordinates calling Groq for a career-mentoring chat response."""

    MAX_CONTEXT_EXCHANGES = 6  # last N user+assistant pairs to include

    @staticmethod
    def is_enabled():
        try:
            return bool(current_app.config.get("GROQ_API_KEY"))
        except RuntimeError:
            return False

    @classmethod
    def chat(cls, user_id, user_message, resume_context=None):
        """Send a message to the assistant and return the response."""
        api_key = current_app.config.get("GROQ_API_KEY")
        if not api_key:
            raise CareerAssistantError("GROQ_API_KEY is not configured.")

        base_url = current_app.config.get("GROQ_BASE_URL")
        model = current_app.config.get("GROQ_MODEL")
        temperature = current_app.config.get("GROQ_TEMPERATURE", 0.3)
        max_tokens = current_app.config.get("GROQ_MAX_TOKENS", 1024)

        # Persist user message
        ChatHistory.create(user_id, "user", user_message)

        # Build context from recent history and hidden resume context
        context_messages = cls._build_context(user_id, resume_context)

        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=base_url)
            completion = client.chat.completions.create(
                model=model,
                messages=context_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            logger.warning("Career assistant API call failed: %s", exc)
            raise CareerAssistantError(str(exc)) from exc

        content = (
            completion.choices[0].message.content or ""
        ).strip() if completion.choices else ""
        if not content:
            raise CareerAssistantError("Assistant returned an empty response.")

        try:
            payload = cls._extract_json(content)
        except (json.JSONDecodeError, ValueError) as exc:
            raise CareerAssistantError(
                f"Could not parse assistant response: {exc}"
            ) from exc

        result = cls._normalise(payload)

        # Persist assistant response
        ChatHistory.create(user_id, "assistant", result["message"])

        return result

    @classmethod
    def _resume_context_text(cls, resume_context):
        """Format hidden resume context for the assistant."""
        return (
            "Use this hidden resume context to inform your answer. "
            "Do not mention that it was provided as hidden context.\n\n"
            "Answer the user’s request using it and keep the response "
            "concise and practical.\n\n"
            "Resume context JSON:\n"
            f"{json.dumps(resume_context, ensure_ascii=False)}"
        )

    @classmethod
    def _build_context(cls, user_id, resume_context=None):
        """Build the message list for the API call."""
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        if resume_context:
            messages.append({
                "role": "system",
                "content": cls._resume_context_text(resume_context),
            })

        try:
            recent = ChatHistory.find_recent_by_user(
                user_id, cls.MAX_CONTEXT_EXCHANGES * 2
            )
            # find_recent returns newest-first; reverse to chronological.
            for entry in reversed(recent):
                messages.append({
                    "role": entry["role"],
                    "content": entry["message"],
                })
        except Exception:
            logger.exception("Failed to load chat history for context")

        return messages

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
    def _normalise(cls, payload):
        """Ensure the response has the expected shape."""
        message = str(payload.get("message") or payload.get("response") or "")
        if not message:
            message = (
                "I'm not sure how to answer that. "
                "Could you rephrase your question?"
            )

        actions = payload.get("actions") or payload.get("suggestions") or []
        if not isinstance(actions, list):
            actions = []
        actions = [str(a) for a in actions if a][:4]

        return {"message": message, "actions": actions}

    @staticmethod
    def get_history(user_id, limit=50):
        """Return the user's chat history."""
        try:
            entries = ChatHistory.find_recent_by_user(user_id, limit)
            return [
                {
                    "id": str(e["_id"]),
                    "role": e["role"],
                    "message": e["message"],
                    "created_at": e["created_at"].isoformat(),
                }
                for e in reversed(entries)
            ]
        except Exception:
            logger.exception("Failed to load chat history")
            return []

    @staticmethod
    def clear_history(user_id):
        """Delete all chat history for a user."""
        try:
            ChatHistory.clear_by_user(user_id)
            return True
        except Exception:
            logger.exception("Failed to clear chat history")
            return False

