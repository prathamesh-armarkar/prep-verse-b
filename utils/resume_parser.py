"""Deterministic, non-AI parsing helpers for common resume layouts."""

import re


SECTION_HEADERS = {
    "education": {"education", "academic background", "academics"},
    "experience": {
        "experience", "work experience", "professional experience", "employment history",
        "internships", "freelancing", "freelancing /", "freelancing / internships",
    },
    "projects": {"projects", "personal projects", "academic projects", "project experience", "project details", "projects / achievements"},
    "skills": {"skills", "technical skills", "core competencies", "technologies", "skills & tools", "skills / proficiency"},
    "certifications": {"certifications", "certificates", "licenses and certifications", "courses", "certification"},
    "languages": {"languages", "language proficiency"},
    "links": {"links", "links / url", "url", "links/url", "profiles"},
}

# Tokens that are bullet/rendering artifacts from PDF text extraction.
# NOTE: "links / url" / "links/url" are NOT noise - they are legitimate
# section headers. Filtering them caused the LINKS boundary to disappear,
# which let portfolio/LinkedIn lines leak into the projects section.
# "freelancing" / "freelancing /" are handled as experience headers instead
# so a wrapped "Freelancing /" + "Internships" header is recognised.
NOISE_TOKENS = {
    ",%v%", "%v%", "skilled", "intermediate", "basic", "coursework:",
    "live portfolio",
}

# Bump when the parsing strategy changes so stored rows can be upgraded
# lazily (see ResumeService._ensure_current_analysis).
PARSER_VERSION = 2

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d{1,3}[ .-]?)?(?:\(?\d{2,4}\)?[ .-]?)?\d{3,5}[ .-]\d{4}(?!\w)")
LINKEDIN_PATTERN = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9_\-/%]+", re.I)
GITHUB_PATTERN = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9_\-]+", re.I)
NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z .'-]{1,80}$")


def _normalise_header(line):
    return re.sub(r"[:\-–—]+$", "", line.strip().lower())


def _section_for_header(line):
    candidate = _normalise_header(line)
    for section, names in SECTION_HEADERS.items():
        if candidate in names:
            return section
    return None


def _clean_lines(text):
    lines = []
    for line in text.splitlines():
        line = line.replace(",%V%", ",").replace("%V%", ",")  # bullet rendering artifacts
        line = line.replace("\u00b7", ",")                    # middle-dot bullet
        line = re.sub(r"\s+", " ", line).strip(" \t\uf0b7•|-")
        if line and line.lower() not in NOISE_TOKENS:
            lines.append(line)
    return lines


def _extract_name(lines):
    for line in lines[:8]:
        if _section_for_header(line) or "@" in line or re.search(r"https?://|linkedin|github|\d{3}", line, re.I):
            continue
        if NAME_PATTERN.match(line) and len(line.split()) >= 2:
            return line
    return None


def _split_items(lines):
    items = []
    for line in lines:
        for item in re.split(r"\s*[,;|\u00b7]\s*", line):
            item = item.strip()
            if not item or item.lower() in NOISE_TOKENS:
                continue
            if item and item not in items:
                items.append(item)
    return items


# ---------------------------------------------------------------------------
# Project entry grouping
# ---------------------------------------------------------------------------
# PDF text extraction splits one visual project entry into multiple physical
# lines: a title line, a tech-stack line, and one or more description lines.
# Storing every line as its own "project" inflated project_count from 4 to
# ~20 on real resumes. These helpers re-join those lines into discrete
# entries so counts and summaries reflect the true number of projects.

_PROJECT_TITLE_DASH = re.compile(r"\s[–—-]\s")
_PROJECT_TITLE_COLON = re.compile(r"[:\u2022]\s*\S")
_PROJECT_TECH_HINT = re.compile(
    r"\b(python|java|javascript|typescript|react|node(?:\.js)?|flask|django|"
    r"mysql|postgresql|mongodb|sql|aws|docker|kubernetes|tensorflow|pytorch|"
    r"scikit|numpy|pandas|html|css|next(?:\.js)?|hibernate|jsp|opencv|ocr|"
    r"tesseract|scispacy|streamlit|tailwind|api|full-?stack)\b",
    re.I,
)


def _is_project_title(line):
    """Return True when a line looks like the start of a new project entry.

    A title line is short, not a wrapped sentence, and either contains a dash
    (e.g. "VYOM AI – Real-Time UPI Fraud Detection System") or a colon
    (e.g. "CypherAI: ...") or reads like a bare project name.
    """
    text = line.strip()
    if not text or len(text) > 80:
        return False
    # Wrapped description lines end with punctuation or are long sentences.
    if text.endswith((".", "…", "!?")):
        return False
    # A tech-stack-only line (all hint tokens) is a continuation, not a title.
    if _PROJECT_TECH_HINT.search(text) and not _PROJECT_TITLE_DASH.search(text) and not _PROJECT_TITLE_COLON.search(text):
        return False
    if _PROJECT_TITLE_DASH.search(text) or _PROJECT_TITLE_COLON.search(text):
        return True
    # Bare short title with 2-7 words and no ending punctuation.
    return 2 <= len(text.split()) <= 7


def _parse_section_entries(lines):
    """Group a section's physical lines into discrete multi-line entries.

    The first line always starts an entry. A later line starts a new entry
    only when it looks like a project title; otherwise it is appended to the
    current entry (wrapped descriptions are re-joined with a space).
    """
    entries = []
    current = []
    for line in lines:
        if not line.strip():
            continue
        if current and _is_project_title(line):
            entries.append(" ".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        entries.append(" ".join(current).strip())
    return [entry for entry in entries if entry]


def _filter_link_lines(lines):
    """Drop lines that are clearly social/portfolio links, not projects."""
    urlish = re.compile(r"(https?://|linkedin\.com/in|github\.com|\.vercel\.app|\.github\.io)", re.I)
    return [line for line in lines if not urlish.search(line)]


def parse_resume(text):
    """Return a stable JSON-serialisable representation of a resume's contents."""
    lines = _clean_lines(text)
    sections = {key: [] for key in SECTION_HEADERS}
    current_section = None
    for line in lines:
        header = _section_for_header(line)
        if header:
            current_section = header
            continue
        if current_section:
            sections[current_section].append(line)

    email = EMAIL_PATTERN.search(text)
    phone = PHONE_PATTERN.search(text)
    linkedin = LINKEDIN_PATTERN.search(text)
    github = GITHUB_PATTERN.search(text)
    return {
        "name": _extract_name(lines),
        "email": email.group(0) if email else None,
        "phone": phone.group(0).strip() if phone else None,
        "linkedin": linkedin.group(0) if linkedin else None,
        "github": github.group(0) if github else None,
        "skills": _split_items(sections["skills"]),
        "education": sections["education"],
        "experience": sections["experience"],
        "projects": _parse_section_entries(_filter_link_lines(sections["projects"])),
        "certifications": sections["certifications"],
        "languages": _split_items(sections["languages"]),
        "parser_version": PARSER_VERSION,
    }

