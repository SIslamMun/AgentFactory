"""Claude Code CLI-powered IOWarp agent.

Uses the locally installed ``claude`` CLI (Claude Code) in print mode
(``claude -p``) to reason about observations and choose IOWarp actions.
Because Claude Code authenticates through the user's existing session,
**no ANTHROPIC_API_KEY is required**.

The agent sends the observation text to Claude Code as a prompt, receives
a JSON response with {thought, action, params}, and converts it into an
Action the environment can execute — exactly the same interface as
IOWarpAgent and LLMAgent.

Requires:
    Claude Code CLI installed and authenticated (``claude --version``).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Any

from agent_factory.core.types import Action, Observation

log = logging.getLogger(__name__)

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

IMPORTANT: Respond with ONLY the JSON object. No markdown, no code fences,
no explanation outside the JSON.
"""


def _parse_response(raw: str) -> dict[str, Any]:
    """Extract JSON from the Claude Code response, handling common quirks."""
    text = raw.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    return json.loads(text)


class ClaudeAgent:
    """Claude Code CLI-powered agent.

    Satisfies the ``Agent`` protocol from ``agent_factory.core.protocols``.

    Uses the ``claude -p`` (print mode) command to send prompts to Claude
    and receive responses without requiring an API key — authentication
    is handled by the existing Claude Code session.
    """

    def __init__(self, model: str = "sonnet") -> None:
        cli = shutil.which("claude")
        if cli is None:
            raise RuntimeError(
                "Claude Code CLI not found. "
                "Install it: https://docs.anthropic.com/en/docs/claude-code"
            )
        self._cli = cli
        self._model = model
        self._last_response: dict[str, Any] = {}

    def think(self, observation: Observation) -> str:
        """Ask Claude to reason about the observation."""
        response = self._call_claude(observation.text)
        self._last_response = response
        return response.get("thought", "No reasoning provided.")

    def act(self, observation: Observation) -> Action:
        """Ask Claude what action to take."""
        if not self._last_response:
            self._call_claude(observation.text)

        response = self._last_response
        self._last_response = {}

        action_name = response.get("action", "query")
        params = response.get("params", {})

        valid = {"assimilate", "query", "retrieve", "destroy", "prune", "list_blobs"}
        if action_name not in valid:
            log.warning(
                "Claude returned invalid action '%s', defaulting to query",
                action_name,
            )
            action_name = "query"
            params = {"tag_pattern": "*"}

        return Action(name=action_name, params=params)

    def _call_claude(self, user_text: str) -> dict[str, Any]:
        """Send the observation to Claude Code CLI and parse the JSON response."""
        try:
            result = subprocess.run(
                [
                    self._cli,
                    "-p",
                    "--model", self._model,
                    "--system-prompt", SYSTEM_PROMPT,
                    "--tools", "",
                    "--no-session-persistence",
                    user_text,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                log.warning("Claude CLI exited with code %d: %s", result.returncode, result.stderr)
                self._last_response = {
                    "thought": f"Claude CLI error: {result.stderr.strip()}",
                    "action": "query",
                    "params": {"tag_pattern": "*"},
                }
                return self._last_response

            raw = result.stdout
            log.debug("Claude CLI raw response: %s", raw)

            parsed = _parse_response(raw)
            self._last_response = parsed
            return parsed

        except json.JSONDecodeError as exc:
            log.warning("Claude returned invalid JSON: %s", exc)
            self._last_response = {
                "thought": f"Failed to parse Claude response: {exc}",
                "action": "query",
                "params": {"tag_pattern": "*"},
            }
            return self._last_response

        except subprocess.TimeoutExpired:
            log.error("Claude CLI timed out after 60s")
            self._last_response = {
                "thought": "Claude CLI timed out",
                "action": "query",
                "params": {"tag_pattern": "*"},
            }
            return self._last_response

        except Exception as exc:
            log.error("Claude CLI call failed: %s", exc)
            self._last_response = {
                "thought": f"Claude CLI error: {exc}",
                "action": "query",
                "params": {"tag_pattern": "*"},
            }
            return self._last_response
