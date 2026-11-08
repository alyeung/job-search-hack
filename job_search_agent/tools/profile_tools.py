"""Google ADK Profile & CareerOS Sync Tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.integrations.careeros import (
    import_careeros_preferences_file,
    sync_preferences_from_careeros,
)
from src.profile import DEFAULT_PROFILE_PATH, load_candidate_profile


def get_candidate_profile(
    profile_path: str = "candidate_profile.json",
) -> dict[str, Any]:
    """Load the active candidate profile JSON including target roles, locations, comp floor, and rubric weights."""
    try:
        profile = load_candidate_profile(profile_path)
        return {
            "status": "success",
            "profile_path": profile_path,
            "profile": profile,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def sync_careeros_preferences(
    profile_path: str = "candidate_profile.json",
    import_file: str = "",
) -> dict[str, Any]:
    """Sync or import candidate preferences from CareerOS (https://app.thecareeros.com/app/preferences)."""
    try:
        path = Path(profile_path or DEFAULT_PROFILE_PATH)
        profile = load_candidate_profile(path)
        if import_file.strip():
            res = import_careeros_preferences_file(import_file.strip(), profile, path)
            return {"status": "success", "sync_result": res}
        res = sync_preferences_from_careeros(profile, path)
        return {"status": "success", "sync_result": res}
    except Exception as e:
        return {"status": "error", "error": str(e)}
