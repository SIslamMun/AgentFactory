"""IngestorAgent — constrains any backend agent to the ``assimilate`` action.

Wraps a backend agent (IOWarpAgent, LLMAgent, or ClaudeAgent) and ensures
the only action it can produce is ``assimilate``.  If the backend returns a
different action, IngestorAgent overrides it with ``assimilate`` using
best-effort parameter extraction from the observation text.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_factory.agents.iowarp_agent import IOWarpAgent
from agent_factory.core.types import Action, Observation

log = logging.getLogger(__name__)

_INGESTOR_PREFIX = (
    "You are an ingestion specialist for the IOWarp context engine. "
    "Your only allowed action is 'assimilate'. "
    "Extract src (URI), dst (tag), and format from the user instruction.\n\n"
)


class IngestorAgent:
    """Agent that constrains its backend to the ``assimilate`` action.

    Satisfies the ``Agent`` protocol from ``agent_factory.core.protocols``.
    """

    def __init__(
        self,
        backend: Any,
        *,
        default_tag: str = "default",
        default_format: str = "arrow",
    ) -> None:
        self._backend = backend
        self._default_tag = default_tag
        self._default_format = default_format

    def think(self, observation: Observation) -> str:
        """Prepend ingestor context and delegate to backend."""
        augmented = Observation(
            text=_INGESTOR_PREFIX + observation.text,
            data=observation.data,
            done=observation.done,
        )
        return self._backend.think(augmented)

    def act(self, observation: Observation) -> Action:
        """Delegate to backend; override to ``assimilate`` if needed."""
        augmented = Observation(
            text=_INGESTOR_PREFIX + observation.text,
            data=observation.data,
            done=observation.done,
        )
        action = self._backend.act(augmented)

        if action.name == "assimilate":
            # Ensure defaults are filled in
            params = dict(action.params)
            # If dst was set to the generic "default" by extraction fallback,
            # replace with this agent's configured default_tag
            if params.get("dst") == "default" and self._default_tag != "default":
                params["dst"] = self._default_tag
            params.setdefault("dst", self._default_tag)
            params.setdefault("format", self._default_format)
            return Action(name="assimilate", params=params)

        # Backend returned a non-assimilate action — override
        log.info(
            "IngestorAgent: backend returned '%s', overriding to 'assimilate'",
            action.name,
        )
        params = self._build_assimilate_params(observation.text)
        return Action(name="assimilate", params=params)

    def _build_assimilate_params(self, text: str) -> dict[str, Any]:
        """Best-effort extraction of assimilate params from observation text."""
        src = IOWarpAgent._extract_uri(text)
        tag = IOWarpAgent._extract_tag(text)
        return {
            "src": src,
            "dst": tag if tag != "default" else self._default_tag,
            "format": self._default_format,
        }
