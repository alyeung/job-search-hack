"""
Profile-Driven Job Fit Evaluator & Application Kit Generator
Scores jobs dynamically against ANY candidate_profile.json rubric using:
1. Fast multi-dimensional rubric scoring (Role/Seniority, Domain/Technical, Candidate Edge, Location/Comp)
2. Google Gemini LLM deep evaluation, Skeptical Hiring Manager critique, and tailored outreach generation
   (supports both `google-genai` SDK and direct Gemini REST API via `requests`, with deterministic fallback).
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)

STOPWORDS = {
    "and",
    "the",
    "for",
    "with",
    "from",
    "that",
    "this",
    "your",
    "will",
    "are",
    "you",
    "our",
    "have",
    "has",
    "inc",
    "via",
    "into",
    "across",
}


def _tokenize_meaningful(text: str) -> List[str]:
    """Extract lowercase alphanumeric tokens of length >= 3, excluding common stopwords."""
    tokens = re.findall(r"[a-z0-9+#/.-]{2,}", text.lower())
    return [t.strip(".-/") for t in tokens if len(t.strip(".-/")) >= 2 and t not in STOPWORDS]


def evaluate_job_rubric(job: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate a single job record against the loaded candidate profile JSON.
    Uses zero hardcoded candidate assumptions—everything comes from `profile`.
    """
    weights = profile.get("scoring_weights", {})
    w_role = float(weights.get("role_and_seniority_fit", 30))
    w_domain = float(weights.get("domain_and_technical_fit", 30))
    w_edge = float(weights.get("candidate_edge_and_pedigree", 25))
    w_loc_comp = float(weights.get("location_and_compensation_fit", 15))

    title = job.get("title", "")
    title_lower = title.lower()
    dept = job.get("department", "")
    plain_text = job.get("plain_text", "") or job.get("content", "")
    full_text_lower = f"{title} {dept} {plain_text}".lower()
    location_str = job.get("location", "")
    loc_lower = location_str.lower()

    # ---------------------------------------------------------
    # 1. Role & Seniority Fit (out of w_role)
    # ---------------------------------------------------------
    target_roles: List[str] = profile.get("target_roles", [])
    constraints = profile.get("constraints_and_comp", {})
    pref_seniority: List[str] = constraints.get("preferred_seniority", [])

    role_ratio = 0.55  # baseline since title passed fetcher filter
    matched_role_terms: List[str] = []

    for r in target_roles:
        if r.lower() in title_lower:
            role_ratio = max(role_ratio, 0.96)
            matched_role_terms.append(r)

    for sen in pref_seniority:
        if sen.lower() in title_lower:
            role_ratio = max(role_ratio, 0.92)
            if sen not in matched_role_terms:
                matched_role_terms.append(f"{sen}-level")
        elif sen.lower() in full_text_lower[:1500]:
            role_ratio = max(role_ratio, 0.80)

    # Boost if strategic/technical keywords from target_roles appear in title
    for role in target_roles:
        for tok in _tokenize_meaningful(role):
            if tok not in ("product", "manager", "management") and tok in title_lower:
                role_ratio = min(1.0, role_ratio + 0.12)
                if tok.upper() not in matched_role_terms:
                    matched_role_terms.append(tok)

    role_score = round(w_role * min(1.0, role_ratio), 1)

    # ---------------------------------------------------------
    # 2. Domain & Technical Fit (out of w_domain)
    # ---------------------------------------------------------
    target_domains: List[str] = profile.get("target_domains", [])
    competencies: List[str] = profile.get("core_competencies", [])

    matched_domains: List[str] = []
    domain_hits = 0
    for dom in target_domains:
        dom_tokens = [t for t in _tokenize_meaningful(dom) if len(t) >= 2]
        if any(
            re.search(rf"\b{re.escape(tok)}\b", full_text_lower) for tok in dom_tokens
        ):
            domain_hits += 1
            matched_domains.append(dom)

    matched_competencies: List[str] = []
    comp_hits = 0
    for comp in competencies:
        comp_tokens = [t for t in _tokenize_meaningful(comp) if len(t) >= 3]
        overlap = sum(
            1
            for tok in comp_tokens
            if re.search(rf"\b{re.escape(tok)}\b", full_text_lower)
        )
        if overlap >= max(1, len(comp_tokens) // 3):
            comp_hits += 1
            matched_competencies.append(comp)

    total_domain_signals = domain_hits + (0.75 * comp_hits)
    domain_ratio = min(1.0, 0.35 + (total_domain_signals / max(3.0, len(target_domains) * 0.75)))
    domain_score = round(w_domain * domain_ratio, 1)

    # ---------------------------------------------------------
    # 3. Candidate Edge & Pedigree Match (out of w_edge)
    # ---------------------------------------------------------
    experiences: List[Dict[str, Any]] = profile.get("experience_highlights", [])
    education: List[Dict[str, Any]] = profile.get("education", [])
    search_prefs = profile.get("search_preferences", {})
    tiers = search_prefs.get("company_tiers", {})
    tier1 = [c.lower() for c in tiers.get("tier_1_priority", [])]
    tier2 = [c.lower() for c in tiers.get("tier_2_target", [])]

    matched_experiences: List[Dict[str, Any]] = []
    exp_score_acc = 0.0
    for exp in experiences:
        exp_text = f"{exp.get('domain', '')} {exp.get('highlights', '')} {exp.get('title', '')}"
        exp_tokens = set(_tokenize_meaningful(exp_text))
        hits = [
            t
            for t in exp_tokens
            if len(t) >= 3 and re.search(rf"\b{re.escape(t)}\b", full_text_lower)
        ]
        if len(hits) >= 2:
            matched_experiences.append(
                {
                    "company": exp.get("company", ""),
                    "title": exp.get("title", ""),
                    "domain": exp.get("domain", ""),
                    "highlights": exp.get("highlights", ""),
                    "matched_keywords": sorted(hits)[:6],
                }
            )
            exp_score_acc += min(0.35, len(hits) * 0.06)

    # Check education alignment (e.g. MBA, Finance, CS/EE/Engineering degree)
    matched_education: List[str] = []
    for edu in education:
        edu_str = f"{edu.get('degree', '')} {edu.get('school', '')} {edu.get('details', '')}"
        if any(
            term in full_text_lower
            for term in ("mba", "master", "engineering", "computer science", "electrical", "technical degree", "finance")
        ):
            matched_education.append(f"{edu.get('degree', '')} ({edu.get('school', '')})")
            exp_score_acc += 0.12

    company_lower = job.get("company", "").lower()
    tier_label = "Standard Target"
    if company_lower in tier1:
        exp_score_acc += 0.20
        tier_label = "Tier 1 Priority"
    elif company_lower in tier2:
        exp_score_acc += 0.12
        tier_label = "Tier 2 Target"

    edge_ratio = min(1.0, 0.35 + exp_score_acc)
    edge_score = round(w_edge * edge_ratio, 1)

    # ---------------------------------------------------------
    # 4. Location & Compensation Fit (out of w_loc_comp)
    # ---------------------------------------------------------
    loc_keywords: List[str] = search_prefs.get("location_keywords", [])
    min_sal_floor = int(constraints.get("min_base_salary_usd", 0) or 0)
    target_sal = int(constraints.get("target_base_salary_usd", 0) or 0)

    loc_ratio = 0.5
    matched_loc = "Check location details"
    candidate_home_city = profile.get("location", "").split(",")[0].strip().lower()
    if candidate_home_city and candidate_home_city in loc_lower:
        loc_ratio = 1.0
        matched_loc = f"Matches home base ({profile.get('location')})"
    elif "remote" in loc_lower:
        loc_ratio = 0.95
        matched_loc = "Remote eligible"
    elif any(k.lower() in loc_lower for k in loc_keywords):
        loc_ratio = 0.90
        matched_loc = f"Matches target location ({location_str})"

    job_max_sal = job.get("max_salary_usd")
    job_min_sal = job.get("min_salary_usd")
    comp_ratio = 0.80  # neutral when undisclosed
    comp_note = job.get("salary_range", "Not Disclosed")

    if job_max_sal:
        if target_sal and job_max_sal >= target_sal:
            comp_ratio = 1.0
            comp_note = f"{job.get('salary_range')} (Exceeds ${target_sal:,} target)"
        elif min_sal_floor and job_max_sal >= min_sal_floor:
            comp_ratio = 0.85
            comp_note = f"{job.get('salary_range')} (Meets ${min_sal_floor:,} floor)"
        elif min_sal_floor and job_max_sal < min_sal_floor:
            comp_ratio = 0.25
            comp_note = f"{job.get('salary_range')} (Below ${min_sal_floor:,} floor)"

    loc_comp_score = round(w_loc_comp * ((0.55 * loc_ratio) + (0.45 * comp_ratio)), 1)

    total_score = round(role_score + domain_score + edge_score + loc_comp_score, 1)

    # Build baseline Skeptical Hiring Manager critique & strengths
    top_exp = matched_experiences[0] if matched_experiences else (experiences[0] if experiences else {})
    why_fit = (
        f"Strong alignment with {', '.join(matched_domains[:2]) or 'target domain'}. "
        f"Directly leverages experience as {top_exp.get('title', 'a leader')} at {top_exp.get('company', 'prior companies')} "
        f"({top_exp.get('domain', '')}) and core strengths in {', '.join(matched_competencies[:2]) or 'product execution'}."
    )

    hm_objection = _infer_hiring_manager_objection(job, profile, matched_domains)

    return {
        "job_id": job.get("id"),
        "company": job.get("company"),
        "company_tier": tier_label,
        "title": title,
        "department": dept,
        "location": location_str,
        "location_note": matched_loc,
        "url": job.get("url"),
        "source": job.get("source"),
        "salary_range": job.get("salary_range", "Not Disclosed"),
        "compensation_note": comp_note,
        "total_score": total_score,
        "score_breakdown": {
            "role_and_seniority_fit": f"{role_score}/{int(w_role)}",
            "domain_and_technical_fit": f"{domain_score}/{int(w_domain)}",
            "candidate_edge_and_pedigree": f"{edge_score}/{int(w_edge)}",
            "location_and_compensation_fit": f"{loc_comp_score}/{int(w_loc_comp)}",
        },
        "matched_domains": matched_domains,
        "matched_competencies": matched_competencies,
        "matched_experiences": matched_experiences,
        "matched_education": matched_education,
        "why_you_fit": why_fit,
        "hiring_manager_critique": hm_objection,
        "evaluation_mode": "rubric",
    }


def _infer_hiring_manager_objection(
    job: Dict[str, Any],
    profile: Dict[str, Any],
    matched_domains: List[str],
) -> Dict[str, str]:
    """Generate a targeted 'Skeptical Hiring Manager' objection and preemption strategy based on the JD and profile."""
    title_lower = job.get("title", "").lower()
    text_lower = (job.get("plain_text", "") or "").lower()[:3000]
    experiences = profile.get("experience_highlights", [])
    recent_exp = experiences[0] if experiences else {}
    recent_company = recent_exp.get("company", "your current organization")

    if "ai" in title_lower or "model" in title_lower or "agent" in title_lower or "llm" in text_lower:
        return {
            "likely_objection": (
                f"Hiring manager may ask how much hands-on LLM/agent evaluation or model-layer product ownership "
                f"you've had versus foundational cloud/platform infrastructure at {recent_company}."
            ),
            "how_to_preempt": (
                "Lead with concrete AI/ML & API platform work (developer SDKs/APIs, speech/analytics ML pipelines) "
                "and showcase projects you've built directly with agentic workflows and developer tooling."
            ),
        }
    if "fintech" in text_lower or "financial" in title_lower or "payment" in text_lower or "billing" in text_lower:
        return {
            "likely_objection": (
                "Hiring manager may look for direct regulated payments/fintech domain tenure."
            ),
            "how_to_preempt": (
                "Highlight your combination of enterprise-scale cloud platform ownership with your formal strategic finance "
                "leadership (MBR ownership, unit economics, and finance/investment background)."
            ),
        }
    return {
        "likely_objection": (
            f"At high-velocity companies like {job.get('company')}, interviewers often probe whether leaders from large "
            f"enterprises ({recent_company}) can operate hands-on with rapid 0-to-1 iteration."
        ),
        "how_to_preempt": (
            "Emphasize 0-to-1 technical ownership, rapid prototyping, and measurable adoption wins across your career "
            "alongside your ability to align engineering and executive stakeholders."
        ),
    }


def _call_gemini_json(prompt: str, model_name: str = "gemini-2.5-flash") -> Optional[Dict[str, Any]]:
    """
    Call Google Gemini to get a structured JSON response.
    Supports `google-genai` SDK if installed, or direct REST API via `requests`
    whenever `GEMINI_API_KEY` or `GOOGLE_API_KEY` is present in the environment.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    # 1. Try google-genai SDK first if installed
    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
        if response and response.text:
            return json.loads(response.text)
    except ImportError:
        pass
    except Exception as e:
        logger.debug("google-genai SDK call failed, trying REST fallback: %s", e)

    # 2. Direct REST call via `requests` (zero extra dependencies required)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2,
        },
    }
    try:
        resp = requests.post(url, json=payload, timeout=25)
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts and "text" in parts[0]:
                    return json.loads(parts[0]["text"])
    except Exception as e:
        logger.warning("Gemini API call error: %s", e)

    return None


def generate_application_kit(
    job: Dict[str, Any],
    evaluation: Dict[str, Any],
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    """
    For a high-scoring job match, generate a tailored Application Kit:
    - Refined LLM fit reasoning & Skeptical Hiring Manager critique (when GEMINI_API_KEY is set)
    - 3 customized resume bullet positioning hooks mapped from `profile['experience_highlights']`
    - A personalized LinkedIn / Hiring Manager outreach note using `profile['outreach_and_positioning']`
    """
    candidate_name = profile.get("name", "Candidate")
    outreach_cfg = profile.get("outreach_and_positioning", {})
    elevator_pitch = outreach_cfg.get("elevator_pitch", "")
    hooks = outreach_cfg.get("alumni_and_network_hooks", [])
    experiences = profile.get("experience_highlights", [])
    education = profile.get("education", [])
    jd_excerpt = (job.get("plain_text", "") or "")[:4000]

    prompt = f"""You are an elite Executive Tech Career Strategist & Hiring Manager Critic.
Evaluate this job posting for the candidate defined in the JSON profile below, and generate a tailored Application Kit.

CANDIDATE PROFILE JSON:
{json.dumps(profile, indent=2)}

JOB POSTING:
Company: {job.get('company')}
Title: {job.get('title')}
Location: {job.get('location')}
Disclosed Salary: {job.get('salary_range')}
Job Description Excerpt:
{jd_excerpt}

Return ONLY valid JSON with this exact schema:
{{
  "refined_score": <number between 0 and 100 based on the profile's scoring_weights and dealbreakers>,
  "why_you_fit": "<2-3 sharp sentences connecting the candidate's exact companies, degrees, and metrics to this role>",
  "hiring_manager_critique": {{
    "likely_objection": "<The #1 skeptical question or gap the hiring manager at {job.get('company')} will raise>",
    "how_to_preempt": "<Concrete way the candidate should frame their background to turn this objection into a strength>"
  }},
  "tailored_resume_bullets": [
    "<Tailored resume bullet #1 adapting the candidate's real experience to this job's top requirement>",
    "<Tailored resume bullet #2 adapting the candidate's real experience to this job's technical/domain needs>",
    "<Tailored resume bullet #3 highlighting cross-functional/financial/strategic impact relevant to this role>"
  ],
  "outreach_message": "<A concise, high-signal 110-word LinkedIn/email note to the hiring manager at {job.get('company')} referencing specific role needs and the candidate's network hooks>"
}}"""

    llm_result = _call_gemini_json(prompt)
    if llm_result and isinstance(llm_result, dict):
        if "refined_score" in llm_result:
            try:
                evaluation["total_score"] = round(float(llm_result["refined_score"]), 1)
            except (TypeError, ValueError):
                pass
        if llm_result.get("why_you_fit"):
            evaluation["why_you_fit"] = llm_result["why_you_fit"]
        if isinstance(llm_result.get("hiring_manager_critique"), dict):
            evaluation["hiring_manager_critique"] = llm_result["hiring_manager_critique"]
        evaluation["evaluation_mode"] = "gemini-llm"
        return {
            "tailored_resume_bullets": llm_result.get("tailored_resume_bullets", []),
            "outreach_message": llm_result.get("outreach_message", ""),
            "generated_by": "gemini-llm",
        }

    # Profile-driven deterministic synthesis when GEMINI_API_KEY is not set
    company = job.get("company", "the team")
    role_title = job.get("title", "this role")
    matched_doms = evaluation.get("matched_domains") or profile.get("target_domains", [])[:2]
    dom_phrase = " & ".join(matched_doms[:2]) if matched_doms else "platform & product strategy"

    bullets: List[str] = []
    for exp in experiences[:3]:
        exp_comp = exp.get("company", "")
        exp_title = exp.get("title", "")
        exp_dom = exp.get("domain", "")
        exp_high = exp.get("highlights", "").rstrip(".")
        bullets.append(
            f"[{exp_comp} — {exp_title}] {exp_high}; directly transferable to {company}'s {role_title} focus on {dom_phrase}."
        )

    # Pick the best network hook based on location/company
    loc_lower = (job.get("location", "") or "").lower()
    selected_hook = hooks[0] if hooks else ""
    if "seattle" in loc_lower or "bellevue" in loc_lower:
        for h in hooks:
            if "washington" in h.lower() or "seattle" in h.lower():
                selected_hook = h
                break
    elif "san francisco" in loc_lower or "bay area" in loc_lower:
        for h in hooks:
            if "berkeley" in h.lower() or "haas" in h.lower() or "bay area" in h.lower():
                selected_hook = h
                break

    edu_summary = (
        f"{education[0].get('degree', '')} ({education[0].get('school', '')})"
        if education
        else ""
    )
    lead_exp = experiences[0] if experiences else {}
    pitch_sentence = (
        elevator_pitch
        or f"I am a {lead_exp.get('title', 'product leader')} at {lead_exp.get('company', '')} ({lead_exp.get('domain', '')}) with a background in {edu_summary}."
    )

    outreach_msg = (
        f"Hi [Hiring Manager],\n\n"
        f"I noticed {company} is hiring for the {role_title} role ({job.get('location')}). "
        f"{pitch_sentence}\n\n"
        f"Given this role's focus on {dom_phrase}, my recent work driving {lead_exp.get('domain', 'platform roadmaps')} at {lead_exp.get('company', 'scale')} "
        f"and delivering measurable platform adoption aligns closely with what your team is building"
        f"{f' (also always glad to connect via the {selected_hook} community)' if selected_hook else ''}.\n\n"
        f"Would you be open to a brief 15-minute chat this week?\n\n"
        f"Best,\n{candidate_name}\n{profile.get('linkedin', '')}"
    ).strip()

    return {
        "tailored_resume_bullets": bullets,
        "outreach_message": outreach_msg,
        "generated_by": "profile-synthesizer",
    }
