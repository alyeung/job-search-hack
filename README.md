# Job Search Agent

This agent automates senior tech job hunting. It pulls live openings from Greenhouse, Ashby, and LinkedIn, scores them against your resume, and writes tailored outreach notes for your top matches.

## Why It Exists

Searching job boards by keyword wastes hours. Most results are the wrong level, the wrong location, or below your compensation floor.

This agent replaces manual board checking with a 4-step workflow:
1. **Pull live jobs** from Greenhouse, Ashby, and LinkedIn.
2. **Filter and extract salary bands** posted under Washington and California pay laws.
3. **Score each role from 0 to 100** based on your target level, domain, location, and pay floor.
4. **Prepare application assets** for your top 5 matches. This includes likely hiring manager objections, tailored resume bullets, and cold outreach messages.

## Built for Anyone, Customized in One File

The Python code contains zero personal information. Everything specific to you lives in `candidate_profile.json`.

* **To customize for yourself:** Edit `candidate_profile.json`.
* **To share with someone else:** They run `python3 main.py --init-profile my_profile.json` and edit their own file. They never touch the code.
* **To sync with CareerOS:** Export or copy your preferences from `https://app.thecareeros.com/app/preferences` into a text file and run `python3 main.py --import-careeros prefs.txt`.

## Architecture

The project uses Google Agent Development Kit (`google-adk`) and Antigravity Harness Engineering (`AGENTS.md`, `.agents/skills/`, and `.agents/hooks.json`).

* `job_search_coordinator` (`root_agent`): Orchestrates four specialized subagents:
  * `discovery_agent`: Searches Greenhouse, Ashby, and LinkedIn and strips untrusted HTML.
  * `fit_matcher_agent`: Scores roles from 0 to 100 against `candidate_profile.json`.
  * `tracker_agent`: Saves seen jobs (`data/seen_jobs.json`), CareerOS spreadsheets (`reports/careeros_job_tracker.csv`), and Markdown briefings (`reports/latest_briefing.md`).
  * `outreach_assistant_agent`: Identifies hiring manager objections and writes resume bullets and outreach notes.

## Quick Start

```bash
# 1. Run across specific companies and LinkedIn (takes ~15 seconds)
python3 main.py --companies anthropic openai databricks stripe cloudflare linear linkedin --top 5

# 2. Run across all companies in your profile
python3 main.py

# 3. Chat interactively with the agent in your terminal
python3 main.py --chat

# 4. Launch the Google ADK Web UI (optional, requires google-adk and GEMINI_API_KEY)
adk web
```

## Where to Find Your Results

* `reports/latest_briefing.md`: Ranked leaderboard, salary bands, hiring manager critiques, and outreach drafts.
* `reports/careeros_job_tracker.csv`: Spreadsheet tracker with LinkedIn alumni search links for each target company.
* `data/seen_jobs.json`: Memory log so the agent flags newly posted roles on future runs.
