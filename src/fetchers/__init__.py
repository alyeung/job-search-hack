"""
Shared Job Fetcher Utilities
Provides profile-driven role title matching, HTML cleaning, prompt-injection sanitization,
and WA/CA salary extraction.
"""

import html
import re
from typing import Dict, List, Optional, Tuple

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt\s*:", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
    re.compile(r"\brm\s+-rf\s+/", re.IGNORECASE),
]


def _sanitize_untrusted_text(raw_text: str) -> Tuple[str, bool]:
    """
    Sanitize scraped external job descriptions (LinkedIn, Greenhouse, Ashby)
    against prompt injection payloads before passing to any LLM agent.
    Returns (sanitized_text, injection_detected).
    """
    if not raw_text:
        return "", False
    # Remove script/style tags if raw HTML is passed
    cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_text, flags=re.I | re.S)
    injection_detected = False
    for pattern in INJECTION_PATTERNS:
        if pattern.search(cleaned):
            injection_detected = True
            cleaned = pattern.sub("[REDACTED_BY_HARNESS_GUARD]", cleaned)
    return cleaned, injection_detected


def clean_html_text(raw_html: str) -> str:
    """Convert HTML-encoded job descriptions into clean, sanitized plain text."""
    if not raw_html:
        return ""
    sanitized_raw, _ = _sanitize_untrusted_text(raw_html)
    unescaped = html.unescape(sanitized_raw)
    unescaped = html.unescape(unescaped)
    # Replace block tags with newlines
    text = re.sub(
        r"</?(p|div|li|br|ul|ol|h[1-6]|tr)[^>]*>", "\n", unescaped, flags=re.I
    )
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

    # Match patterns like $190,000 - $260,000 or $190,000—$260,000 USD or $190,000/yr - $260,000/yr
    range_pattern = re.compile(
        r"\$\s*([1-9]\d{2}),(\d{3})(?:\.\d{2})?(?:\s*/\s*yr|\s*USD)?\s*(?:[-–—]|to)\s*\$\s*([1-9]\d{2}),(\d{3})",
        re.IGNORECASE,
    )
    match = range_pattern.search(text)
    if match:
        low = int(match.group(1) + match.group(2))
        high = int(match.group(3) + match.group(4))
        if 60000 <= low <= high <= 1500000:
            return low, high, f"${low:,} - ${high:,}"

    # Match patterns like $190K - $250K or $190K/yr - $250K/yr
    k_pattern = re.compile(
        r"\$\s*([1-9]\d{1,2})(?:\.\d+)?\s*[kK](?:\s*/\s*yr)?\s*(?:[-–—]|to)\s*\$\s*([1-9]\d{1,2})(?:\.\d+)?\s*[kK]"
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
