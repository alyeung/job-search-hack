"""AI Job Search Agent Package (Google ADK).

Follows lazy-import conventions from the `google/adk-python` optimization study
to keep cold package import latency minimal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.adk.agents import LlmAgent

__all__ = ["root_agent", "get_root_agent"]


def get_root_agent() -> "LlmAgent":
    """Lazily construct and return the root Google ADK job search coordinator agent."""
    from .agent import root_agent

    return root_agent


def __getattr__(name: str):
    if name == "root_agent":
        from .agent import root_agent

        return root_agent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
