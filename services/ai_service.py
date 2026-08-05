"""AI-powered resume analysis using Groq's Llama 3.1 8B Instant model.

Token-efficiency design
-----------------------
- A compact, structured *digest* is sent to the model instead of the full
  parsed-data JSON blob. Arrays are capped and long strings truncated, which
  keeps the input small and the response focused.
- Raw extracted text is *chunked*: the head (contact/skills region) is given
  priority, and the tail (projects/experience region) is appended only when
  budget allows. This avoids sending thousands of redundant characters.
- The output schema is strict and *bounded* (max items per array), so the
  model cannot drift into long, token-heavy responses.
- A small TTL cache keyed by a hash of the digest avoids repeat API calls for
  identical content (e.g. repeated dashboard reads of the same resume).

Every field returned by the model is validated and normalised so the frontend
always receives well-formed data, and the whole service degrades gracefully
(raises AIAnalysisError) when the API is unavailable.
"""

import hashlib
import json
import logging
import re
import threading
import time

from flask import current_app

logger = logging.getLogger(__name__)

# Compact prompt: exact schema + explicit bounds + a scoring rubric. The rubric
# (not extra tokens) is what forces the model to populate EVERY array, so the
# frontend report never renders with empty cards.
SYSTEM_PROMPT = (
    "You are an expert ATS (Applicant Tracking System) resume reviewer. "
    "Analyze the resume for the role it targets and return ONE valid JSON "
    "object matching the schema exactly. No markdown, no code fences, no extra "
    "text.\n"
    "Schema (populate EVERY field; empty arrays are NOT allowed):\n"
    "{\n"
    '  "ats_score": int 0-100 (overall ATS compatibility),\n'
    '  "confidence": int 0-100 (how confident you are in the score),\n'
    '  "keyword_match": int 0-100,\n'
    '  "ats_breakdown": [{"name": str, "score": int 0-100, "tip": str}] (4-6 items),\n'
    '  "matched_skills": [{"name": str, "reason": str, "importance": str, "market_demand": str}] (up to 8),\n'
    '  "missing_skills": [{"name": str, "reason": str}] (up to 6),\n'
    '  "recommended_skills": [{"name": str, "reason": str}] (up to 6),\n'
    '  "keyword_analysis": [{"name": str, "matched": int 0-100, "missing": int 0-100}] (up to 8),\n'
    '  "sections": [{"name": str, "score": int 0-100, "strength": str, "recommendation": str}] (up to 10),\n'
    '  "resume_strength": [{"name": str, "score": int 0-100, "recommendation": str}] (up to 5),\n'
    '  "suggestions": [{"priority": "high"|"medium"|"low", "title": str, "example": str, "estimated_ats_increase": int 0-20}] (up to 5)\n'
    "}\n"
    "Scoring rubric:\n"
    "- Use the provided target role for scoring context; score against the keywords "
    "that role typically requires.\n"
    "- ats_breakdown must cover Contact, Skills, Experience, Projects, "
    "Education, and Keyword match.\n"
    "- Section identification is SEMANTIC: the same section appears under many "
    "heading names across resumes. Map the heading meaning to ONE canonical "
    "name. Examples: 'Career Objective', 'Profile Summary', 'Professional "
    "Summary', 'About Me', 'Executive Summary', 'Summary of Qualifications', "
    "'Objective' -> Summary; 'Technical Skills', 'Key Skills', 'Skill Set', "
    "'Core Competencies', 'Technologies & Tools', 'Tech Stack', 'Skills & "
    "Abilities', 'Proficiencies' -> Skills; 'Work History', 'Employment "
    "History', 'Professional Experience', 'Internships & Freelancing' -> "
    "Experience; 'Academic Projects', 'Project Portfolio', 'Key Projects' -> "
    "Projects; 'Courses', 'Certificates', 'Trainings' -> Certifications. "
    "Also recognise: 'Hobbies & Interests', 'Extra-curricular Activities' -> "
    "Interests; 'Awards & Achievements' -> Achievements; 'Volunteering & "
    "Community Service' -> Volunteering; 'References available on request' -> "
    "References; 'Declaration' -> Declaration.\n"
    "- sections must report ONLY the sections actually present, using these "
    "canonical names: Contact, Summary, Skills, Projects, Experience, "
    "Education, Certifications, Languages, Achievements, Publications, "
    "Volunteering, Interests, References, Declaration.\n"
    "- Use the 'Detected headings' line to map the resume's exact written "
    "headings to these canonical section names - never invent a section.\n"
    "- matched_skills = skills already present; missing_skills = skills absent "
    "but expected for the target role; recommended_skills = next best skills "
    "to add.\n"
    "- Base every score and every string ONLY on the content provided; never "
    "invent facts. Keep each string under ~15 words."
)

AI_FIELDS = (
    "ats_score",
    "confidence",
    "ats_breakdown",
    "matched_skills",
    "missing_skills",
    "recommended_skills",
    "keyword_analysis",
    "keyword_match",
    "sections",
    "resume_strength",
    "suggestions",
)

# Maximum number of items kept per array after normalisation (bounds output).
_ARRAY_LIMITS = {
    "ats_breakdown": 6,
    "matched_skills": 8,
    "missing_skills": 6,
    "recommended_skills": 6,
    "keyword_analysis": 8,
    "sections": 10,
    "resume_strength": 5,
    "suggestions": 5,
}

# Heading aliases used to surface how the resume is actually written so the
# model can map them to canonical section names regardless of the format.
HEADING_PATTERNS = [
    ("Summary", re.compile(r"career\s+objective|professional\s+summary|profile\s+summary|executive\s+summary|summary\s+of\s+qualifications|about\s+me|personal\s+profile|objectives?|professional\s+profile", re.I)),
    ("Skills", re.compile(r"technical\s+skills|key\s+skills|skill\s+set|core\s+competencies|technologies|tech\s+stack|tools\s+and\s+technologies|languages\s+and\s+technologies|skills\s+and\s+abilities|professional\s+skills|proficien", re.I)),
    ("Experience", re.compile(r"work\s+experience|work\s+history|employment\s+history|professional\s+experience|internships?\s+and\s+freelancing|career\s+history|internship\s+experience|experience", re.I)),
    ("Projects", re.compile(r"academic\s+projects|personal\s+projects|project\s+portfolio|key\s+projects|major\s+projects|project\s+details|internship\s+projects|projects", re.I)),
    ("Education", re.compile(r"education|academic\s+background|academics|educational\s+qualifications|qualifications|education\s+history|academic\s+qualifications", re.I)),
    ("Certifications", re.compile(r"certifications?|certificates|courses?\s+and\s+certifications|trainings?|licenses\s+and\s+certifications|workshops", re.I)),
    ("Languages", re.compile(r"languages?\s+(known|spoken|proficiency|skills)?|linguistic\s+skills|language\s+proficiency", re.I)),
    ("Achievements", re.compile(r"achievements?|accomplishments|awards|honors|recognitions", re.I)),
    ("Publications", re.compile(r"publications?|research\s+papers|patents", re.I)),
    ("Volunteering", re.compile(r"volunteer|community\s+service|social\s+work|ngo", re.I)),
    ("Interests", re.compile(r"hobbies|interests?|extra.?curricular|co.?curricular|activities", re.I)),
    ("Strengths", re.compile(r"strengths?|key\s+strengths", re.I)),
    ("References", re.compile(r"references?|referees?", re.I)),
    ("Declaration", re.compile(r"declaration", re.I)),
]

_cache_lock = threading.Lock()
_cache = {}


class AIAnalysisError(Exception):
    """Raised when the AI analysis cannot be produced."""


class ResumeAIAnalysisService:
    """Coordinates calling Groq's Llama model for a structured resume review."""

    @staticmethod
    def is_enabled():
        try:
            return bool(current_app.config.get("GROQ_API_KEY"))
        except RuntimeError:
            return False

    @classmethod
    def analyze(cls, parsed_data, extracted_text, target_role="", job_description=""):
        """Return a validated AI analysis dict.

        Args:
            parsed_data: dict from the deterministic resume parser.
            extracted_text: raw text extracted from the uploaded file.
            target_role: the job role the user is targeting (required).
            job_description: optional job description text for context-aware scoring.

        Raises:
            AIAnalysisError: when the API key is missing or the API call fails.
        """
        api_key = current_app.config.get("GROQ_API_KEY")
        if not api_key:
            raise AIAnalysisError("GROQ_API_KEY is not configured.")

        base_url = current_app.config.get("GROQ_BASE_URL")
        model = current_app.config.get("GROQ_MODEL")
        temperature = current_app.config.get("GROQ_TEMPERATURE", 0.2)
        max_tokens = current_app.config.get("GROQ_MAX_TOKENS", 2400)

        digest = cls._build_digest(
            parsed_data,
            extracted_text,
            target_role=target_role,
            job_description=job_description,
        )

        cache_key = cls._cache_key(digest)
        cached = cls._cache_get(cache_key)
        if cached is not None:
            return cached

        user_prompt = cls._build_prompt(
            digest,
            target_role=target_role,
            job_description=job_description,
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
            logger.warning("Groq AI analysis failed: %s", exc)
            raise AIAnalysisError(str(exc)) from exc

        content = (completion.choices[0].message.content or "").strip() if completion.choices else ""
        if not content:
            raise AIAnalysisError("Groq returned an empty response.")

        try:
            payload = cls._extract_json(content)
        except (json.JSONDecodeError, ValueError) as exc:
            raise AIAnalysisError(f"Could not parse AI response: {exc}") from exc

        result = cls._normalise(payload)
        # Safety net: llama-3.1-8b-instant can return only the numeric scores
        # (e.g. on truncation) and skip the arrays. Synthesise the report
        # arrays from the parsed data so the dashboard never renders empty
        # cards. Model output is always preferred.
        cls._backfill_from_parsed(parsed_data, result, extracted_text=extracted_text)
        cls._cache_set(cache_key, result)
        return result

    # ------------------------------------------------------------------
    # Token optimisation: digest building + chunked text
    # ------------------------------------------------------------------

    @staticmethod
    def _clean(value):
        """Collapse whitespace on a scalar value."""
        return re.sub(r"\s+", " ", str(value)).strip()

    @classmethod
    def _cap_items(cls, items, limit, width):
        """Return a compact, de-duplicated list of capped strings."""
        out = []
        seen = set()
        for item in items or []:
            text = cls._clean(item)
            if not text or text in seen:
                continue
            seen.add(text)
            if len(text) > width:
                text = text[:width] + "\u2026"
            out.append(text)
            if len(out) >= limit:
                break
        return out

    @classmethod
    def _detect_section_headings(cls, text):
        """Best-effort scan of heading wording actually used in the resume.

        This is a hint for the model, not a parser: the AI still decides how
        to interpret, name, and score each section. Capturing the exact
        written headings ensures every resume format is surfaced.
        """
        if not text:
            return []
        found = []
        seen = set()
        for raw in text.splitlines():
            line = re.sub(r"[:\-–—]+$", "", raw.strip()).strip()
            if not line or len(line) > 48:
                continue
            if line.endswith((".", "…", "!", "?")):
                continue
            low = line.lower()
            for canonical, pattern in HEADING_PATTERNS:
                if pattern.search(low) and canonical not in seen:
                    seen.add(canonical)
                    found.append(f'{canonical} ("{line}")')
                    break
        return found

    @staticmethod
    def _has_summary(parsed, text):
        """Return True when a summary/objective-like section is present."""
        if parsed.get("summary"):
            return True
        if not text:
            return False
        head = text[:4000]
        pattern = re.compile(
            r"^\s*(career\s+objective|professional\s+summary|profile\s+summary|"
            r"executive\s+summary|summary\s+of\s+qualifications|about\s+me|"
            r"professional\s+objective|career\s+goal|objectives?|summary)\s*[:.\-–—]?",
            re.I | re.M,
        )
        return bool(pattern.search(head))

    @classmethod
    def _build_digest(cls, parsed_data, extracted_text, target_role="", job_description=""):
        """Build a compact digest + priority-chunked raw excerpt.

        Token-budget strategy (digest-first):
        1. The structured digest (name, contact, target role, skills, education,
           experience, projects, certifications) is always built in full.
           Target role and job description are included when provided.
        2. If a job description is provided, a capped excerpt is appended to
           the digest so the model can score keyword relevance accurately.
        3. The raw text excerpt uses only the leftover budget. The head
           (contact/skills region) is always kept, and the tail
           (projects/experience region) is appended only when space allows.
        4. The full document is never sent, and the digest is never truncated,
           so the model always sees the candidate's key signals.
        """
        parsed = parsed_data or {}
        budget = int(current_app.config.get("GROQ_INPUT_CHARS", 7000) or 7000)

        lines = []
        name = cls._clean(parsed.get("name"))
        if name:
            lines.append(f"Name: {name}")

        if target_role:
            lines.append(f"Target Role: {target_role}")

        contact = (
            f"Email: {cls._clean(parsed.get('email')) or 'n/a'} | "
            f"Phone: {cls._clean(parsed.get('phone')) or 'n/a'} | "
            f"LinkedIn: {'yes' if parsed.get('linkedin') else 'no'} | "
            f"GitHub: {'yes' if parsed.get('github') else 'no'}"
        )
        lines.append(contact)

        # Per-section caps: skills are the ATS driver so they get the largest
        # limit; verbose narrative sections are capped tighter to save tokens.
        section_caps = {
            "skills": (12, 100),
            "certifications": (6, 100),
            "education": (6, 120),
            "languages": (6, 60),
            "experience": (4, 160),
            "projects": (5, 160),
        }
        for section in ("skills", "education", "experience", "projects", "certifications", "languages"):
            limit, width = section_caps.get(section, (6, 120))
            items = cls._cap_items(parsed.get(section), limit=limit, width=width)
            if items:
                lines.append(f"{section.upper()}: " + " | ".join(items))

        # Surface the exact written headings so the model can map them to
        # canonical section names regardless of resume format.
        headings = cls._detect_section_headings(extracted_text or "")
        if headings:
            lines.append("DETECTED HEADINGS: " + " | ".join(headings))

        # Append job description if provided (capped to save budget).
        if job_description:
            jd_clean = cls._clean(job_description)
            jd_budget = 1500
            if jd_clean:
                truncated = jd_clean[:jd_budget]
                if len(jd_clean) > jd_budget:
                    truncated += "\u2026"
                lines.append(f"JOB DESCRIPTION: {truncated}")

        digest_text = "\n".join(lines)

        # Raw text chunking uses only the leftover budget, so a long digest
        # never crowds out the excerpt and vice-versa.
        raw = cls._clean(extracted_text or "")
        excerpt = ""
        if raw:
            remaining = max(0, budget - len(digest_text))
            if remaining > 300:
                head_budget = int(remaining * 0.65)
                head = raw[:head_budget]
                tail_room = max(0, remaining - len(head) - 16)
                tail = raw[-tail_room:] if tail_room > 200 else ""
                excerpt = head + ("\n[--truncated--]\n" + tail if tail else "")
            else:
                excerpt = raw[:remaining]

        return {"digest": digest_text, "excerpt": excerpt}

    @classmethod
    def _backfill_from_parsed(cls, parsed_data, result, extracted_text=""):
        """Fill empty report arrays from the deterministic parsed data.

        Llama-3.1-8b-instant occasionally returns only the numeric scores and
        omits the arrays, even with a strict prompt. Rather than showing empty
        cards, we synthesise conservative values from the parsed fields so the
        dashboard always renders a complete report. Model output is always
        preferred; only completely empty arrays are backfilled.
        """
        parsed = parsed_data or {}
        raw_text = extracted_text or ""

        # --- ats_breakdown -----------------------------------------------------
        if not result.get("ats_breakdown"):
            skills = parsed.get("skills") or []
            projects = parsed.get("projects") or []
            experience = parsed.get("experience") or []
            education = parsed.get("education") or []
            has_contact = bool(parsed.get("email") or parsed.get("phone"))
            result["ats_breakdown"] = [
                {"name": "Contact", "score": 100 if has_contact else 40,
                 "tip": "Add an email and phone number so recruiters can reach you."},
                {"name": "Skills", "score": 70 if skills else 30,
                 "tip": "List more role-specific technologies and tools."},
                {"name": "Projects", "score": 80 if projects else 40,
                 "tip": "Describe projects with the technologies and outcomes used."},
                {"name": "Experience", "score": 75 if experience else 35,
                 "tip": "Quantify achievements with metrics and action verbs."},
                {"name": "Education", "score": 80 if education else 45,
                 "tip": "Include your degree, institution, and year of study."},
                {"name": "Keyword match", "score": result.get("keyword_match", 60),
                 "tip": "Mirror the exact wording used in job descriptions."},
            ][:_ARRAY_LIMITS["ats_breakdown"]]

        # --- matched_skills ------------------------------------------------------
        if not result.get("matched_skills") and parsed.get("skills"):
            result["matched_skills"] = [
                {"name": skill, "reason": "Listed in your resume skills section.",
                 "importance": "High", "market_demand": "In-demand"}
                for skill in (parsed.get("skills") or [])[:_ARRAY_LIMITS["matched_skills"]]
            ]

        # --- keyword_analysis -----------------------------------------------------
        if not result.get("keyword_analysis") and parsed.get("skills"):
            result["keyword_analysis"] = [
                {"name": skill, "matched": 100, "missing": 0}
                for skill in (parsed.get("skills") or [])[:_ARRAY_LIMITS["keyword_analysis"]]
            ]

        # --- sections ------------------------------------------------------------
        if not result.get("sections"):
            def present(section):
                return bool(parsed.get(section))

            rows = [
                ("Contact", present("email") or present("phone"), 100, 55,
                 "Contact information present.", "Add both email and phone so recruiters can reach you."),
                ("Summary", present("summary"), 80, 35,
                 "Summary/objective section detected.", "Add a concise summary with your target role and top strengths."),
                ("Skills", bool(parsed.get("skills")), 85, 35,
                 "Skills section detected.", "Expand the skills list with role-relevant technologies."),
                ("Projects", bool(parsed.get("projects")), 80, 35,
                 "Projects section detected.", "Add a measurable outcome to each project."),
                ("Experience", bool(parsed.get("experience")), 80, 35,
                 "Experience section detected.", "Add quantified achievements and action verbs."),
                ("Education", bool(parsed.get("education")), 85, 40,
                 "Education section detected.", "Add institution, degree, and year of study."),
                ("Certifications", bool(parsed.get("certifications")), 75, 35,
                 "Certifications detected.", "Add relevant certifications for the target role."),
                ("Languages", bool(parsed.get("languages")), 70, 35,
                 "Languages detected.", "Add languages for multilingual roles."),
                ("Achievements", bool(parsed.get("achievements")), 70, 35,
                 "Achievements detected.", "Add measurable awards and recognitions."),
                ("Interests", bool(parsed.get("interests")), 65, 35,
                 "Interests detected.", "Add hobbies that reinforce personal brand."),
            ]
            sections = []
            for name, is_present, full_score, partial, strength, recommendation in rows:
                sections.append({
                    "name": name,
                    "score": full_score if is_present else partial,
                    "strength": strength,
                    "recommendation": recommendation,
                })
            result["sections"] = sections[:_ARRAY_LIMITS["sections"]]

        # --- resume_strength ------------------------------------------------------
        if not result.get("resume_strength"):
            strengths = []
            if parsed.get("skills"):
                strengths.append({"name": "Technical breadth", "score": 80,
                                  "recommendation": "Keep skills aligned to your target role."})
            if parsed.get("projects"):
                strengths.append({"name": "Project work", "score": 75,
                                  "recommendation": "Add outcome metrics to each project."})
            if parsed.get("experience"):
                strengths.append({"name": "Professional experience", "score": 75,
                                  "recommendation": "Quantify achievements with numbers."})
            if parsed.get("summary"):
                strengths.append({"name": "Summary/objective", "score": 75,
                                  "recommendation": "Tighten summary with target role keywords."})
            if not strengths:
                strengths.append({"name": "Foundation", "score": 60,
                                  "recommendation": "Add skills, projects, and experience to strengthen the resume."})
            result["resume_strength"] = strengths[:_ARRAY_LIMITS["resume_strength"]]

        # --- suggestions -----------------------------------------------------------
        if not result.get("suggestions"):
            suggestions = []
            if not (parsed.get("email") or parsed.get("phone")):
                suggestions.append({"priority": "high", "title": "Add contact details",
                                    "example": "Add an email and phone number at the top of the resume.",
                                    "estimated_ats_increase": 10})
            if not cls._has_summary(parsed, raw_text):
                suggestions.append({"priority": "high", "title": "Add a professional summary",
                                    "example": "Write 2-3 lines summarising your target role, top skills, and impact.",
                                    "estimated_ats_increase": 7})
            if not parsed.get("skills"):
                suggestions.append({"priority": "high", "title": "Add a skills section",
                                    "example": "List 6-10 technologies relevant to your target role.",
                                    "estimated_ats_increase": 8})
            if not parsed.get("projects"):
                suggestions.append({"priority": "medium", "title": "Add project details",
                                    "example": "Describe 2-3 projects with tech stack and outcomes.",
                                    "estimated_ats_increase": 5})
            if not parsed.get("experience"):
                suggestions.append({"priority": "medium", "title": "Add work experience",
                                    "example": "Include internships or jobs with quantified achievements.",
                                    "estimated_ats_increase": 5})
            if not suggestions:
                suggestions.append({"priority": "medium", "title": "Quantify your impact",
                                    "example": "Replace descriptive bullets with numbers and percentages.",
                                    "estimated_ats_increase": 5})
            result["suggestions"] = suggestions[:_ARRAY_LIMITS["suggestions"]]

        return result

    @staticmethod
    def _cache_key(digest):
        raw = json.dumps(digest, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def _cache_get(cls, key):
        ttl = int(current_app.config.get("GROQ_CACHE_TTL", 3600) or 3600)
        now = time.monotonic()
        with _cache_lock:
            entry = _cache.get(key)
            if entry and entry[0] > now:
                return entry[1]
            if entry:
                _cache.pop(key, None)
        return None

    @classmethod
    def _cache_set(cls, key, value):
        ttl = int(current_app.config.get("GROQ_CACHE_TTL", 3600) or 3600)
        with _cache_lock:
            if len(_cache) >= 200:
                # Drop the oldest entries to keep memory bounded.
                oldest = sorted(_cache.items(), key=lambda kv: kv[1][0])[:40]
                for old_key, _ in oldest:
                    _cache.pop(old_key, None)
            _cache[key] = (time.monotonic() + ttl, value)

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(digest, target_role="", job_description=""):
        return (
            "RESUME CONTENT (structured digest):\n"
            f"{digest['digest'] or 'No structured data available.'}\n\n"
            "RAW EXTRACTED TEXT (truncated excerpt):\n"
            f"{digest['excerpt'] or 'Not available.'}\n\n"
            "Return the JSON object described in the system instructions."
        )

    # ------------------------------------------------------------------
    # Response parsing & validation
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(content):
        """Return the JSON object from the model response, tolerating fences."""
        cleaned = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            raise ValueError("AI response is not a JSON object.")
        return data

    @classmethod
    def _normalise(cls, payload):
        """Clamp numeric fields, coerce arrays, and bound list lengths."""
        result = {}

        def to_int(value, default=0, lo=0, hi=100):
            try:
                num = int(float(value))
            except (TypeError, ValueError):
                return default
            return max(lo, min(hi, num))

        def capped(key):
            return _ARRAY_LIMITS.get(key, 6)

        result["ats_score"] = to_int(payload.get("ats_score"), 0)
        result["confidence"] = to_int(payload.get("confidence"), 0)
        result["keyword_match"] = to_int(payload.get("keyword_match"), 0)

        # ats_breakdown
        breakdown = []
        for item in payload.get("ats_breakdown") or []:
            if not isinstance(item, dict):
                continue
            breakdown.append({
                "name": str(item.get("name") or "Category"),
                "score": to_int(item.get("score")),
                "tip": str(item.get("tip") or ""),
            })
        result["ats_breakdown"] = breakdown[: capped("ats_breakdown")]

        # matched_skills
        matched = []
        for item in payload.get("matched_skills") or []:
            if isinstance(item, str):
                item = {"name": item}
            if not isinstance(item, dict):
                continue
            matched.append({
                "name": str(item.get("name") or ""),
                "reason": str(item.get("reason") or ""),
                "importance": str(item.get("importance") or ""),
                "market_demand": str(item.get("market_demand") or ""),
            })
        result["matched_skills"] = [m for m in matched if m["name"]][: capped("matched_skills")]

        # missing_skills & recommended_skills
        for key in ("missing_skills", "recommended_skills"):
            items = []
            for item in payload.get(key) or []:
                if isinstance(item, str):
                    item = {"name": item}
                if not isinstance(item, dict):
                    continue
                items.append({
                    "name": str(item.get("name") or ""),
                    "reason": str(item.get("reason") or ""),
                })
            result[key] = [i for i in items if i["name"]][: capped(key)]

        # keyword_analysis
        keywords = []
        for item in payload.get("keyword_analysis") or []:
            if isinstance(item, str):
                item = {"name": item}
            if not isinstance(item, dict):
                continue
            keywords.append({
                "name": str(item.get("name") or ""),
                "matched": to_int(item.get("matched")),
                "missing": to_int(item.get("missing")),
            })
        result["keyword_analysis"] = [k for k in keywords if k["name"]][: capped("keyword_analysis")]

        # sections
        sections = []
        for item in payload.get("sections") or []:
            if not isinstance(item, dict):
                continue
            sections.append({
                "name": str(item.get("name") or "Section"),
                "score": to_int(item.get("score")),
                "strength": str(item.get("strength") or ""),
                "recommendation": str(item.get("recommendation") or ""),
            })
        result["sections"] = sections[: capped("sections")]

        # resume_strength
        strength = []
        for item in payload.get("resume_strength") or []:
            if not isinstance(item, dict):
                continue
            strength.append({
                "name": str(item.get("name") or "Strength"),
                "score": to_int(item.get("score")),
                "recommendation": str(item.get("recommendation") or ""),
            })
        result["resume_strength"] = strength[: capped("resume_strength")]

        # suggestions
        suggestions = []
        for item in payload.get("suggestions") or []:
            if isinstance(item, str):
                item = {"title": item}
            if not isinstance(item, dict):
                continue
            priority = str(item.get("priority") or "medium").lower()
            if priority not in ("high", "medium", "low"):
                priority = "medium"
            suggestions.append({
                "priority": priority,
                "title": str(item.get("title") or item.get("reason") or "Suggestion"),
                "example": str(item.get("example") or ""),
                "estimated_ats_increase": to_int(item.get("estimated_ats_increase"), 0, 0, 20),
            })
        result["suggestions"] = suggestions[: capped("suggestions")]

        return result

    @staticmethod
    def extract_ai_fields(analysis):
        """Return only the AI-generated fields from a merged analysis dict."""
        if not isinstance(analysis, dict):
            return {}
        return {field: analysis[field] for field in AI_FIELDS if field in analysis}

