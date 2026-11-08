"""Google ADK Multi-Agent Hierarchy for the AI Job Search Agent.

Compatible with:
  - `adk web` (Interactive Web UI)
  - `adk run job_search_agent` (Interactive CLI)
  - `python3 main.py ...` (Direct CLI & autonomous workflow runner)
"""

from __future__ import annotations

import os
from google.adk.agents import LlmAgent

from .tools.fit_tools import (
    generate_tailored_outreach_for_job,
    score_and_rank_all_jobs,
)
from .tools.profile_tools import (
    get_candidate_profile,
    sync_careeros_preferences,
)
from .tools.search_tools import (
    search_ashby_jobs,
    search_greenhouse_jobs,
    search_linkedin_jobs,
)

DEFAULT_MODEL = os.environ.get("JOB_SEARCH_AGENT_MODEL", "gemini-2.5-flash")

# -----------------------------------------------------------------------------
# 1. Multi-Source Discovery Subagent (Greenhouse, Ashby, LinkedIn)
# -----------------------------------------------------------------------------
discovery_agent = LlmAgent(
    name="discovery_agent",
    model=DEFAULT_MODEL,
    description=(
        "Fetches live job postings across Greenhouse, Ashby, and LinkedIn, "
        "sanitizes HTML against prompt injection, and extracts WA/CA salary bands."
    ),
    instruction=(
        "You are the Multi-Source Job Discovery Specialist.\n"
        "1. Inspect the candidate profile (`get_candidate_profile`) first so your searches "
        "use their exact role title filters and target locations.\n"
        "2. Query Greenhouse (`search_greenhouse_jobs`), Ashby (`search_ashby_jobs`), and "
        "LinkedIn (`search_linkedin_jobs`).\n"
        "3. Never fabricate job URLs or salaries."
    ),
    tools=[
        get_candidate_profile,
        search_greenhouse_jobs,
        search_ashby_jobs,
        search_linkedin_jobs,
    ],
)

# -----------------------------------------------------------------------------
# 2. Fit Scoring & Rubric Evaluator Subagent
# -----------------------------------------------------------------------------
fit_matcher_agent = LlmAgent(
    name="fit_matcher_agent",
    model=DEFAULT_MODEL,
    description=(
        "Scores job postings from 0 to 100 against the candidate_profile.json rubric "
        "(Role/Seniority, Domain/Tech, Candidate Edge, Location/Comp)."
    ),
    instruction=(
        "You are the Candidate Fit & Compensation Analyst.\n"
        "1. Load `candidate_profile.json` via `get_candidate_profile`.\n"
        "2. Run `score_and_rank_all_jobs` to evaluate jobs across all 4 rubric dimensions "
        "and compare disclosed WA/CA salary bands against the candidate's salary floor.\n"
        "3. Explain clearly why top roles scored high and flag any compensation gaps."
    ),
    tools=[
        get_candidate_profile,
        score_and_rank_all_jobs,
    ],
)

# -----------------------------------------------------------------------------
# 3. CareerOS & Briefing Tracker Subagent
# -----------------------------------------------------------------------------
tracker_agent = LlmAgent(
    name="tracker_agent",
    model=DEFAULT_MODEL,
    description=(
        "Syncs preferences with CareerOS (https://app.thecareeros.com/app/preferences) "
        "and exports ranked job trackers (CSV/JSON) and Markdown briefings."
    ),
    instruction=(
        "You are the CareerOS Pipeline & Briefing Tracker.\n"
        "1. Use `sync_careeros_preferences` to pull or import preferences from CareerOS.\n"
        "2. Use `score_and_rank_all_jobs` to persist seen jobs (`data/seen_jobs.json`), "
        "export `reports/careeros_job_tracker.csv` with Alumni LinkedIn search links, "
        "and generate `reports/latest_briefing.md`."
    ),
    tools=[
        get_candidate_profile,
        sync_careeros_preferences,
        score_and_rank_all_jobs,
    ],
)

# -----------------------------------------------------------------------------
# 4. Hiring Manager Critic & Outreach Assistant Subagent
# -----------------------------------------------------------------------------
outreach_assistant_agent = LlmAgent(
    name="outreach_assistant_agent",
    model=DEFAULT_MODEL,
    description=(
        "Runs a Skeptical Hiring Manager critique on top job matches and drafts "
        "tailored resume bullets and personalized LinkedIn/email outreach messages."
    ),
    instruction=(
        "You are the Executive Tech Career Strategist & Hiring Manager Critic.\n"
        "1. Use `generate_tailored_outreach_for_job` to identify the #1 likely objection "
        "a hiring manager will have and how the candidate should preempt it.\n"
        "2. Draft 3 tailored resume bullets and a concise cold outreach message using "
        "the candidate's school and company network hooks."
    ),
    tools=[
        get_candidate_profile,
        generate_tailored_outreach_for_job,
    ],
)

# -----------------------------------------------------------------------------
# Root Coordinator Agent (`root_agent` required by ADK CLI / Web)
# -----------------------------------------------------------------------------
root_agent = LlmAgent(
    name="job_search_coordinator",
    model=DEFAULT_MODEL,
    description=(
        "Root coordinator agent for discovering jobs across Greenhouse, Ashby, and LinkedIn, "
        "scoring fit against candidate_profile.json, syncing with CareerOS, and drafting outreach."
    ),
    instruction=(
        "You are the AI Job Search Coordinator built with Google ADK.\n"
        "You help the candidate discover live roles across Greenhouse, Ashby, and LinkedIn, "
        "score them against `candidate_profile.json`, export trackers for CareerOS, and draft "
        "tailored resume bullets and outreach notes.\n\n"
        "You have direct access to fast tools as well as four specialist subagents:\n"
        "- `discovery_agent`: Greenhouse, Ashby, and LinkedIn live job search.\n"
        "- `fit_matcher_agent`: 0-100 weighted rubric scoring and salary floor verification.\n"
        "- `tracker_agent`: CareerOS sync, CSV export, and Markdown briefing generation.\n"
        "- `outreach_assistant_agent`: Skeptical Hiring Manager critique and outreach drafting.\n\n"
        "Always ground your answers in `candidate_profile.json` and never fabricate URLs."
    ),
    tools=[
        get_candidate_profile,
        sync_careeros_preferences,
        search_greenhouse_jobs,
        search_ashby_jobs,
        search_linkedin_jobs,
        score_and_rank_all_jobs,
        generate_tailored_outreach_for_job,
    ],
    sub_agents=[
        discovery_agent,
        fit_matcher_agent,
        tracker_agent,
        outreach_assistant_agent,
    ],
)
