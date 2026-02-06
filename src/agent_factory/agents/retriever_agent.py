"""RetrieverAgent — constrains any backend agent to query/retrieve/list_blobs.

Wraps a backend agent and ensures the action is one of the allowed retrieval
actions.  If the backend returns a disallowed action, it defaults to ``query``.

Also provides ``act_compound()`` for pipeline use: runs query then retrieves
all matching blobs.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_factory.core.types import Action, Observation, StepResult

log = logging.getLogger(__name__)

_ALLOWED_ACTIONS = frozenset({"query", "retrieve", "list_blobs"})

_RETRIEVER_PREFIX = (
    "You are a data-access specialist for the IOWarp context engine. "
    "You may look up, access, or enumerate blobs. "
    "Extract tag patterns, blob names, and parameters from the instruction.\n\n"
)


class RetrieverAgent:
    """Agent that constrains its backend to retrieval actions.

    Satisfies the ``Agent`` protocol from ``agent_factory.core.protocols``.
    """

    def __init__(
        self,
        backend: Any,
        *,
        default_tag_pattern: str = "*",
    ) -> None:
        self._backend = backend
        self._default_tag_pattern = default_tag_pattern

    def think(self, observation: Observation) -> str:
        """Prepend retriever context and delegate to backend."""
        augmented = Observation(
            text=_RETRIEVER_PREFIX + observation.text,
            data=observation.data,
            done=observation.done,
        )
        return self._backend.think(augmented)

    def act(self, observation: Observation) -> Action:
        """Delegate to backend; constrain to allowed retrieval actions."""
        augmented = Observation(
            text=_RETRIEVER_PREFIX + observation.text,
            data=observation.data,
            done=observation.done,
        )
        action = self._backend.act(augmented)

        if action.name in _ALLOWED_ACTIONS:
            return action

        # Backend returned a disallowed action — default to query
        log.info(
            "RetrieverAgent: backend returned '%s', defaulting to 'query'",
            action.name,
        )
        return Action(
            name="query",
            params={"tag_pattern": self._default_tag_pattern},
        )

    def act_compound(
        self,
        observation: Observation,
        environment: Any,
    ) -> list[StepResult]:
        """Run query then retrieve all matches (beyond Agent protocol).

        Useful for pipeline execution where we want to query and then
        automatically retrieve every matching blob.

        Returns a list of StepResult from the retrieve steps.
        """
        # Step 1: Query
        query_action = Action(
            name="query",
            params={"tag_pattern": self._default_tag_pattern},
        )
        query_result = environment.step(query_action)

        # Step 2: Retrieve each match
        results: list[StepResult] = []
        matches = query_result.observation.data.get("matches", [])
        for match in matches:
            tag = match.get("tag", "")
            for blob_name in match.get("blobs", []):
                retrieve_action = Action(
                    name="retrieve",
                    params={"tag": tag, "blob_name": blob_name},
                )
                result = environment.step(retrieve_action)
                results.append(result)

        return results
