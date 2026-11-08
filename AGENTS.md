# Job Search Agent: Harness Engineering and Repository Rules

This repository implements an AI Job Search multi-agent application built with Google Agent Development Kit (`google-adk`) and Antigravity Harness Engineering (`AGENTS.md`, `.agents/skills/`, and `.agents/hooks.json`).

## 1. Repository Structure

```text
job-search-hack/
├── AGENTS.md                        # Always-on repository rules and boundaries
├── candidate_profile.json           # Local personal profile (gitignored)
├── candidate_profile.template.json  # Blank profile template for new users
├── main.py                          # CLI and autonomous workflow runner
├── job_search_agent/                # Google ADK Python package (`adk web` compatible)
│   ├── __init__.py                  # Exports `root_agent` with lazy-import startup
│   ├── agent.py                     # Root coordinator + 4 specialist subagents
│   └── tools/                       # ADK FunctionTools
│       ├── profile_tools.py         # Profile loader and CareerOS preference sync
│       ├── search_tools.py          # Greenhouse, Ashby, and LinkedIn job search
│       └── fit_tools.py             # 0-100 rubric scorer and outreach kit generator
├── src/                             # Core fetchers, evaluator, and CareerOS integration
├── .agents/                         # Antigravity Harness Engineering layer
│   ├── hooks.json                   # PreToolUse safety gate hook config
│   ├── scripts/pre_tool_guard.py    # Deterministic command and secret guard
│   └── skills/                      # Progressive-disclosure modular skills
│       ├── adk-architecture/        # ADK conventions and tool rules
│       ├── job-discovery/           # Greenhouse, Ashby, and LinkedIn discovery runbook
│       └── outreach-tailoring/      # Hiring manager critique and outreach runbook
├── data/                            # Local state (`seen_jobs.json`, CareerOS payload)
├── reports/                         # Generated Markdown briefings and CareerOS CSV
└── tests/                           # Pytest suite verifying tools, guard, and ADK agents
```

## 2. Core Guardrails

1. **Public Tool Schema Stability**:
   - Do not change the function signature or parameter names of public ADK tool functions in `job_search_agent/tools/` without updating agent instructions and unit tests.
   - Prefix internal helper functions with a single underscore (`_helper_name`) so they are not exposed as public ADK tools.
2. **Fast Cold Imports**:
   - Keep `job_search_agent/__init__.py` lightweight. Never run network calls at import time.
3. **Zero Hardcoded Personal Information**:
   - All personal resume facts, target roles, salary floors, and locations must be loaded dynamically from `candidate_profile.json`.
   - Never commit `candidate_profile.json` or `.env` to Git.
4. **Prompt Injection Defense on External Job Pages**:
   - All scraped HTML and text from LinkedIn, Greenhouse, and Ashby must pass through `_sanitize_untrusted_text()` in `src/fetchers/__init__.py`.
5. **Verification Before Completion**:
   - Run pytest on `tests/` after modifying code and verify all tests pass.
