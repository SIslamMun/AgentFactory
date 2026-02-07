"""Rule-based IOWarp agent — Phase 1 placeholder for LLM-backed agent.

Analyses the observation text with simple keyword matching to decide
which IOWarp action to take.  Designed to be swapped out for an LLM
agent later with the same think()/act() interface.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from agent_factory.core.types import Action, Observation

log = logging.getLogger(__name__)

# Keyword → action mapping (order matters — first match wins).
# Matched with word boundaries so "ingestion" won't match "ingest".
_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bingest\b"), "assimilate"),
    (re.compile(r"\bassimilate\b"), "assimilate"),
    (re.compile(r"\bimport\b"), "assimilate"),
    (re.compile(r"\bload\b"), "assimilate"),
    (re.compile(r"\bfind\b"), "query"),
    (re.compile(r"\bsearch\b"), "query"),
    (re.compile(r"\bquery\b"), "query"),
    (re.compile(r"\blist\b"), "list_blobs"),
    (re.compile(r"\bget\b"), "retrieve"),
    (re.compile(r"\bretrieve\b"), "retrieve"),
    (re.compile(r"\bfetch\b"), "retrieve"),
    (re.compile(r"\bread\b"), "retrieve"),
    (re.compile(r"\bdestroy\b"), "destroy"),  # Permanent deletion (tag-level)
    (re.compile(r"\bprune\b"), "prune"),      # Cache eviction (blob-level)
    (re.compile(r"\bevict\b"), "prune"),
    (re.compile(r"\bdelete\b"), "destroy"),   # Default to permanent
    (re.compile(r"\bremove\b"), "destroy"),
]


class IOWarpAgent:
    """Rule-based agent that maps observation keywords to IOWarp actions.

    Satisfies the ``Agent`` protocol from ``agent_factory.core.protocols``.
    """

    def __init__(self, default_params: dict[str, Any] | None = None) -> None:
        self._default_params = default_params or {}

    def think(self, observation: Observation) -> str:
        """Produce a reasoning trace from an observation."""
        text = observation.text.lower()

        for pattern, action_name in _RULES:
            if pattern.search(text):
                return (
                    f"Observation matches '{pattern.pattern}' → "
                    f"will perform '{action_name}'."
                )

        return "No matching keyword found — defaulting to query."

    def act(self, observation: Observation) -> Action:
        """Choose an action given an observation."""
        text = observation.text.lower()
        # Keep original text for path extraction (case-sensitive)
        original_text = observation.text

        for pattern, action_name in _RULES:
            if pattern.search(text):
                params = self._extract_params(original_text, action_name)
                return Action(name=action_name, params=params)

        # Default: query everything
        return Action(name="query", params={"tag_pattern": "*"})

    def _extract_params(self, text: str, action_name: str) -> dict[str, Any]:
        """Best-effort parameter extraction from observation text.
        
        Note: text should be original case-sensitive text to preserve paths.
        We do case-insensitive matching for keywords only.
        """
        params: dict[str, Any] = dict(self._default_params)

        if action_name == "assimilate":
            params.setdefault("src", self._extract_uri(text))
            params.setdefault("dst", self._extract_tag(text))
            params.setdefault("format", "arrow")

        elif action_name == "query":
            params.setdefault("tag_pattern", self._extract_pattern(text) or "*")

        elif action_name == "retrieve":
            params.setdefault("tag", self._extract_tag(text))
            params.setdefault("blob_name", self._extract_blob(text))
            # Check for skip_cache keywords
            skip = self._should_skip_cache(text)
            log.debug(f"_should_skip_cache('{text}') = {skip}")
            if skip:
                params["skip_cache"] = True

        elif action_name == "prune":
            # Prune = cache eviction (requires blob_names)
            params.setdefault("tag", self._extract_tag(text))
            blob = self._extract_blob(text)
            if blob and blob != "*":
                params["blob_names"] = [blob]

        elif action_name == "destroy":
            # Destroy = permanent deletion (tag-level)
            params.setdefault("tags", self._extract_tag(text))

        elif action_name == "list_blobs":
            params.setdefault("tag_pattern", self._extract_pattern(text) or "*")

        return params

    # -- simple extractors (placeholder for LLM) ----------------------------

    @staticmethod
    def _extract_uri(text: str) -> str:
        """Try to pull a URI from the text.
        
        Auto-detects if a plain path is a folder or file and adds the appropriate scheme.
        """
        # First, check for explicit URI schemes
        for scheme in ("file::", "folder::", "mem::", "hdf5::"):
            match = re.search(rf"{re.escape(scheme)}(\S+)", text)
            if match:
                return f"{scheme}{match.group(1)}"
        
        # Fallback: look for file paths and auto-detect type
        # Match both absolute paths and relative paths
        match = re.search(r"((?:\./|/|\.\./)[\w./-]+)", text)
        if match:
            path_str = match.group(1)
            # Auto-detect if it's a folder or file
            try:
                path = Path(path_str)
                if path.is_dir():
                    return f"folder::{path_str}"
                elif path.is_file():
                    return f"file::{path_str}"
                else:
                    # Path doesn't exist yet, assume folder if no extension
                    if '.' in Path(path_str).name:
                        return f"file::{path_str}"
                    else:
                        return f"folder::{path_str}"
            except Exception:
                # If any error, default to file
                return f"file::{path_str}"
        
        return "file::."

    @staticmethod
    def _extract_tag(text: str) -> str:
        """Extract tag name from text.

        Patterns: "tag:X", "from X", "into X", "as X",
                  "destroy/delete/remove X"
        """
        # Try explicit tag: syntax first
        match = re.search(r"tag[:\s=]+['\"]?(\w+)", text)
        if match:
            return match.group(1).strip("'\"")

        # Try "from X" pattern
        match = re.search(r"\bfrom\s+['\"]?(\w+)", text)
        if match:
            return match.group(1).strip("'\"")

        # Try "into X" or "as X" pattern
        match = re.search(r"(?:into|as)\s+['\"]?(\w+)", text)
        if match:
            return match.group(1).strip("'\"")

        # Try "destroy/delete/remove X" — tag is the word after the action verb
        _SKIP_WORDS = {"the", "all", "a", "an", "this", "that", "it", "from", "in"}
        match = re.search(
            r"\b(?:destroy|delete|remove|query|find|search|list)\s+['\"]?(\w+)",
            text, re.IGNORECASE,
        )
        if match:
            word = match.group(1).strip("'\"")
            if word.lower() not in _SKIP_WORDS:
                return word

        return "default"

    @staticmethod
    def _extract_blob(text: str) -> str:
        """Extract blob name from text.
        
        Patterns: "blob:X", "prune X from", "get X from", "evict X from"
        """
        # Try explicit blob: syntax first
        match = re.search(r"blob[:\s=]+['\"]?([\w.-]+)", text)
        if match:
            return match.group(1).strip("'\"")
        
        # Try "prune/get/evict X from" pattern - blob name before "from"
        match = re.search(r"(?:prune|get|evict|retrieve)\s+['\"]?([\w.-]+\.[\w]+)\s+from", text)
        if match:
            return match.group(1).strip("'\"")
        
        return "*"

    @staticmethod
    def _extract_pattern(text: str) -> str | None:
        match = re.search(r"pattern[:\s=]+['\"]?(\S+)", text)
        if match:
            return match.group(1).strip("'\"")
        return None

    @staticmethod
    def _should_skip_cache(text: str) -> bool:
        """Check if text indicates bypassing cache.
        
        Keywords: "force", "bypass cache", "skip cache", "from iowarp", "direct"
        """
        text_lower = text.lower()
        skip_keywords = [
            r"\bforce\b",
            r"\bbypass\s+cache\b",
            r"\bskip\s+cache\b",
            r"\bfrom\s+iowarp\b",
            r"\bdirect(?:ly)?\b",
            r"\bno\s+cache\b",
        ]
        return any(re.search(pattern, text_lower) for pattern in skip_keywords)
