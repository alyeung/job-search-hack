"""
CareerOS Integration (https://app.thecareeros.com/app/preferences)
Provides bidirectional integration between CareerOS and the AI Job Search Agent:
1. Inbound (`sync_preferences_from_careeros` / `import_careeros_preferences_text`):
   Pulls or parses a student's CareerOS Preferences (target roles, locations, industries,
   and target companies) and updates `candidate_profile.json` automatically.
2. Outbound (`export_matches_for_careeros`):
   Exports top-ranked job matches, networking search links (Haas/UW alumni filters),
   and ready-to-send outreach notes into `reports/careeros_tracker_export.csv` and
   `data/careeros_sync_payload.json` (plus optional API push when CAREEROS_BEARER_TOKEN is set).
"""

import csv
from datetime import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus
import requests

from src.evaluators.fit_evaluator import _call_gemini_json

logger = logging.getLogger(__name__)

CAREEROS_PREFERENCES_URL = "https://app.thecareeros.com/app/preferences"
CAREEROS_API_CANDIDATES = [
    "https://api.thecareeros.com/v1/user/preferences",
    "https://app.thecareeros.com/api/user/preferences",
    "https://app.thecareeros.com/api/v1/preferences",
]


def sync_preferences_from_careeros(
    profile: Dict[str, Any],
    profile_path: Path,
    bearer_token: Optional[str] = None,
    cookie_str: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Attempt live pull from CareerOS (`https://app.thecareeros.com/app/preferences`)
    using `CAREEROS_BEARER_TOKEN` or `CAREEROS_SESSION_COOKIE` from `.env`.
    If authenticated JSON is returned, merges target roles, locations, domains, and
    companies into `candidate_profile.json`.
    """
    token = bearer_token or os.environ.get("CAREEROS_BEARER_TOKEN")
    cookie = cookie_str or os.environ.get("CAREEROS_SESSION_COOKIE")

    if not token and not cookie:
        return {
            "status": "skipped_no_credentials",
            "preferences_url": CAREEROS_PREFERENCES_URL,
            "message": (
                "No CAREEROS_BEARER_TOKEN or CAREEROS_SESSION_COOKIE set in .env. "
                "Using local candidate_profile.json preferences (or run `--import-careeros <file>` "
                "to parse exported/copied CareerOS preferences)."
            ),
        }

    headers: Dict[str, str] = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "JobSearchAgent-CareerOS-Sync/1.0",
    }
    if token:
        headers["Authorization"] = (
            token if token.lower().startswith("bearer ") else f"Bearer {token}"
        )
    if cookie:
        headers["Cookie"] = cookie

    raw_payload: Optional[Dict[str, Any]] = None
    for endpoint in CAREEROS_API_CANDIDATES:
        try:
            resp = requests.get(endpoint, headers=headers, timeout=10)
            if resp.status_code == 200 and "json" in resp.headers.get("Content-Type", "").lower():
                raw_payload = resp.json()
                break
        except Exception as e:
            logger.debug("CareerOS endpoint %s probe failed: %s", endpoint, e)

    if not raw_payload:
        return {
            "status": "sso_or_manual_export_needed",
            "preferences_url": CAREEROS_PREFERENCES_URL,
            "message": (
                "CareerOS uses university SSO (e.g., Berkeley Haas CalNet). "
                "To import your CareerOS preferences without API tokens, copy the text or JSON from "
                f"{CAREEROS_PREFERENCES_URL} into a file and run: python3 main.py --import-careeros <file>"
            ),
        }

    updated_fields = _merge_careeros_payload_into_profile(profile, raw_payload)
    with profile_path.open("w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)

    return {
        "status": "synced",
        "preferences_url": CAREEROS_PREFERENCES_URL,
        "updated_fields": updated_fields,
        "message": f"Successfully synced CareerOS preferences into {profile_path.name}.",
    }


def import_careeros_preferences_file(
    source_file: str | Path,
    profile: Dict[str, Any],
    profile_path: Path,
) -> Dict[str, Any]:
    """
    Parse a saved JSON, HTML, or copy-pasted text dump from
    `https://app.thecareeros.com/app/preferences` and merge it into `candidate_profile.json`.
    Makes it effortless for any student on CareerOS to customize the agent in seconds.
    """
    src = Path(source_file)
    if not src.exists():
        raise FileNotFoundError(f"CareerOS import file not found: {src}")

    raw_text = src.read_text(encoding="utf-8").strip()

    # 1. Try direct JSON parse first
    parsed_data: Optional[Dict[str, Any]] = None
    try:
        parsed_data = json.loads(raw_text)
    except Exception:
        pass

    # 2. If plain text / HTML copied from https://app.thecareeros.com/app/preferences,
    #    use Gemini LLM (if key available) or structured heuristic parser
    if not parsed_data:
        llm_extracted = _call_gemini_json(
            f"Extract the student's career preferences from this CareerOS preferences page text "
            f"({CAREEROS_PREFERENCES_URL}) into JSON with keys: "
            f"`target_roles` (list of strings), `target_locations` (list of strings), "
            f"`target_domains` (list of strings), `target_companies` (list of strings).\n\n"
            f"TEXT:\n{raw_text[:8000]}"
        )
        if llm_extracted and isinstance(llm_extracted, dict):
            parsed_data = llm_extracted
        else:
            parsed_data = _parse_careeros_text_heuristically(raw_text)

    updated = _merge_careeros_payload_into_profile(profile, parsed_data)
    with profile_path.open("w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)

    return {
        "status": "imported",
        "source_file": str(src),
        "updated_fields": updated,
        "profile_path": str(profile_path),
    }


def _parse_careeros_text_heuristically(raw_text: str) -> Dict[str, List[str]]:
    """Fallback parser for copy-pasted text from CareerOS Preferences page."""
    result: Dict[str, List[str]] = {
        "target_roles": [],
        "target_locations": [],
        "target_domains": [],
        "target_companies": [],
    }
    current_key: Optional[str] = None
    for raw_line in raw_text.splitlines():
        line = raw_line.strip(" •-*,\t")
        if not line:
            continue
        low = line.lower()
        if any(h in low for h in ("role", "job title", "position", "function")):
            current_key = "target_roles"
            if ":" in line:
                vals = [v.strip() for v in line.split(":", 1)[1].split(",") if v.strip()]
                result["target_roles"].extend(vals)
            continue
        if any(h in low for h in ("location", "city", "cities", "geography", "country")):
            current_key = "target_locations"
            if ":" in line:
                vals = [v.strip() for v in line.split(":", 1)[1].split(",") if v.strip()]
                result["target_locations"].extend(vals)
            continue
        if any(h in low for h in ("industry", "industries", "sector", "domain")):
            current_key = "target_domains"
            if ":" in line:
                vals = [v.strip() for v in line.split(":", 1)[1].split(",") if v.strip()]
                result["target_domains"].extend(vals)
            continue
        if any(h in low for h in ("compan", "employer", "organization")):
            current_key = "target_companies"
            if ":" in line:
                vals = [v.strip() for v in line.split(":", 1)[1].split(",") if v.strip()]
                result["target_companies"].extend(vals)
            continue

        if current_key and len(line) < 80:
            result[current_key].append(line)

    return result


def _merge_careeros_payload_into_profile(
    profile: Dict[str, Any],
    payload: Dict[str, Any],
) -> List[str]:
    """Merge extracted CareerOS preferences into `candidate_profile.json` without losing existing data."""
    updated_sections: List[str] = []
    data = payload.get("data", payload) if isinstance(payload, dict) else {}

    roles = (
        data.get("target_roles")
        or data.get("roles")
        or data.get("jobTitles")
        or data.get("functions")
        or []
    )
    if roles and isinstance(roles, list):
        existing = profile.get("target_roles", [])
        for r in roles:
            if isinstance(r, str) and r not in existing:
                existing.append(r)
        profile["target_roles"] = existing
        updated_sections.append("target_roles")

    locations = (
        data.get("target_locations")
        or data.get("locations")
        or data.get("cities")
        or data.get("geographies")
        or []
    )
    if locations and isinstance(locations, list):
        existing_locs = profile.get("target_locations", [])
        for loc in locations:
            if isinstance(loc, str) and loc not in existing_locs:
                existing_locs.append(loc)
        profile["target_locations"] = existing_locs
        updated_sections.append("target_locations")

    domains = (
        data.get("target_domains")
        or data.get("industries")
        or data.get("sectors")
        or []
    )
    if domains and isinstance(domains, list):
        existing_doms = profile.get("target_domains", [])
        for d in domains:
            if isinstance(d, str) and d not in existing_doms:
                existing_doms.append(d)
        profile["target_domains"] = existing_doms
        updated_sections.append("target_domains")

    companies = (
        data.get("target_companies")
        or data.get("companies")
        or data.get("employers")
        or []
    )
    if companies and isinstance(companies, list):
        prefs = profile.setdefault("search_preferences", {})
        tiers = prefs.setdefault("company_tiers", {})
        t1 = tiers.setdefault("tier_1_priority", [])
        for c in companies:
            if isinstance(c, str) and c not in t1:
                t1.append(c)
        updated_sections.append("search_preferences.company_tiers")

    careeros_meta = profile.setdefault("careeros_integration", {})
    careeros_meta["preferences_url"] = CAREEROS_PREFERENCES_URL
    careeros_meta["last_synced_at"] = datetime.now().isoformat(timespec="seconds")

    return updated_sections


def export_matches_for_careeros(
    evaluated_jobs: List[Dict[str, Any]],
    profile: Dict[str, Any],
    reports_dir: Path,
    data_dir: Path,
    top_n: int = 15,
) -> Dict[str, Path]:
    """
    Export ranked job matches and networking/outreach kits into CareerOS-compatible
    Job Tracker CSV (`reports/careeros_job_tracker.csv`) and JSON payload
    (`data/careeros_sync_payload.json`).
    Also generates pre-filled Alumni & Hiring Manager networking search URLs for CareerOS/LinkedIn.
    """
    csv_path = reports_dir / "careeros_job_tracker.csv"
    json_path = data_dir / "careeros_sync_payload.json"

    education = profile.get("education", [])
    primary_school = education[0].get("school", "UC Berkeley Haas") if education else ""
    careeros_cfg = profile.get("careeros_integration", {})
    default_stage = careeros_cfg.get("default_pipeline_stage", "Targeting")

    rows: List[Dict[str, Any]] = []
    for rank, ev in enumerate(evaluated_jobs[:top_n], start=1):
        company = ev.get("company", "")
        title = ev.get("title", "")
        kit = ev.get("application_kit", {})
        critique = ev.get("hiring_manager_critique", {})

        # Pre-built networking search query for CareerOS Contacts / LinkedIn Alumni
        networking_query = f"{company} Product Manager {primary_school.split(',')[0]}"
        linkedin_alumni_search = (
            f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(networking_query)}"
        )

        row = {
            "Rank": rank,
            "CareerOS_Stage": default_stage,
            "Company": company,
            "Company_Tier": ev.get("company_tier", ""),
            "Job_Title": title,
            "Location": ev.get("location", ""),
            "Salary_Range": ev.get("salary_range", "Not Disclosed"),
            "Fit_Score": ev.get("total_score", 0),
            "Application_URL": ev.get("url", ""),
            "CareerOS_Preferences_Source": careeros_cfg.get(
                "preferences_url", CAREEROS_PREFERENCES_URL
            ),
            "Alumni_Contact_Search_URL": linkedin_alumni_search,
            "Why_You_Fit": ev.get("why_you_fit", ""),
            "HM_Objection_To_Preempt": critique.get("likely_objection", ""),
            "Outreach_Draft": (kit.get("outreach_message", "") or "").replace("\n", " "),
        }
        rows.append(row)

    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    payload = {
        "careeros_preferences_url": careeros_cfg.get(
            "preferences_url", CAREEROS_PREFERENCES_URL
        ),
        "candidate_name": profile.get("name"),
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "pipeline_stage": default_stage,
        "records": rows,
    }
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return {"csv_path": csv_path, "json_path": json_path}
