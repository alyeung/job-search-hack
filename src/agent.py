"""
Autonomous & Interactive Job Search AI Agent
Uses a profile-driven Tool-Calling & Reflection Loop (Sense -> Discover -> Evaluate -> Critique & Draft -> Report).
Works for ANY user by reading all rules, targets, and credentials from `candidate_profile.json`.
"""

from datetime import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

from src.evaluators.fit_evaluator import (
    _call_gemini_json,
    evaluate_job_rubric,
    generate_application_kit,
)
from src.fetchers.ashby import fetch_ashby_jobs
from src.fetchers.greenhouse import fetch_greenhouse_jobs
from src.fetchers.linkedin import fetch_linkedin_jobs
from src.integrations.careeros import (
    CAREEROS_PREFERENCES_URL,
    export_matches_for_careeros,
    import_careeros_preferences_file,
    sync_preferences_from_careeros,
)
from src.profile import DEFAULT_PROFILE_PATH, load_candidate_profile

logger = logging.getLogger(__name__)


class JobSearchAgent:
    """
    Profile-driven AI Agent that discovers live jobs across ATS platforms,
    scores them against a weighted candidate rubric, runs a Skeptical Hiring Manager
    critique on top matches, and generates tailored resume bullets + outreach notes.
    """

    def __init__(
        self,
        profile_path: str | Path = DEFAULT_PROFILE_PATH,
        data_dir: str | Path = "data",
        reports_dir: str | Path = "reports",
    ) -> None:
        self.profile_path = Path(profile_path)
        self.profile: Dict[str, Any] = load_candidate_profile(self.profile_path)
        self.data_dir = Path(data_dir)
        self.reports_dir = Path(reports_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self.memory_file = self.data_dir / "seen_jobs.json"
        self.latest_results_file = self.data_dir / "latest_evaluated_jobs.json"

        self.discovered_jobs: List[Dict[str, Any]] = []
        self.evaluated_jobs: List[Dict[str, Any]] = []
        self.seen_jobs: Dict[str, Any] = self._load_memory()

    # ------------------------------------------------------------------
    # Tool 1: Memory Management (`data/seen_jobs.json`)
    # ------------------------------------------------------------------
    def _load_memory(self) -> Dict[str, Any]:
        if self.memory_file.exists():
            try:
                with self.memory_file.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Could not read memory file %s: %s", self.memory_file, e)
        return {}

    def save_memory(self) -> None:
        """Persist seen jobs and scores to `data/seen_jobs.json` and `data/latest_evaluated_jobs.json`."""
        now_iso = datetime.now().isoformat(timespec="seconds")
        for ev in self.evaluated_jobs:
            jid = ev.get("job_id")
            if jid:
                self.seen_jobs[jid] = {
                    "company": ev.get("company"),
                    "title": ev.get("title"),
                    "location": ev.get("location"),
                    "score": ev.get("total_score"),
                    "first_seen": self.seen_jobs.get(jid, {}).get("first_seen", now_iso),
                    "last_evaluated": now_iso,
                }
        with self.memory_file.open("w", encoding="utf-8") as f:
            json.dump(self.seen_jobs, f, indent=2)

        with self.latest_results_file.open("w", encoding="utf-8") as f:
            json.dump(self.evaluated_jobs, f, indent=2)

    # ------------------------------------------------------------------
    # Tool 2: Inspect Candidate Profile
    # ------------------------------------------------------------------
    def tool_inspect_profile(self) -> Dict[str, Any]:
        """Return a structured summary of the active candidate profile & rubric."""
        prefs = self.profile.get("search_preferences", {})
        boards = prefs.get("target_boards", {})
        constraints = self.profile.get("constraints_and_comp", {})
        careeros = self.profile.get("careeros_integration", {})
        return {
            "profile_file": str(self.profile_path),
            "candidate_name": self.profile.get("name"),
            "location": self.profile.get("location"),
            "target_locations": self.profile.get("target_locations", []),
            "target_roles": self.profile.get("target_roles", []),
            "target_domains": self.profile.get("target_domains", []),
            "min_base_salary_usd": constraints.get("min_base_salary_usd", 0),
            "scoring_weights": self.profile.get("scoring_weights", {}),
            "greenhouse_targets_count": len(boards.get("greenhouse", [])),
            "ashby_targets_count": len(boards.get("ashby", [])),
            "careeros_preferences_url": careeros.get(
                "preferences_url", CAREEROS_PREFERENCES_URL
            ),
        }

    # ------------------------------------------------------------------
    # Tool 2b: CareerOS Preferences Sync & Tracker Export
    # ------------------------------------------------------------------
    def tool_sync_careeros(
        self, import_file: Optional[str | Path] = None
    ) -> Dict[str, Any]:
        """
        Sync or import candidate preferences from CareerOS
        (https://app.thecareeros.com/app/preferences) into `candidate_profile.json`.
        """
        if import_file:
            res = import_careeros_preferences_file(
                import_file, self.profile, self.profile_path
            )
            self.profile = load_candidate_profile(self.profile_path)
            return res
        res = sync_preferences_from_careeros(self.profile, self.profile_path)
        if res.get("status") == "synced":
            self.profile = load_candidate_profile(self.profile_path)
        return res

    def tool_export_careeros(self, top_n: int = 15) -> Dict[str, Path]:
        """Export evaluated matches into CareerOS Job Tracker CSV & JSON payload."""
        return export_matches_for_careeros(
            self.evaluated_jobs,
            self.profile,
            reports_dir=self.reports_dir,
            data_dir=self.data_dir,
            top_n=top_n,
        )

    # ------------------------------------------------------------------
    # Tool 3: Multi-ATS Live Job Discovery
    # ------------------------------------------------------------------
    def tool_discover_jobs(
        self,
        override_companies: Optional[List[str]] = None,
        filter_by_location: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Fetch live jobs from Greenhouse and Ashby using the active profile's
        `search_preferences` (role include/exclude keywords, locations, target boards).
        """
        prefs = self.profile.get("search_preferences", {})
        include_kw = prefs.get("role_title_include_keywords", [])
        exclude_kw = prefs.get("role_title_exclude_keywords", [])
        loc_kw = prefs.get("location_keywords", []) if filter_by_location else None

        boards = prefs.get("target_boards", {})
        gh_companies: List[str] = boards.get("greenhouse", [])
        ashby_companies: List[str] = boards.get("ashby", [])

        if override_companies:
            override_lower = [c.lower() for c in override_companies]
            gh_filtered = [c for c in override_lower if c not in ashby_companies]
            ashby_filtered = [c for c in override_lower if c in ashby_companies or c in ("openai", "linear", "ramp", "supabase", "perplexity", "cohere", "langchain")]
            # Any company not known in Ashby defaults to trying Greenhouse too
            gh_companies = gh_filtered
            ashby_companies = ashby_filtered

        gh_jobs = (
            fetch_greenhouse_jobs(
                companies=gh_companies,
                keyword_filter=include_kw,
                exclude_keywords=exclude_kw,
                location_filter=loc_kw,
            )
            if gh_companies
            else []
        )

        ashby_jobs = (
            fetch_ashby_jobs(
                companies=ashby_companies,
                keyword_filter=include_kw,
                exclude_keywords=exclude_kw,
                location_filter=loc_kw,
            )
            if ashby_companies
            else []
        )

        # Fetch live LinkedIn jobs using the candidate's top target roles and locations
        li_queries = prefs.get("linkedin_queries") or [
            f"{role} {self.profile.get('target_domains', [''])[0].split()[0]}".strip()
            for role in self.profile.get("target_roles", ["Product Manager"])[:2]
        ]
        li_locations = [
            loc
            for loc in self.profile.get("target_locations", ["Seattle, WA"])
            if loc.lower() != "remote"
        ]
        linkedin_jobs = (
            fetch_linkedin_jobs(
                search_queries=li_queries,
                locations=li_locations,
                keyword_filter=include_kw,
                exclude_keywords=exclude_kw,
                location_filter=loc_kw,
                max_per_query=5,
                fetch_details=True,
            )
            if not override_companies or "linkedin" in [c.lower() for c in override_companies]
            else []
        )

        self.discovered_jobs = gh_jobs + ashby_jobs + linkedin_jobs
        return self.discovered_jobs

    # ------------------------------------------------------------------
    # Tool 4: Rubric Evaluation & Ranking
    # ------------------------------------------------------------------
    def tool_evaluate_and_rank(
        self,
        min_score: float = 65.0,
    ) -> List[Dict[str, Any]]:
        """
        Evaluate all discovered jobs against the candidate profile's 4-dimension
        weighted rubric, tag new vs. previously seen jobs, and sort descending by score.
        """
        jobs_by_id = {j["id"]: j for j in self.discovered_jobs if j.get("id")}
        results: List[Dict[str, Any]] = []

        for job in self.discovered_jobs:
            ev = evaluate_job_rubric(job, self.profile)
            ev["is_new"] = job.get("id") not in self.seen_jobs
            if ev["total_score"] >= min_score:
                results.append(ev)

        results.sort(
            key=lambda x: (
                x.get("total_score", 0.0),
                1 if x.get("company_tier") == "Tier 1 Priority" else 0,
                x.get("salary_range") != "Not Disclosed",
            ),
            reverse=True,
        )

        # Keep reference to raw job payload for top matches
        for ev in results:
            ev["_raw_job"] = jobs_by_id.get(ev["job_id"], {})

        self.evaluated_jobs = results
        return results

    # ------------------------------------------------------------------
    # Tool 5: Conditional Deep Action — Critique & Application Kit
    # ------------------------------------------------------------------
    def tool_generate_application_kits(self, top_n: int = 5) -> List[Dict[str, Any]]:
        """
        For the top N highest-scoring roles, run the Skeptical Hiring Manager critique
        and generate tailored resume bullets + personalized cold outreach notes.
        """
        top_matches = self.evaluated_jobs[:top_n]
        for ev in top_matches:
            raw_job = ev.pop("_raw_job", None) or {
                "company": ev.get("company"),
                "title": ev.get("title"),
                "location": ev.get("location"),
                "salary_range": ev.get("salary_range"),
                "plain_text": "",
            }
            kit = generate_application_kit(raw_job, ev, self.profile)
            ev["application_kit"] = kit

        # Clean up any remaining _raw_job keys on lower-ranked items
        for ev in self.evaluated_jobs[top_n:]:
            ev.pop("_raw_job", None)

        # Re-sort top matches in case Gemini LLM refined their scores
        self.evaluated_jobs.sort(key=lambda x: x.get("total_score", 0.0), reverse=True)
        return self.evaluated_jobs[:top_n]

    # ------------------------------------------------------------------
    # Tool 6: Generate Executive Markdown Report (`reports/`)
    # ------------------------------------------------------------------
    def tool_save_report(
        self,
        top_n: int = 5,
        filename: Optional[str] = None,
    ) -> Path:
        """Write an executive Markdown briefing to `reports/`."""
        candidate_name = self.profile.get("name", "Candidate")
        date_str = datetime.now().strftime("%Y-%m-%d")
        report_name = filename or f"job_briefing_{date_str}.md"
        report_path = self.reports_dir / report_name
        latest_alias = self.reports_dir / "latest_briefing.md"

        weights = self.profile.get("scoring_weights", {})
        constraints = self.profile.get("constraints_and_comp", {})
        min_sal = constraints.get("min_base_salary_usd", 0)
        api_mode = (
            "Google Gemini LLM + Rubric"
            if (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
            else "Profile Rubric + Deterministic Strategist (Set GEMINI_API_KEY for live Gemini LLM)"
        )

        new_count = sum(1 for j in self.evaluated_jobs if j.get("is_new"))

        lines: List[str] = [
            f"# AI Job Search Agent Briefing — {candidate_name}",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')} | **Profile:** `{self.profile_path.name}` | **Engine:** {api_mode}",
            "",
            "## 1. Agent Run Summary",
            f"- **Target Locations:** {', '.join(self.profile.get('target_locations', []))}",
            f"- **Compensation Floor:** ${min_sal:,}+ Base USD" if min_sal else "- **Compensation Floor:** Not specified",
            f"- **Scoring Rubric Weights:** Role/Seniority ({weights.get('role_and_seniority_fit', 30)}%) · Domain/Tech ({weights.get('domain_and_technical_fit', 30)}%) · Candidate Edge ({weights.get('candidate_edge_and_pedigree', 25)}%) · Location/Comp ({weights.get('location_and_compensation_fit', 15)}%)",
            f"- **Jobs Discovered (Role + Location Filtered):** {len(self.discovered_jobs)}",
            f"- **High-Fit Matches Evaluated:** {len(self.evaluated_jobs)} ({new_count} newly discovered)",
            "",
            "## 2. Leaderboard (Top 15 Ranked Matches)",
            "",
            "| Rank | Score | Company | Role Title | Location | Disclosed Base Salary | Tier |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        for idx, ev in enumerate(self.evaluated_jobs[:15], start=1):
            new_badge = "🆕 " if ev.get("is_new") else ""
            title_link = f"[{ev.get('title')}]({ev.get('url')})" if ev.get("url") else ev.get("title", "")
            lines.append(
                f"| #{idx} | **{ev.get('total_score')}/100** | **{ev.get('company')}** | {new_badge}{title_link} | {ev.get('location')} | `{ev.get('salary_range')}` | {ev.get('company_tier')} |"
            )

        lines.extend(
            [
                "",
                f"## 3. Deep-Dive Dossiers & Tailored Application Kits (Top {min(top_n, len(self.evaluated_jobs))})",
                "",
            ]
        )

        for idx, ev in enumerate(self.evaluated_jobs[:top_n], start=1):
            bd = ev.get("score_breakdown", {})
            critique = ev.get("hiring_manager_critique", {})
            kit = ev.get("application_kit", {})
            bullets = kit.get("tailored_resume_bullets", [])
            outreach = kit.get("outreach_message", "")

            lines.extend(
                [
                    f"### #{idx}. {ev.get('company')} — {ev.get('title')} (Score: {ev.get('total_score')}/100)",
                    f"- **Apply Link:** [{ev.get('url')}]({ev.get('url')})",
                    f"- **Location:** {ev.get('location')} (*{ev.get('location_note')}*)",
                    f"- **Compensation:** `{ev.get('compensation_note')}`",
                    f"- **Rubric Breakdown:** Role/Seniority `{bd.get('role_and_seniority_fit')}` · Domain/Tech `{bd.get('domain_and_technical_fit')}` · Edge `{bd.get('candidate_edge_and_pedigree')}` · Location/Comp `{bd.get('location_and_compensation_fit')}`",
                    "",
                    "#### Why You Fit",
                    f"> {ev.get('why_you_fit')}",
                    "",
                    "#### Skeptical Hiring Manager Critique",
                    f"- **Likely Objection:** {critique.get('likely_objection', '')}",
                    f"- **How to Preempt:** {critique.get('how_to_preempt', '')}",
                    "",
                    "#### Tailored Resume Bullet Hooks",
                ]
            )
            for b in bullets:
                lines.append(f"- {b}")

            lines.extend(
                [
                    "",
                    "#### Ready-to-Send Hiring Manager Outreach",
                    "```text",
                    outreach,
                    "```",
                    "",
                    "---",
                    "",
                ]
            )

        content = "\n".join(lines)
        report_path.write_text(content, encoding="utf-8")
        latest_alias.write_text(content, encoding="utf-8")
        return report_path

    # ------------------------------------------------------------------
    # Autonomous Agent Execution Loop (Plan -> Act -> Observe -> Reflect)
    # ------------------------------------------------------------------
    def run_autonomous(
        self,
        override_companies: Optional[List[str]] = None,
        top_n: int = 5,
        min_score: float = 65.0,
    ) -> Path:
        """
        Execute the full 5-step autonomous agent reasoning loop with transparent
        terminal trace logs showing each Tool Call, Observation, and Decision.
        """
        print("=" * 76)
        print("🤖 AUTONOMOUS JOB SEARCH AI AGENT")
        print("=" * 76)

        # Step 1: Sense Profile & Memory
        prof_info = self.tool_inspect_profile()
        print(
            f"\n[Step 1/5 · Tool: inspect_candidate_profile] Loaded '{prof_info['profile_file']}'"
        )
        print(f"  ├─ Candidate:        {prof_info['candidate_name']} ({prof_info['location']})")
        print(
            f"  ├─ Target Locations: {', '.join(prof_info['target_locations'])}"
        )
        print(
            f"  ├─ Target Domains:   {', '.join(prof_info['target_domains'][:4])}"
        )
        print(
            f"  ├─ Comp Floor:       ${prof_info['min_base_salary_usd']:,}+ Base USD"
        )
        print(
            f"  └─ Agent Memory:     {len(self.seen_jobs)} previously tracked jobs in '{self.memory_file}'"
        )

        # Step 2: Multi-Source Discovery
        print(
            "\n[Step 2/5 · Tool: discover_live_jobs] Querying Greenhouse, Ashby, and LinkedIn..."
        )
        discovered = self.tool_discover_jobs(override_companies=override_companies)
        gh_count = sum(1 for j in discovered if j.get("source") == "greenhouse")
        ashby_count = sum(1 for j in discovered if j.get("source") == "ashby")
        li_count = sum(1 for j in discovered if j.get("source") == "linkedin")
        sal_disclosed = sum(
            1 for j in discovered if j.get("salary_range") != "Not Disclosed"
        )
        print(
            f"  ├─ Observation: Found {len(discovered)} role & location-matched jobs "
            f"({gh_count} Greenhouse, {ashby_count} Ashby, {li_count} LinkedIn)."
        )
        print(
            f"  └─ Pay Transparency Parser: Extracted USD salary bands from {sal_disclosed}/{len(discovered)} postings."
        )

        if not discovered:
            print(
                "\n[Agent Reflection] Zero matching jobs found with strict location filter. "
                "Relaxing location filter to inspect broader openings..."
            )
            discovered = self.tool_discover_jobs(
                override_companies=override_companies, filter_by_location=False
            )
            print(f"  └─ Observation: Found {len(discovered)} role-matched jobs.")

        # Step 3: Weighted Rubric Evaluation & Ranking
        print(
            f"\n[Step 3/5 · Tool: evaluate_and_rank_jobs] Scoring {len(discovered)} jobs against "
            f"{prof_info['candidate_name']}'s weighted rubric (threshold >= {min_score})..."
        )
        ranked = self.tool_evaluate_and_rank(min_score=min_score)
        new_matches = sum(1 for r in ranked if r.get("is_new"))
        print(
            f"  ├─ Observation: {len(ranked)} jobs passed the {min_score}/100 threshold ({new_matches} new)."
        )
        for idx, r in enumerate(ranked[: min(8, len(ranked))], start=1):
            print(
                f"  │  #{idx} [{r['total_score']:>4}/100] {r['company']} — {r['title']} "
                f"({r['location']}) | {r['salary_range']}"
            )

        # Step 4: Conditional Deep Action on Top Matches
        actual_top = min(top_n, len(ranked))
        llm_active = bool(
            os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        )
        engine_label = (
            "Google Gemini LLM"
            if llm_active
            else "Profile Strategist (set GEMINI_API_KEY for live Gemini LLM)"
        )
        print(
            f"\n[Step 4/5 · Tool: generate_application_kits] Running Skeptical Hiring Manager "
            f"Critique & drafting custom bullets/outreach for Top {actual_top} matches via {engine_label}..."
        )
        top_kits = self.tool_generate_application_kits(top_n=actual_top)
        for idx, ev in enumerate(top_kits, start=1):
            critique = ev.get("hiring_manager_critique", {})
            print(
                f"  ├─ #{idx} {ev['company']} ({ev['title']}) -> Score: {ev['total_score']}/100"
            )
            print(
                f"  │    • HM Objection Preempted: {critique.get('likely_objection', '')[:95]}..."
            )

        # Step 5: Persist Memory, CareerOS Export & Publish Executive Report
        print(
            "\n[Step 5/5 · Tool: save_briefing_report & export_careeros] Saving agent memory, CareerOS tracker, and Markdown dossier..."
        )
        self.save_memory()
        careeros_paths = self.tool_export_careeros(top_n=15)
        report_path = self.tool_save_report(top_n=actual_top)
        print(f"  ├─ Updated Memory:   {self.memory_file}")
        print(f"  ├─ Evaluated JSON:   {self.latest_results_file}")
        print(
            f"  ├─ CareerOS Tracker: {careeros_paths['csv_path']} (synced for {prof_info['careeros_preferences_url']})"
        )
        print(f"  └─ Briefing Report:  {report_path} (and reports/latest_briefing.md)")
        print("=" * 76)
        return report_path

    # ------------------------------------------------------------------
    # Interactive Conversational Agent Mode (`--chat`)
    # ------------------------------------------------------------------
    def run_interactive_chat(self) -> None:
        """
        Interactive conversational loop where the user can ask the agent to search
        specific companies, explain match scores, critique roles, or draft outreach.
        """
        prof = self.tool_inspect_profile()
        print("=" * 76)
        print(
            f"💬 INTERACTIVE JOB SEARCH AGENT — Loaded Profile: {prof['candidate_name']} ({self.profile_path.name})"
        )
        print(
            "Commands you can ask naturally:\n"
            "  • 'run' or 'search anthropic openai cloudflare databricks'\n"
            "  • 'show top 5' or 'explain #1'\n"
            "  • 'outreach #2' (show tailored resume bullets & cold outreach for rank #2)\n"
            "  • 'profile' (show active profile & rubric weights)\n"
            "  • 'exit' or 'quit'"
        )
        print("=" * 76)

        # Load cached evaluated jobs if available so user can query immediately
        if not self.evaluated_jobs and self.latest_results_file.exists():
            try:
                self.evaluated_jobs = json.loads(
                    self.latest_results_file.read_text(encoding="utf-8")
                )
                print(
                    f"Loaded {len(self.evaluated_jobs)} evaluated matches from previous run ({self.latest_results_file})."
                )
            except Exception:
                pass

        while True:
            try:
                user_input = input("\nYou > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting interactive agent.")
                break

            if not user_input:
                continue
            low = user_input.lower()
            if low in ("exit", "quit", "q"):
                print("Goodbye!")
                break

            if low in ("profile", "show profile", "rubric"):
                print(json.dumps(self.tool_inspect_profile(), indent=2))
                continue

            if low.startswith("search") or low == "run":
                parts = [
                    p.strip(", ")
                    for p in low.replace("search", "").replace("run", "").split()
                    if p.strip(", ")
                ]
                override = parts if parts else None
                self.run_autonomous(override_companies=override, top_n=5)
                continue

            if "top" in low or "list" in low or "leaderboard" in low:
                if not self.evaluated_jobs:
                    print("No jobs evaluated yet. Running discovery now...")
                    self.run_autonomous(top_n=5)
                else:
                    for i, ev in enumerate(self.evaluated_jobs[:10], start=1):
                        print(
                            f"#{i} [{ev['total_score']}/100] {ev['company']} — {ev['title']} ({ev['location']}) | {ev['salary_range']}"
                        )
                continue

            # Check if user references a specific rank like #1, #2, 1, 2
            rank_idx = None
            for tok in low.replace("#", " #").split():
                if tok.startswith("#") and tok[1:].isdigit():
                    rank_idx = int(tok[1:]) - 1
                    break

            if rank_idx is not None and 0 <= rank_idx < len(self.evaluated_jobs):
                ev = self.evaluated_jobs[rank_idx]
                if not ev.get("application_kit"):
                    ev["application_kit"] = generate_application_kit(ev, ev, self.profile)
                kit = ev["application_kit"]
                critique = ev.get("hiring_manager_critique", {})
                print(
                    f"\n=== #{rank_idx + 1}: {ev['company']} — {ev['title']} ({ev['total_score']}/100) ==="
                )
                print(f"URL:      {ev.get('url')}")
                print(f"Location: {ev.get('location')} | Salary: {ev.get('salary_range')}")
                print(f"\nWhy You Fit:\n  {ev.get('why_you_fit')}")
                print(
                    f"\nSkeptical Hiring Manager Critique:\n  • Objection: {critique.get('likely_objection')}\n  • Preempt:   {critique.get('how_to_preempt')}"
                )
                print("\nTailored Resume Bullets:")
                for b in kit.get("tailored_resume_bullets", []):
                    print(f"  - {b}")
                print(f"\nOutreach Message:\n{kit.get('outreach_message')}")
                continue

            # If GEMINI_API_KEY is available, answer open-ended career/job questions with context
            ans = _call_gemini_json(
                f"Answer the user's question concisely using their candidate profile and top evaluated jobs.\n"
                f"Profile: {json.dumps(self.tool_inspect_profile())}\n"
                f"Top 5 Evaluated Jobs: {json.dumps(self.evaluated_jobs[:5])}\n"
                f"User Question: {user_input}\n"
                f"Return JSON: {{\"answer\": \"<your response>\"}}"
            )
            if ans and ans.get("answer"):
                print(f"\nAgent > {ans['answer']}")
            else:
                print(
                    "\nAgent > Try commands like `run`, `search anthropic openai`, `top`, `explain #1`, `outreach #2`, or `profile`."
                )
