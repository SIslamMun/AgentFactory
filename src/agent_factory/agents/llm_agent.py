"""LLM-powered IOWarp agent using Ollama.

Replaces the rule-based keyword matching with a real LLM that:
  1. Reads the observation (what the environment said)
  2. Thinks about what to do (chain-of-thought reasoning)
  3. Picks an action and extracts parameters

The LLM returns structured JSON so the environment can execute it.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import ollama

from agent_factory.core.types import Action, Observation

log = logging.getLogger(__name__)

# The system prompt teaches the LLM what tools it has and how to respond.
SYSTEM_PROMPT = """\
You are an intelligent data management agent. You interact with a data storage
system called IOWarp through an environment that understands these actions:

ACTIONS YOU CAN TAKE:
  assimilate  — Ingest files into the storage engine
                params: src (URI string — COPY EXACTLY as given), dst (tag name), format (data format)
                URI schemes: "file::path", "folder::path", "hdf5::path"
  query       — Search for stored data by tag/blob patterns
                params: tag_pattern (glob like "*" or "docs*")
  retrieve    — Get a specific piece of data back
                params: tag (tag name), blob_name (file name)
  destroy     — Permanently delete entire tag(s) from storage and cache
                params: tags (tag name or list of tag names)
  prune       — Evict specific blobs from cache only (data stays in IOWarp)
                params: tag (tag name), blob_names (list of blob names to evict)
  list_blobs  — List everything stored under a tag
                params: tag_pattern (glob like "*")

CRITICAL RULES FOR URIs:
1. URIs use DOUBLE COLON (::) not slashes. Examples:
   - "file::data/sample.txt" NOT "file://data/sample.txt"
   - "folder::/home/user/docs" NOT "folder:///home/user/docs"
   - "hdf5::./data.h5" NOT "hdf5://./data.h5"

2. When you see a URI in user input, copy it EXACTLY character-by-character.
   Do NOT convert :: to ://
   Do NOT remove ./
   Do NOT add or remove any slashes
   Do NOT normalize paths

3. If the user says "folder::path", write "folder::path" NOT "folder:///path"

HOW TO RESPOND:
You must respond with ONLY a JSON object, no other text. The JSON must have:
{
  "thought": "your reasoning about what to do and why",
  "action": "one of: assimilate, query, retrieve, destroy, prune, list_blobs",
  "params": { ... action parameters ... }
}

IMPORTANT: Respond with ONLY the JSON object. No markdown, no code fences, no explanation outside the JSON.
"""


def _parse_llm_response(raw: str) -> dict[str, Any]:
    """Extract JSON from the LLM response, handling common quirks."""
    text = raw.strip()

    # Strip markdown code fences if the LLM added them
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    return json.loads(text)


class LLMAgent:
    """LLM-powered agent using Ollama for reasoning.

    Satisfies the ``Agent`` protocol from ``agent_factory.core.protocols``.

    The LLM receives the observation text and must return a JSON object
    with thought, action, and params. The agent parses that JSON and
    returns an Action object the environment can execute.
    """

    def __init__(
        self,
        model: str = "llama3.2:latest",
        system_prompt: str | None = None,
        temperature: float = 0.1,
    ) -> None:
        self._model = model
        self._system_prompt = system_prompt or SYSTEM_PROMPT
        self._temperature = temperature
        self._last_response: dict[str, Any] = {}

    def think(self, observation: Observation) -> str:
        """Ask the LLM to reason about the observation, return the thought."""
        response = self._call_llm(observation.text)
        self._last_response = response
        return response.get("thought", "No reasoning provided.")

    def act(self, observation: Observation) -> Action:
        """Ask the LLM what action to take, return an Action object."""
        # If think() was just called with the same text, reuse the response
        # to avoid calling the LLM twice for the same observation
        if not self._last_response:
            self._call_llm(observation.text)

        response = self._last_response
        self._last_response = {}  # reset for next call

        action_name = response.get("action", "query")
        params = response.get("params", {})

        # Validate action name
        valid = {"assimilate", "query", "retrieve", "prune", "list_blobs"}
        if action_name not in valid:
            log.warning("LLM returned invalid action '%s', defaulting to query", action_name)
            action_name = "query"
            params = {"tag_pattern": "*"}

        return Action(name=action_name, params=params)

    def _call_llm(self, user_text: str) -> dict[str, Any]:
        """Send the observation to Ollama and parse the JSON response."""
        try:
            result = ollama.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": user_text},
                ],
                options={"temperature": self._temperature},
            )
            raw = result.message.content
            log.debug("LLM raw response: %s", raw)

            parsed = _parse_llm_response(raw)
            self._last_response = parsed
            return parsed

        except json.JSONDecodeError as exc:
            log.warning("LLM returned invalid JSON: %s", exc)
            self._last_response = {
                "thought": f"Failed to parse LLM response: {exc}",
                "action": "query",
                "params": {"tag_pattern": "*"},
            }
            return self._last_response

        except Exception as exc:
            log.error("Ollama call failed: %s", exc)
            self._last_response = {
                "thought": f"LLM error: {exc}",
                "action": "query",
                "params": {"tag_pattern": "*"},
            }
            return self._last_response
