"""Deterministic analysis of structured resume data; no AI or ATS scoring."""

import re


class ResumeAnalysisService:
    TECHNICAL_SKILLS = {
        "python", "java", "javascript", "typescript", "c", "c++", "c#", "sql",
        "html", "css", "react", "angular", "vue", "next.js", "nextjs", "tailwind",
        "tailwind css", "flask", "django", "fastapi", "express", "express.js",
        "node", "node.js", "mysql", "postgresql", "mongodb", "aws", "azure", "gcp",
        "git", "docker", "kubernetes", "tensorflow", "pytorch", "pandas", "numpy",
        "excel", "scikit-learn", "sklearn", "xgboost", "nlp", "scispacy",
        "computer vision", "opencv", "ocr", "jsp", "servlet", "rest api", "restful",
        "spring", "spring boot", "api development", "flask", "deep learning",
        "machine learning", "data visualization", "power bi", "tableau", "c++",
        "bootstrap", "jquery", "mongo", "redis", "graphql", "firebase", "selenium",
        "pytest", "unittest", "git", "github", "jira", "agile",
    }
    SOFT_SKILLS = {
        "communication", "leadership", "teamwork", "team player", "problem solving",
        "problem-solving", "adaptability", "time management", "critical thinking",
        "collaboration", "creativity", "presentation", "management",
    }
    TECHNOLOGY_TERMS = TECHNICAL_SKILLS | {"api", "rest", "machine learning", "firebase", "ocr", "nlp", "jsp"}

    # Category ordering is preserved for frontend display.
    SKILL_CATEGORIES = {
        "Programming": {
            "python", "java", "javascript", "typescript", "c", "c++", "c#", "sql",
            "kotlin", "go", "golang", "rust", "php", "ruby", "swift",
        },
        "Frontend": {
            "html", "css", "react", "next.js", "nextjs", "angular", "vue", "tailwind",
            "tailwind css", "bootstrap", "jquery", "redux", "sass", "scss", "typescript",
        },
        "Backend": {
            "flask", "django", "fastapi", "express", "express.js", "node", "node.js",
            "jsp", "servlet", "spring", "spring boot", "rest api", "restful", "api",
            "api development", "graphql", "firebase", "docker", "kubernetes", "aws",
            "azure", "gcp", "rest", "backend", "microservices",
        },
        "Database": {
            "mysql", "postgresql", "mongodb", "mongo", "sqlite", "oracle", "redis",
            "sql", "database", "dbms", "nosql", "dynamodb",
        },
        "AI / ML": {
            "python", "tensorflow", "pytorch", "pandas", "numpy", "scikit-learn",
            "sklearn", "xgboost", "nlp", "scispacy", "computer vision", "opencv",
            "machine learning", "deep learning", "ocr", "data visualization",
            "power bi", "tableau", "matplotlib", "seaborn", "ai", "ml", "nltk",
            "spacy", "llm", "genai", "generative ai", "data science",
        },
        "Tools & Others": {
            "git", "github", "docker", "kubernetes", "jira", "agile", "excel",
            "power bi", "tableau", "selenium", "pytest", "unittest", "word", "ppt",
            "postman", "figma", "linux", "ci/cd",
        },
    }
    # Normalise common skill aliases before categorising.
    SKILL_ALIASES = {
        "node": "node.js", "nodejs": "node.js", "express": "express.js",
        "next": "next.js", "sklearn": "scikit-learn", "reactjs": "react",
        "ml": "machine learning", "ai": "artificial intelligence",
        "tailwindcss": "tailwind css", "c++": "c++", "js": "javascript",
        "ts": "typescript", "mongo": "mongodb", "rest": "rest api",
    }
    DEGREE_PATTERNS = (
        ("PhD", 6, r"\b(ph\.?d|doctor(?:ate)?|dphil)\b"),
        ("MBA", 5, r"\bm\.?b\.?a\.?\b"),
        ("MCA", 5, r"\bm\.?c\.?a\.?\b"),
        ("MTech", 5, r"\bm\.?tech\b|master of technology"),
        ("Master's", 5, r"\b(m\.?s\.?c?|master(?:'s)?|m\.s\.)\b"),
        ("BTech", 4, r"\bb\.?tech\b|bachelor of technology"),
        ("BCA", 4, r"\bb\.?c\.?a\.?\b"),
        ("Bachelor's", 4, r"\b(b\.?s\.?c?|bachelor(?:'s)?)\b"),
        ("Diploma", 3, r"\bdiploma\b"),
        ("High School", 2, r"\b(high school|higher secondary|class (?:10|12))\b"),
    )

    @staticmethod
    def _items(parsed_data, field):
        value = parsed_data.get(field) or []
        return value if isinstance(value, list) else []

    @classmethod
    def analyze_contact(cls, parsed_data):
        values = {
            "email": bool(parsed_data.get("email")),
            "phone": bool(parsed_data.get("phone")),
            "linkedin": bool(parsed_data.get("linkedin")),
            "github": bool(parsed_data.get("github")),
            "portfolio": bool(parsed_data.get("portfolio")),
        }
        labels = {"email": "Email", "phone": "Phone", "linkedin": "LinkedIn", "github": "GitHub", "portfolio": "Portfolio"}
        return {
            "score": round(sum(values.values()) * 100 / len(values)),
            **values,
            "missing": [labels[key] for key, present in values.items() if not present],
        }

    @classmethod
    def analyze_skills(cls, parsed_data):
        skills = [str(skill).strip() for skill in cls._items(parsed_data, "skills") if str(skill).strip()]
        soft = [skill for skill in skills if skill.lower() in cls.SOFT_SKILLS]
        technical = [skill for skill in skills if skill not in soft]
        return {
            "total_skills": len(skills),
            "technical_skills": len(technical),
            "soft_skills": len(soft),
            "top_skills": skills[:5],
            "categories": cls.categorize_skills(skills),
        }

    @classmethod
    def categorize_skills(cls, skills):
        """Group skills into labelled buckets while preserving insertion order."""
        categories = {category: [] for category in cls.SKILL_CATEGORIES}
        seen = set()
        for skill in skills:
            normalized = cls.SKILL_ALIASES.get(skill.lower(), skill.lower())
            placed = False
            for category, keywords in cls.SKILL_CATEGORIES.items():
                if normalized in keywords:
                    display = cls.SKILL_ALIASES.get(skill.lower(), skill)
                    if display not in seen:
                        seen.add(display)
                        categories[category].append(display)
                    placed = True
                    break
            if not placed and skill not in seen and skill.lower() not in cls.SOFT_SKILLS:
                seen.add(skill)
                categories["Tools & Others"].append(skill)
        return {category: items for category, items in categories.items() if items}

    @classmethod
    def analyze_projects(cls, parsed_data):
        projects = [str(item).strip() for item in cls._items(parsed_data, "projects") if str(item).strip()]
        with_technologies = [project for project in projects if cls._contains_technology(project)]
        return {
            "project_count": len(projects),
            "projects_with_description": len(projects),
            "projects_with_technologies": len(with_technologies),
            "strong_projects": len(with_technologies),
            "project_summaries": [cls._project_summary(project) for project in projects],
        }

    @classmethod
    def _project_summary(cls, project):
        """Split a raw project line into name, tech stack, and strength status."""
        lower = project.lower()
        # Prefer a dash between the project name and its description.
        if re.search(r"\s-\s", project):
            name, _, description = project.partition(" - ")
        else:
            name, description = project, project
        # Trim bullet/prefix noise from the name.
        name = name.strip(" \t•|-:,").strip()
        if not name:
            name = "Untitled project"
        tech_terms = [term for term in cls.TECHNOLOGY_TERMS if re.search(rf"\b{re.escape(term)}\b", lower)]
        tech_terms = cls._dedupe_terms(tech_terms)
        has_description = len(description.strip()) > len(name.strip())
        has_tech = bool(tech_terms)
        if has_tech and has_description:
            status = "Strong"
        elif has_tech:
            status = "Good"
        else:
            status = "Needs work"
        return {
            "name": name,
            "description": description.strip(),
            "tech_stack": tech_terms,
            "status": status,
        }

    @staticmethod
    def _dedupe_terms(terms):
        """Remove alias duplicates (e.g. node + node.js) keeping the more specific term."""
        def key(term):
            return re.sub(r"[^a-z0-9]", "", term.lower())

        normalized = [{"term": term, "key": key(term)} for term in terms]
        # Keep the longest/most specific term when one key is a prefix of another.
        kept = []
        for item in normalized:
            more_specific = [
                other["term"] for other in normalized
                if other["key"] != item["key"] and other["key"].startswith(item["key"])
            ]
            if more_specific and item["term"] not in more_specific:
                continue
            if any(existing["key"] == item["key"] for existing in kept):
                continue
            kept.append(item)
        return [item["term"] for item in kept]

    @classmethod
    def analyze_experience(cls, parsed_data):
        experience = [str(item).strip() for item in cls._items(parsed_data, "experience") if str(item).strip()]
        internships = [item for item in experience if re.search(r"\bintern(?:ship)?\b", item, re.I)]
        return {"experience_count": len(experience), "internships": len(internships), "full_time": len(experience) - len(internships)}

    @classmethod
    def analyze_education(cls, parsed_data):
        education = [str(item).strip() for item in cls._items(parsed_data, "education") if str(item).strip()]
        highest = None
        highest_rank = 0
        for item in education:
            for degree, rank, pattern in cls.DEGREE_PATTERNS:
                if rank > highest_rank and re.search(pattern, item, re.I):
                    highest, highest_rank = degree, rank
        return {"highest_degree": highest, "education_count": len(education)}

    @classmethod
    def analyze_certifications(cls, parsed_data):
        return {"certification_count": len(cls._items(parsed_data, "certifications"))}

    @classmethod
    def analyze_languages(cls, parsed_data):
        languages = [str(item).strip() for item in cls._items(parsed_data, "languages") if str(item).strip()]
        return {"language_count": len(languages), "languages": languages}

    @classmethod
    def calculate_resume_completeness(cls, analysis):
        sections = {
            "Contact": analysis["contact_analysis"]["score"] > 0,
            "Skills": analysis["skills_analysis"]["total_skills"] > 0,
            "Projects": analysis["project_analysis"]["project_count"] > 0,
            "Experience": analysis["experience_analysis"]["experience_count"] > 0,
            "Education": analysis["education_analysis"]["education_count"] > 0,
            "Certifications": analysis["certification_analysis"]["certification_count"] > 0,
            "Languages": analysis["language_analysis"]["language_count"] > 0,
        }
        contact_score = analysis["contact_analysis"]["score"]
        other_scores = sum(100 for name, complete in sections.items() if name != "Contact" and complete)
        overall = round((contact_score + other_scores) / len(sections))
        return {
            "overall_completion": overall,
            "completed_sections": [name for name, complete in sections.items() if complete],
            "missing_sections": [name for name, complete in sections.items() if not complete],
        }

    @classmethod
    def generate_overview(cls, parsed_data, analysis):
        """Build a compact candidate overview for the dashboard header."""
        name = parsed_data.get("name")
        education = [str(item).strip() for item in cls._items(parsed_data, "education") if str(item).strip()]
        highest = None
        highest_rank = 0
        for item in education:
            for degree, rank, pattern in cls.DEGREE_PATTERNS:
                if rank > highest_rank and re.search(pattern, item, re.I):
                    highest, highest_rank = item, rank
        experience = [str(item).strip() for item in cls._items(parsed_data, "experience") if str(item).strip()]
        skills_analysis = analysis["skills_analysis"]
        return {
            "name": name,
            "highest_education": highest or (education[0] if education else None),
            "experience": experience[0] if experience else None,
            "project_count": analysis["project_analysis"]["project_count"],
            "technical_skill_count": skills_analysis["technical_skills"],
            "certification_count": analysis["certification_analysis"]["certification_count"],
        }

    @classmethod
    def generate_analysis(cls, parsed_data):
        analysis = {
            "contact_analysis": cls.analyze_contact(parsed_data),
            "skills_analysis": cls.analyze_skills(parsed_data),
            "project_analysis": cls.analyze_projects(parsed_data),
            "experience_analysis": cls.analyze_experience(parsed_data),
            "education_analysis": cls.analyze_education(parsed_data),
            "certification_analysis": cls.analyze_certifications(parsed_data),
            "language_analysis": cls.analyze_languages(parsed_data),
        }
        analysis["resume_completeness"] = cls.calculate_resume_completeness(analysis)
        analysis["overview"] = cls.generate_overview(parsed_data, analysis)
        return analysis

    @classmethod
    def _contains_technology(cls, text):
        lower_text = text.lower()
        return any(re.search(rf"\b{re.escape(term)}\b", lower_text) for term in cls.TECHNOLOGY_TERMS)
