"""
Ashby Jobs Fetcher
Fetches live jobs from companies using Ashby ATS (e.g., OpenAI, Linear, Ramp, Supabase, Perplexity).
Public API endpoint: https://api.ashbyhq.com/posting-api/job-board/{board_name}?includeCompensation=true
"""

import logging
from typing import Dict, List, Optional
import requests

try:
    from src.fetchers import (
        clean_html_text,
        extract_salary_band,
        matches_location,
        matches_role_title,
    )
except ImportError:
    from __init__ import (  # type: ignore
        clean_html_text,
        extract_salary_band,
        matches_location,
        matches_role_title,
    )

logger = logging.getLogger(__name__)

DEFAULT_ASHBY_COMPANIES = [
    "openai",
    "linear",
    "ramp",
    "supabase",
    "perplexity",
    "cohere",
    "langchain",
]

COMPANY_DISPLAY_NAMES = {
    "openai": "OpenAI",
    "linear": "Linear",
    "ramp": "Ramp",
    "supabase": "Supabase",
    "perplexity": "Perplexity",
    "cohere": "Cohere",
    "langchain": "LangChain",
}


def fetch_ashby_jobs(
    companies: Optional[List[str]] = None,
    keyword_filter: Optional[List[str]] = None,
    exclude_keywords: Optional[List[str]] = None,
    location_filter: Optional[List[str]] = None,
) -> List[Dict]:
    """Fetch live jobs from Ashby public job board API for a list of companies."""
    targets = companies or DEFAULT_ASHBY_COMPANIES
    include_terms = keyword_filter or [
        "product manager",
        "product management",
        "principal pm",
        "staff pm",
        "group pm",
        "technical pm",
        "director, product",
        "director of product",
        "head of product",
    ]
    exclude_terms = (
        exclude_keywords
        if exclude_keywords is not None
        else [
            "associate product manager",
            "intern",
            "product designer",
            "product marketing",
            "product counsel",
            "production",
        ]
    )
    all_jobs: List[Dict] = []

    for comp in targets:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{comp}?includeCompensation=true"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            jobs = data.get("jobs", [])

            for j in jobs:
                if not j.get("isListed", True):
                    continue
                title = j.get("title", "")
                if not matches_role_title(title, include_terms, exclude_terms):
                    continue

                primary_loc = j.get("location", "") or ""
                secondary_locs = [
                    loc.get("location", "")
                    for loc in j.get("secondaryLocations", [])
                    if isinstance(loc, dict) and loc.get("location")
                ]
                loc_parts = [p for p in [primary_loc] + secondary_locs if p]
                if j.get("isRemote") and not any("remote" in p.lower() for p in loc_parts):
                    loc_parts.append("Remote")
                loc_name = " | ".join(loc_parts) if loc_parts else "Not Specified"

                if location_filter and not matches_location(loc_name, location_filter):
                    continue

                plain_text = j.get("descriptionPlain", "") or clean_html_text(
                    j.get("descriptionHtml", "")
                )

                # Extract structured compensation from Ashby or fallback to regex
                comp_data = j.get("compensation") or {}
                comp_summary = comp_data.get("compensationTierSummary", "") or ""
                min_sal, max_sal, sal_str = extract_salary_band(
                    f"{comp_summary}\n{plain_text}"
                )

                company_display = COMPANY_DISPLAY_NAMES.get(
                    comp.lower(), comp.capitalize()
                )

                job_record = {
                    "source": "ashby",
                    "board_token": comp,
                    "company": company_display,
                    "title": title,
                    "department": j.get("department", "") or j.get("team", "") or "",
                    "location": loc_name,
                    "url": j.get("jobUrl", "") or j.get("applyUrl", ""),
                    "id": f"ashby_{comp}_{j.get('id')}",
                    "content": j.get("descriptionHtml", "") or plain_text,
                    "plain_text": plain_text,
                    "min_salary_usd": min_sal,
                    "max_salary_usd": max_sal,
                    "salary_range": sal_str,
                    "updated_at": j.get("publishedAt", ""),
                }
                all_jobs.append(job_record)
        except Exception as e:
            logger.warning("Error fetching Ashby jobs for %s: %s", comp, e)

    return all_jobs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing Ashby fetcher with OpenAI, Linear, Ramp...")
    jobs = fetch_ashby_jobs(["openai", "linear", "ramp"])
    print(f"Found {len(jobs)} matching jobs across test companies.")
    for job in jobs[:5]:
        print(
            f"- {job['company']}: {job['title']} ({job['location']}) | Salary: {job['salary_range']}"
        )
