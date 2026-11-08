"""
Greenhouse Jobs Fetcher
Fetches live jobs from companies using Greenhouse ATS.
Public API endpoint: https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
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

DEFAULT_GREENHOUSE_COMPANIES = [
    "anthropic",
    "stripe",
    "databricks",
    "cloudflare",
    "datadog",
    "figma",
    "gitlab",
    "brex",
    "affirm",
    "airtable",
    "samsara",
    "elastic",
    "dbtlabs",
    "gusto",
    "coinbase",
    "roblox",
    "pinterest",
    "instacart",
    "benchling",
]


def fetch_greenhouse_jobs(
    companies: Optional[List[str]] = None,
    keyword_filter: Optional[List[str]] = None,
    exclude_keywords: Optional[List[str]] = None,
    location_filter: Optional[List[str]] = None,
) -> List[Dict]:
    """Fetch jobs from Greenhouse public board API for a list of companies."""
    targets = companies or DEFAULT_GREENHOUSE_COMPANIES
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
        url = f"https://boards-api.greenhouse.io/v1/boards/{comp}/jobs?content=true"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            jobs = data.get("jobs", [])

            for j in jobs:
                title = j.get("title", "")
                if not matches_role_title(title, include_terms, exclude_terms):
                    continue

                location_info = j.get("location", {})
                loc_name = (
                    location_info.get("name", "")
                    if isinstance(location_info, dict)
                    else str(location_info)
                ) or "Not Specified"

                if location_filter and not matches_location(loc_name, location_filter):
                    continue

                raw_content = j.get("content", "")
                plain_text = clean_html_text(raw_content)
                min_sal, max_sal, sal_str = extract_salary_band(plain_text)

                # Extract department names if available
                departments = [
                    d.get("name", "")
                    for d in j.get("departments", [])
                    if isinstance(d, dict) and d.get("name")
                ]

                job_record = {
                    "source": "greenhouse",
                    "board_token": comp,
                    "company": comp.capitalize(),
                    "title": title,
                    "department": ", ".join(departments),
                    "location": loc_name,
                    "url": j.get("absolute_url", ""),
                    "id": f"gh_{comp}_{j.get('id')}",
                    "content": raw_content,
                    "plain_text": plain_text,
                    "min_salary_usd": min_sal,
                    "max_salary_usd": max_sal,
                    "salary_range": sal_str,
                    "updated_at": j.get("updated_at", ""),
                }
                all_jobs.append(job_record)
        except Exception as e:
            logger.warning("Error fetching Greenhouse jobs for %s: %s", comp, e)

    return all_jobs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing Greenhouse fetcher with 3 companies...")
    jobs = fetch_greenhouse_jobs(["anthropic", "cloudflare", "stripe"])
    print(f"Found {len(jobs)} matching jobs across test companies.")
    for job in jobs[:5]:
        print(
            f"- {job['company']}: {job['title']} ({job['location']}) | Salary: {job['salary_range']}"
        )
