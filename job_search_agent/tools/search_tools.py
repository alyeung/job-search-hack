"""Google ADK Multi-Source Job Discovery Tools (Greenhouse, Ashby, LinkedIn)."""

from __future__ import annotations

from typing import Any

from src.fetchers.ashby import fetch_ashby_jobs
from src.fetchers.greenhouse import fetch_greenhouse_jobs
from src.fetchers.linkedin import fetch_linkedin_jobs
from src.profile import load_candidate_profile


def search_greenhouse_jobs(
    companies: list[str] | None = None,
    profile_path: str = "candidate_profile.json",
) -> dict[str, Any]:
    """Fetch live role- and location-matched jobs from Greenhouse ATS boards."""
    try:
        profile = load_candidate_profile(profile_path)
        prefs = profile.get("search_preferences", {})
        targets = companies or prefs.get("target_boards", {}).get("greenhouse", [])
        jobs = fetch_greenhouse_jobs(
            companies=targets,
            keyword_filter=prefs.get("role_title_include_keywords"),
            exclude_keywords=prefs.get("role_title_exclude_keywords"),
            location_filter=prefs.get("location_keywords"),
        )
        return {"status": "success", "source": "greenhouse", "count": len(jobs), "jobs": jobs}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def search_ashby_jobs(
    companies: list[str] | None = None,
    profile_path: str = "candidate_profile.json",
) -> dict[str, Any]:
    """Fetch live role- and location-matched jobs from Ashby ATS boards (e.g., OpenAI, Linear, Ramp)."""
    try:
        profile = load_candidate_profile(profile_path)
        prefs = profile.get("search_preferences", {})
        targets = companies or prefs.get("target_boards", {}).get("ashby", [])
        jobs = fetch_ashby_jobs(
            companies=targets,
            keyword_filter=prefs.get("role_title_include_keywords"),
            exclude_keywords=prefs.get("role_title_exclude_keywords"),
            location_filter=prefs.get("location_keywords"),
        )
        return {"status": "success", "source": "ashby", "count": len(jobs), "jobs": jobs}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def search_linkedin_jobs(
    query: str = "Principal Product Manager Cloud",
    location: str = "Seattle, WA",
    max_results: int = 5,
    profile_path: str = "candidate_profile.json",
) -> dict[str, Any]:
    """Search live LinkedIn job postings with prompt-injection sanitization and salary extraction."""
    try:
        profile = load_candidate_profile(profile_path)
        prefs = profile.get("search_preferences", {})
        jobs = fetch_linkedin_jobs(
            search_queries=[query],
            locations=[location],
            keyword_filter=prefs.get("role_title_include_keywords"),
            exclude_keywords=prefs.get("role_title_exclude_keywords"),
            location_filter=prefs.get("location_keywords"),
            max_per_query=max_results,
            fetch_details=True,
        )
        return {"status": "success", "source": "linkedin", "count": len(jobs), "jobs": jobs}
    except Exception as e:
        return {"status": "error", "error": str(e)}
