"""
Candidate Profile Loader & Normalizer
Ensures the agent works for ANY user profile JSON without hardcoding personal details.
"""

import json
from pathlib import Path
import shutil
from typing import Any, Dict, List

DEFAULT_PROFILE_PATH = Path("candidate_profile.json")
TEMPLATE_PROFILE_PATH = Path("candidate_profile.template.json")


def load_candidate_profile(
    profile_path: str | Path = DEFAULT_PROFILE_PATH,
) -> Dict[str, Any]:
    """
    Load a candidate profile JSON and enrich missing optional sections
    with dynamic defaults derived from `target_roles` and `target_locations`.
    """
    path = Path(profile_path)
    if not path.exists():
        if path == DEFAULT_PROFILE_PATH and TEMPLATE_PROFILE_PATH.exists():
            shutil.copyfile(TEMPLATE_PROFILE_PATH, path)
            print(
                f"[Setup] Created '{path}' from '{TEMPLATE_PROFILE_PATH}'. "
                f"Customize '{path}' with your own resume & preferences!"
            )
        else:
            raise FileNotFoundError(
                f"Candidate profile not found at '{path}'. "
                f"Run `python3 main.py --init-profile {path}` to create one from the template."
            )

    with path.open("r", encoding="utf-8") as f:
        profile: Dict[str, Any] = json.load(f)

    # Dynamically derive search_preferences if a user provides a minimal profile
    search_prefs = profile.setdefault("search_preferences", {})

    if not search_prefs.get("role_title_include_keywords"):
        target_roles: List[str] = profile.get("target_roles", [])
        derived_keywords = []
        for role in target_roles:
            derived_keywords.append(role.lower())
            # Also extract the core role noun phrase (e.g., "Product Manager" from "Principal Product Manager")
            for prefix in (
                "principal ",
                "staff ",
                "senior ",
                "lead ",
                "group ",
                "director of ",
                "director, ",
                "vp of ",
            ):
                if role.lower().startswith(prefix):
                    core = role.lower()[len(prefix) :].strip()
                    if core and core not in derived_keywords:
                        derived_keywords.append(core)
        search_prefs["role_title_include_keywords"] = derived_keywords or [
            "product manager"
        ]

    search_prefs.setdefault(
        "role_title_exclude_keywords",
        ["intern", "internship", "recruiter"],
    )

    if not search_prefs.get("location_keywords"):
        target_locs: List[str] = profile.get("target_locations", [])
        loc_keywords = []
        for loc in target_locs:
            base_city = loc.split(",")[0].strip().lower()
            if base_city:
                loc_keywords.append(base_city)
        search_prefs["location_keywords"] = loc_keywords or ["remote"]

    target_boards = search_prefs.setdefault("target_boards", {})
    target_boards.setdefault(
        "greenhouse",
        [
            "anthropic",
            "stripe",
            "databricks",
            "cloudflare",
            "datadog",
            "figma",
            "gitlab",
            "brex",
        ],
    )
    target_boards.setdefault(
        "ashby",
        ["openai", "linear", "ramp", "supabase", "perplexity", "cohere"],
    )

    # Constraints & compensation defaults
    constraints = profile.setdefault("constraints_and_comp", {})
    constraints.setdefault("min_base_salary_usd", 0)
    constraints.setdefault("target_base_salary_usd", 0)
    constraints.setdefault("preferred_seniority", [])
    constraints.setdefault("dealbreakers", [])

    # Scoring weights (sum to 100)
    weights = profile.setdefault("scoring_weights", {})
    weights.setdefault("role_and_seniority_fit", 30)
    weights.setdefault("domain_and_technical_fit", 30)
    weights.setdefault("candidate_edge_and_pedigree", 25)
    weights.setdefault("location_and_compensation_fit", 15)

    # Outreach positioning defaults
    outreach = profile.setdefault("outreach_and_positioning", {})
    outreach.setdefault("elevator_pitch", "")
    outreach.setdefault("alumni_and_network_hooks", [])

    # CareerOS integration defaults (https://app.thecareeros.com/app/preferences)
    careeros = profile.setdefault("careeros_integration", {})
    careeros.setdefault("enabled", True)
    careeros.setdefault("preferences_url", "https://app.thecareeros.com/app/preferences")
    careeros.setdefault("default_pipeline_stage", "Targeting")
    careeros.setdefault("auto_export_job_tracker_csv", True)

    return profile


def create_profile_from_template(output_path: str | Path) -> Path:
    """Create a new candidate profile JSON file from the generic template."""
    dest = Path(output_path)
    if dest.exists():
        raise FileExistsError(f"Profile file '{dest}' already exists.")

    if TEMPLATE_PROFILE_PATH.exists():
        shutil.copyfile(TEMPLATE_PROFILE_PATH, dest)
    else:
        default_data = load_candidate_profile(DEFAULT_PROFILE_PATH)
        with dest.open("w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=2)
    return dest
