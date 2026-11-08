#!/usr/bin/env python3
"""
Entrypoint for the Profile-Driven AI Job Search Agent.
- Built for everyone: zero hardcoded personal data in code.
- Customized for you: edit `candidate_profile.json` (or pass `--profile another_profile.json`).
"""

import argparse
import os
from pathlib import Path
import sys

from src.agent import JobSearchAgent
from src.profile import create_profile_from_template


def _load_dotenv_if_present(dotenv_path: str = ".env") -> None:
    """Lightweight .env loader requiring no external package."""
    path = Path(dotenv_path)
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = val


def main() -> int:
    _load_dotenv_if_present()

    parser = argparse.ArgumentParser(
        description="Autonomous & Interactive AI Job Search Agent (Profile-Driven)"
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="candidate_profile.json",
        help="Path to the candidate profile JSON file (default: candidate_profile.json)",
    )
    parser.add_argument(
        "--init-profile",
        type=str,
        metavar="NEW_PROFILE_JSON",
        help="Create a new candidate profile JSON from candidate_profile.template.json for another user",
    )
    parser.add_argument(
        "--companies",
        nargs="+",
        help="Optional subset of company slugs to query (e.g. --companies anthropic openai cloudflare stripe)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Number of top-scoring matches to generate full Application Kits for (default: 5)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=65.0,
        help="Minimum rubric score (0-100) to include in ranked matches (default: 65.0)",
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="Launch interactive conversational agent mode",
    )
    parser.add_argument(
        "--sync-careeros",
        action="store_true",
        help="Sync preferences from CareerOS (https://app.thecareeros.com/app/preferences) using CAREEROS_BEARER_TOKEN / CAREEROS_SESSION_COOKIE",
    )
    parser.add_argument(
        "--import-careeros",
        type=str,
        metavar="CAREEROS_FILE",
        help="Import saved text/JSON/HTML preferences from https://app.thecareeros.com/app/preferences into candidate_profile.json",
    )

    args = parser.parse_args()

    if args.init_profile:
        try:
            dest = create_profile_from_template(args.init_profile)
            print(
                f"Created new profile at '{dest}'.\n"
                f"Customize that file and run:\n  python3 main.py --profile {dest}"
            )
            return 0
        except Exception as e:
            print(f"Error creating profile: {e}", file=sys.stderr)
            return 1

    try:
        agent = JobSearchAgent(profile_path=args.profile)
    except Exception as e:
        print(f"Error loading profile '{args.profile}': {e}", file=sys.stderr)
        return 1

    if args.import_careeros:
        try:
            res = agent.tool_sync_careeros(import_file=args.import_careeros)
            print(
                f"CareerOS Import Complete ({res['status']}): Updated {res['updated_fields']} in '{res['profile_path']}'"
            )
        except Exception as e:
            print(f"CareerOS import error: {e}", file=sys.stderr)
            return 1

    if args.sync_careeros:
        res = agent.tool_sync_careeros()
        print(f"[CareerOS Sync] {res['message']}")

    if args.chat:
        agent.run_interactive_chat()
        return 0

    agent.run_autonomous(
        override_companies=args.companies,
        top_n=args.top,
        min_score=args.min_score,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
