# Profile-Driven AI Job Search Agent

An autonomous and interactive AI Job Search Agent that discovers live roles across **Greenhouse** and **Ashby** ATS job boards, parses **WA/CA disclosed salary bands**, evaluates fit using a **weighted 4-dimension rubric**, runs a **Skeptical Hiring Manager Critique**, and drafts **tailored resume bullets + cold outreach messages**.

---

## How "Built for Everyone, Customized for You" Works

The architecture strictly separates **the Agent Engine (Python code)** from **the Candidate Profile (JSON data)**:

* **To customize for yourself:** You only ever edit **`candidate_profile.json`**.
* **For anyone else to use this agent:** They do not touch a single line of Python. They generate or edit their own JSON file from **`candidate_profile.template.json`** and run `python3 main.py --profile their_profile.json`.

### What You Can Customize in `candidate_profile.json`

| Section in `candidate_profile.json` | Purpose |
| :--- | :--- |
| `target_locations`, `target_roles`, `target_domains` | Defines your target cities/remote, seniority/titles, and industry domains. |
| `search_preferences.role_title_include_keywords` | Keywords a job title must match (e.g., `"product manager"`, `"principal pm"`). |
| `search_preferences.role_title_exclude_keywords` | Noise titles to reject immediately (e.g., `"intern"`, `"associate product manager"`, `"production"`). |
| `search_preferences.target_boards` | Lists of company board tokens to scan across `greenhouse` and `ashby`. |
| `search_preferences.company_tiers` | Groups dream companies into `tier_1_priority` and `tier_2_target` for extra scoring weight. |
| `constraints_and_comp` | Your `min_base_salary_usd`, `target_base_salary_usd`, `preferred_seniority`, and hard `dealbreakers`. |
| `scoring_weights` | Customizable weights summing to 100 across `role_and_seniority_fit`, `domain_and_technical_fit`, `candidate_edge_and_pedigree`, and `location_and_compensation_fit`. |
| `experience_highlights`, `education`, `core_competencies` | Your background evidence used to score jobs and write tailored resume bullet hooks. |
| `outreach_and_positioning` | Your `elevator_pitch` and `alumni_and_network_hooks` woven into cold outreach drafts. |

---

## Quick Start

### 1. Run Autonomous Agent Mode (Uses `candidate_profile.json`)
```bash
# Run across all configured Greenhouse & Ashby companies
python3 main.py

# Or run a fast demo across specific companies
python3 main.py --companies anthropic openai cloudflare databricks stripe --top 5
```

### 2. Enable Live Google Gemini LLM Reasoning (Optional)
The agent works out-of-the-box using its profile-driven rubric synthesizer, and automatically upgrades to live **Google Gemini (`gemini-2.5-flash`)** when `GEMINI_API_KEY` is set:
```bash
cp .env.example .env
# Edit .env and paste your GEMINI_API_KEY
python3 main.py
```

### 3. Run Interactive Chat Mode
```bash
python3 main.py --chat
```
Inside chat mode, try:
* `profile` — inspect active profile & rubric weights
* `search anthropic openai linear` — run live discovery and scoring
* `top` — view the ranked leaderboard
* `explain #1` or `outreach #2` — view Skeptical Hiring Manager critique, tailored bullets, and outreach note

### 4. CareerOS Integration (`https://app.thecareeros.com/app/preferences`)
University and MBA programs (such as UC Berkeley Haas) use **CareerOS** to manage student preferences, target companies, job tracking boards, and alumni networking.

* **Inbound Sync (CareerOS Preferences $\rightarrow$ `candidate_profile.json`):**
  ```bash
  # Sync directly if CAREEROS_BEARER_TOKEN / CAREEROS_SESSION_COOKIE is set in .env
  python3 main.py --sync-careeros

  # Or copy-paste / save your preferences from https://app.thecareeros.com/app/preferences into a file:
  python3 main.py --import-careeros my_careeros_prefs.txt
  ```
* **Outbound Sync (Agent Matches $\rightarrow$ CareerOS Job Tracker & Alumni Contacts):**
  Every run automatically generates **`reports/careeros_job_tracker.csv`** and **`data/careeros_sync_payload.json`** with:
  * Pipeline stage (`Targeting`), fit scores, and disclosed WA/CA salary bands
  * Pre-built **Alumni & Hiring Manager Contact Search URLs** (filtered by target company + your school from `candidate_profile.json`)
  * Ready-to-send outreach notes for your CareerOS Contacts CRM

### 5. Onboard Another User (Without Touching Code)
```bash
python3 main.py --init-profile classmate_profile.json
python3 main.py --profile classmate_profile.json
```

---

## Outputs
* **`reports/latest_briefing.md`** (and dated `reports/job_briefing_YYYY-MM-DD.md`): Full executive Markdown dossier with clickable apply links, salary bands, rubric breakdowns, Skeptical Hiring Manager critiques, tailored resume bullets, and ready-to-send outreach notes.
* **`data/seen_jobs.json`**: Persistent agent memory tracking previously discovered jobs and scores across runs.
* **`data/latest_evaluated_jobs.json`**: Full structured JSON output of evaluated matches.
