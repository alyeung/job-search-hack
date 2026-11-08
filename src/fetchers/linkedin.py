"""
LinkedIn Public Guest Jobs Fetcher
Fetches live job postings from LinkedIn's public job search endpoints without requiring credentials:
  - Search endpoint: https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
  - Detail endpoint: https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}
Includes prompt-injection sanitization and WA/CA salary band extraction.
"""

import html
import logging
import re
from typing import Dict, List, Optional
import requests

try:
    from src.fetchers import (
        _sanitize_untrusted_text,
        clean_html_text,
        extract_salary_band,
        matches_location,
        matches_role_title,
    )
except ImportError:
    from __init__ import (  # type: ignore
        _sanitize_untrusted_text,
        clean_html_text,
        extract_salary_band,
        matches_location,
        matches_role_title,
    )

logger = logging.getLogger(__name__)

LINKEDIN_SEARCH_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
)
LINKEDIN_DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _parse_linkedin_search_cards(raw_html: str) -> List[Dict[str, str]]:
    """Parse job cards from LinkedIn's seeMoreJobPostings HTML snippet."""
    cards: List[Dict[str, str]] = []
    if not raw_html:
        return cards

    cleaned_html = re.sub(
        r"<(script|style)[^>]*>.*?</\1>", "", raw_html, flags=re.S | re.I
    )

    for li_match in re.finditer(r"<li>(.*?)</li>", cleaned_html, flags=re.S | re.I):
        block = li_match.group(1)
        urn_match = re.search(r'data-entity-urn="urn:li:jobPosting:(\d+)"', block)
        if not urn_match:
            continue
        job_id = urn_match.group(1)

        title_match = re.search(
            r'class="base-search-card__title[^"]*"[^>]*>(.*?)</h3>',
            block,
            flags=re.S | re.I,
        )
        company_match = re.search(
            r'class="base-search-card__subtitle[^"]*"[^>]*>(.*?)</h4>',
            block,
            flags=re.S | re.I,
        )
        loc_match = re.search(
            r'class="job-search-card__location[^"]*"[^>]*>(.*?)</span>',
            block,
            flags=re.S | re.I,
        )
        url_match = re.search(
            r'class="base-card__full-link[^"]*"[^>]*href="([^"]+)"',
            block,
            flags=re.S | re.I,
        )
        salary_match = re.search(
            r'class="job-search-card__salary-info[^"]*"[^>]*>(.*?)</span>',
            block,
            flags=re.S | re.I,
        )
        date_match = re.search(r'<time[^>]*datetime="([^"]+)"', block, flags=re.I)

        title = clean_html_text(title_match.group(1)) if title_match else ""
        company = clean_html_text(company_match.group(1)) if company_match else ""
        location = clean_html_text(loc_match.group(1)) if loc_match else "Not Specified"
        raw_url = html.unescape(url_match.group(1)).split("?")[0] if url_match else f"https://www.linkedin.com/jobs/view/{job_id}"
        card_salary = clean_html_text(salary_match.group(1)) if salary_match else ""
        posted_at = date_match.group(1) if date_match else ""

        if title and company:
            cards.append(
                {
                    "job_id": job_id,
                    "title": title,
                    "company": company,
                    "location": location,
                    "url": raw_url,
                    "card_salary": card_salary,
                    "updated_at": posted_at,
                }
            )
    return cards


def _fetch_linkedin_job_detail(job_id: str) -> str:
    """Fetch full job description HTML for a LinkedIn job_id and sanitize it."""
    url = LINKEDIN_DETAIL_URL.format(job_id=job_id)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code != 200:
            return ""
        desc_match = re.search(
            r'class="show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>',
            resp.text,
            flags=re.S | re.I,
        )
        raw_section = desc_match.group(1) if desc_match else resp.text
        return clean_html_text(raw_section)
    except Exception as e:
        logger.debug("LinkedIn detail fetch failed for %s: %s", job_id, e)
        return ""


def fetch_linkedin_jobs(
    search_queries: Optional[List[str]] = None,
    locations: Optional[List[str]] = None,
    keyword_filter: Optional[List[str]] = None,
    exclude_keywords: Optional[List[str]] = None,
    location_filter: Optional[List[str]] = None,
    max_per_query: int = 10,
    fetch_details: bool = True,
) -> List[Dict]:
    """
    Search live LinkedIn job postings across search queries and locations.
    Deduplicates by LinkedIn job ID, filters by candidate role include/exclude keywords,
    fetches full descriptions for top matches, sanitizes against prompt injection,
    and extracts salary bands.
    """
    queries = search_queries or [
        "Principal Product Manager Cloud AI",
        "Staff Product Manager Developer Platform",
    ]
    target_locs = [loc for loc in (locations or ["Seattle, WA", "San Francisco Bay Area"]) if loc.lower() != "remote"]
    if not target_locs:
        target_locs = ["United States"]

    include_terms = keyword_filter or [
        "product manager",
        "product management",
        "principal pm",
        "staff pm",
        "group pm",
        "technical pm",
        "director, product",
        "director of product",
    ]
    exclude_terms = (
        exclude_keywords
        if exclude_keywords is not None
        else [
            "associate product manager",
            "intern",
            "product designer",
            "product marketing",
            "production",
        ]
    )

    seen_ids = set()
    all_jobs: List[Dict] = []

    for query in queries[:3]:
        for loc in target_locs[:2]:
            try:
                resp = requests.get(
                    LINKEDIN_SEARCH_URL,
                    params={"keywords": query, "location": loc, "start": 0},
                    headers=HEADERS,
                    timeout=10,
                )
                if resp.status_code != 200:
                    continue
                cards = _parse_linkedin_search_cards(resp.text)
                count_for_query = 0

                for card in cards:
                    jid = card["job_id"]
                    if jid in seen_ids:
                        continue
                    title = card["title"]
                    if not matches_role_title(title, include_terms, exclude_terms):
                        continue
                    if location_filter and not matches_location(
                        card["location"], location_filter
                    ):
                        continue

                    seen_ids.add(jid)
                    plain_text = (
                        _fetch_linkedin_job_detail(jid)
                        if fetch_details and count_for_query < max_per_query
                        else ""
                    )
                    sanitized_text, injection_flag = _sanitize_untrusted_text(
                        f"{card['card_salary']}\n{plain_text}"
                    )
                    min_sal, max_sal, sal_str = extract_salary_band(sanitized_text)

                    job_record = {
                        "source": "linkedin",
                        "board_token": "linkedin",
                        "company": card["company"],
                        "title": title,
                        "department": "",
                        "location": card["location"],
                        "url": card["url"],
                        "id": f"li_{jid}",
                        "content": sanitized_text,
                        "plain_text": sanitized_text,
                        "min_salary_usd": min_sal,
                        "max_salary_usd": max_sal,
                        "salary_range": sal_str,
                        "updated_at": card["updated_at"],
                        "injection_sanitized": injection_flag,
                    }
                    all_jobs.append(job_record)
                    count_for_query += 1
                    if count_for_query >= max_per_query:
                        break
            except Exception as e:
                logger.warning(
                    "Error fetching LinkedIn jobs for query '%s' (%s): %s",
                    query,
                    loc,
                    e,
                )

    return all_jobs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing LinkedIn fetcher...")
    jobs = fetch_linkedin_jobs(
        search_queries=["Principal Product Manager Cloud"],
        locations=["Seattle, WA"],
        max_per_query=5,
    )
    print(f"Found {len(jobs)} matching LinkedIn jobs.")
    for j in jobs[:5]:
        print(
            f"- {j['company']}: {j['title']} ({j['location']}) | Salary: {j['salary_range']}"
        )
