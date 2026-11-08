---
name: job-discovery
description: >-
  Use this skill when searching for jobs across Greenhouse, Ashby, and LinkedIn,
  syncing CareerOS preferences, or updating the job tracker and briefing report.
---

# Multi-Source Job Discovery Skill

Follow this runbook when discovering, filtering, and scoring jobs.

## Steps

1. **Load Candidate Profile First**:
   - Call `get_candidate_profile()` before running searches so role filters, locations, and salary floors come from `candidate_profile.json`.
2. **Run Multi-Source Discovery**:
   - Query Greenhouse (`search_greenhouse_jobs`), Ashby (`search_ashby_jobs`), and LinkedIn (`search_linkedin_jobs`).
   - Ensure all external HTML passes through `_sanitize_untrusted_text()`.
3. **Score and Export**:
   - Run `score_and_rank_all_jobs()` to compute the 0-100 Fit Score, update `data/seen_jobs.json`, export `reports/careeros_job_tracker.csv`, and generate `reports/latest_briefing.md`.
