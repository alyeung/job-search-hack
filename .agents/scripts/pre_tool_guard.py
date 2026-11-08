#!/usr/bin/env python3
"""Antigravity PreToolUse Safety Gate Hook (Harness Engineering Layer).

Implements deterministic allow/deny/ask rules:
  1. Immediately DENY destructive filesystem/git commands or secret/PII exfiltration.
  2. Escalate (ASK) before deleting local job tracking data or pushing code.
  3. Auto-approve (ALLOW) safe development, testing, and job search CLI commands.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

DENY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+(/|~|\$HOME|\.\.)(\s|$)"),
        "Blocked destructive recursive deletion outside workspace.",
    ),
    (
        re.compile(r"\bgit\s+push\s+.*--force"),
        "Blocked force-push command by repository safety gate.",
    ),
    (
        re.compile(
            r"\b(curl|wget)\b.*(\.env|GEMINI_API_KEY|GOOGLE_API_KEY|CAREEROS_BEARER_TOKEN|candidate_profile\.json)"
        ),
        "Blocked potential credential or personal profile exfiltration over network command.",
    ),
]

ASK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\brm\b.*(seen_jobs\.json|careeros_job_tracker\.csv|latest_briefing\.md)"),
        "Deleting tracked job memory or reports requires user confirmation.",
    ),
    (
        re.compile(r"\bsudo\b"),
        "Privileged sudo execution requires explicit user confirmation.",
    ),
    (
        re.compile(r"\bgit\s+push\b"),
        "Pushing to remote repository requires user confirmation.",
    ),
]


def evaluate_command(command_line: str) -> dict[str, Any]:
    """Evaluate a shell command string against deterministic harness rules."""
    cmd = (command_line or "").strip()
    if not cmd:
        return {"decision": "allow", "reason": "Empty command."}

    for pattern, reason in DENY_PATTERNS:
        if pattern.search(cmd):
            return {"decision": "deny", "reason": reason}

    for pattern, reason in ASK_PATTERNS:
        if pattern.search(cmd):
            return {"decision": "ask", "reason": reason}

    return {
        "decision": "allow",
        "reason": "Command passed job-search harness safety gate.",
    }


def main() -> None:
    try:
        raw_input = sys.stdin.read()
        payload = json.loads(raw_input) if raw_input.strip() else {}
    except Exception:
        print(json.dumps({"decision": "allow"}))
        return

    tool_call = payload.get("toolCall", {})
    tool_name = tool_call.get("name", "")
    args = tool_call.get("args", {}) or {}

    if tool_name == "run_command":
        cmd = str(args.get("CommandLine", ""))
        result = evaluate_command(cmd)
        print(json.dumps(result))
        return

    print(json.dumps({"decision": "allow"}))


if __name__ == "__main__":
    main()
