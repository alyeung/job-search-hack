"""Google ADK Fit Scoring, Rubric & Outreach Tools."""

from __future__ import annotations

from typing import Any

from src.agent import JobSearchAgent
from src.evaluators.fit_evaluator import evaluate_job_rubric, generate_application_kit
from src.profile import load_candidate_profile


def score_and_rank_all_jobs(
    companies: list[str] | None = None,
    min_score: float = 65.0,
    top_n: int = 5,
    profile_path: str = "candidate_profile.json",
) -> dict[str, Any]:
    """Discover jobs across Greenhouse, Ashby, and LinkedIn, score them on the 0-100 rubric, and export reports."""
    try:
        agent = JobSearchAgent(profile_path=profile_path)
        agent.tool_discover_jobs(override_companies=companies)
        ranked = agent.tool_evaluate_and_rank(min_score=min_score)
        top_kits = agent.tool_generate_application_kits(top_n=top_n)
        agent.save_memory()
        careeros_paths = agent.tool_export_careeros(top_n=15)
        report_path = agent.tool_save_report(top_n=top_n)
        return {
            "status": "success",
            "discovered_count": len(agent.discovered_jobs),
            "matched_count": len(ranked),
            "report_path": str(report_path),
            "careeros_csv_path": str(careeros_paths["csv_path"]),
            "top_matches": top_kits,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def generate_tailored_outreach_for_job(
    company: str,
    title: str,
    location: str,
    job_description: str = "",
    salary_range: str = "Not Disclosed",
    profile_path: str = "candidate_profile.json",
) -> dict[str, Any]:
    """Evaluate a specific job and generate a Skeptical Hiring Manager critique, tailored bullets, and outreach note."""
    try:
        profile = load_candidate_profile(profile_path)
        job = {
            "id": f"custom_{company.lower()}_{title.lower()[:15]}",
            "company": company,
            "title": title,
            "location": location,
            "plain_text": job_description,
            "salary_range": salary_range,
            "source": "manual",
            "url": "",
        }
        evaluation = evaluate_job_rubric(job, profile)
        kit = generate_application_kit(job, evaluation, profile)
        return {
            "status": "success",
            "evaluation": evaluation,
            "application_kit": kit,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
