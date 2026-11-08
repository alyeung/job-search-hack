"""
Shared Job Fetcher Utilities
Provides profile-driven role title matching, HTML cleaning, and WA/CA salary extraction.
"""

import html
import re
from typing import Dict, List, Optional, Tuple


def clean_html_text(raw_html: str) -> str:
    """Convert HTML-encoded job descriptions into clean, readable plain text."""
    if not raw_html:
        return ""
    unescaped = html.unescape(raw_html)
    # Unescape a second time for double-escaped entities common in Greenhouse APIs
    unescaped = html.unescape(unescaped)
    # Replace block tags with newlines
    text = re.sub(r"</?(p|div|li|br|ul|ol|h[1-6]|tr)[^>]*>", "\n", unescaped, flags=re.I)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Collapse excessive whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_salary_band(text: str) -> Tuple[Optional[int], Optional[int], str]:
    """
    Extract USD base salary range (e.g., '$210,000 - $265,000' or '$200K - $250K')
    commonly disclosed in WA, CA, and NY job postings.
    Returns (min_usd, max_usd, display_string).
    """
    if not text:
        return None, None, "Not Disclosed"

    # Match patterns like $190,000 - $260,000 or $190,000—$260,000 USD
    range_pattern = re.compile(
        r"\$\s*([1-9]\d{2}),(\d{3})(?:\.\d{2})?\s*(?:USD)?\s*(?:[-–—]|to)\s*\$\s*([1-9]\d{2}),(\d{3})",
        re.IGNORECASE,
    )
    match = range_pattern.search(text)
    if match:
        low = int(match.group(1) + match.group(2))
        high = int(match.group(3) + match.group(4))
        if 60000 <= low <= high <= 1500000:
            return low, high, f"${low:,} - ${high:,}"

    # Match patterns like $190K - $250K
    k_pattern = re.compile(
        r"\$\s*([1-9]\d{1,2})\s*[kK]\s*(?:[-–—]|to)\s*\$\s*([1-9]\d{1,2})\s*[kK]"
    )
    match_k = k_pattern.search(text)
    if match_k:
        low = int(match_k.group(1)) * 1000
        high = int(match_k.group(2)) * 1000
        if 60000 <= low <= high <= 1500000:
            return low, high, f"${low:,} - ${high:,}"

    # Match single salary mention near "base salary" or "annual salary"
    single_pattern = re.compile(
        r"(?:base|annual|salary|pay|range)[^$\n]{0,60}\$\s*([1-9]\d{2}),(\d{3})",
        re.IGNORECASE,
    )
    match_single = single_pattern.search(text)
    if match_single:
        val = int(match_single.group(1) + match_single.group(2))
        if 60000 <= val <= 1200000:
            return val, val, f"${val:,}"

    return None, None, "Not Disclosed"


def matches_role_title(
    title: str,
    include_keywords: List[str],
    exclude_keywords: Optional[List[str]] = None,
) -> bool:
    """
    Check if a job title matches the candidate's target role keywords
    and does not hit any excluded role keywords.
    Uses word boundaries for short terms (<= 3 chars like 'pm' or 'ai')
    so 'product' does not match 'AV Production' and 'pm' does not match 'development'.
    """
    if not title:
        return False
    title_lower = title.lower()

    for excl in exclude_keywords or []:
        excl_l = excl.lower().strip()
        if not excl_l:
            continue
        if len(excl_l) <= 3:
            if re.search(rf"\b{re.escape(excl_l)}\b", title_lower):
                return False
        elif excl_l in title_lower:
            return False

    if not include_keywords:
        return True

    for inc in include_keywords:
        inc_l = inc.lower().strip()
        if not inc_l:
            continue
        if len(inc_l) <= 3:
            if re.search(rf"\b{re.escape(inc_l)}\b", title_lower):
                return True
        elif inc_l in title_lower:
            return True

    return False


def matches_location(
    location_str: str,
    location_keywords: Optional[List[str]] = None,
) -> bool:
    """Check whether a job's location string matches any of the candidate's target location keywords."""
    if not location_keywords:
        return True
    if not location_str:
        return True
    loc_lower = location_str.lower()
    return any(k.lower().strip() in loc_lower for k in location_keywords if k.strip())
