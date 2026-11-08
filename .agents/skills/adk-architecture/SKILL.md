---
name: adk-architecture
description: >-
  Use this skill when modifying or extending the Google ADK agent hierarchy,
  adding new FunctionTools, or optimizing runtime and import performance in
  job_search_agent/.
---

# Google ADK Architecture Skill

Follow these rules when building or modifying agents and tools in `job_search_agent/`.

## Steps

1. **Tool Contract Rules**:
   - Every public tool function in `job_search_agent/tools/` must use simple JSON-serializable parameter types (`str`, `int`, `float`, `bool`, `list[str]`) and return a `dict[str, Any]` with a `"status"` key (`"success"` or `"error"`).
   - Prefix all internal helpers with `_` (for example, `_sanitize_untrusted_text`, `_parse_linkedin_search_cards`).
2. **Lazy Imports**:
   - Keep `job_search_agent/__init__.py` lazy so importing `get_root_agent` does not trigger slow network calls.
3. **Verify with Pytest**:
   - Run pytest on `tests/test_job_search_agent.py` to validate tool schemas, safety hooks, and ADK agent initialization.
