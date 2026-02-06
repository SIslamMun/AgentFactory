"""Unit tests for IngestorAgent."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent_factory.core.types import Action, Observation
from agent_factory.agents.ingestor_agent import IngestorAgent


class TestIngestorAgent:
    """Tests for IngestorAgent action constraining."""

    def _make_backend(self, action: Action | None = None, thought: str = "thinking"):
        """Create a mock backend agent."""
        backend = MagicMock()
        backend.think.return_value = thought
        if action is not None:
            backend.act.return_value = action
        return backend

    def test_think_prepends_ingestor_context(self):
        backend = self._make_backend()
        agent = IngestorAgent(backend)
        obs = Observation(text="load some files")
        agent.think(obs)

        # Backend should receive augmented observation
        call_args = backend.think.call_args[0]
        assert "ingestion specialist" in call_args[0].text
        assert "load some files" in call_args[0].text

    def test_think_returns_backend_result(self):
        backend = self._make_backend(thought="I will assimilate files")
        agent = IngestorAgent(backend)
        obs = Observation(text="load files")
        result = agent.think(obs)
        assert result == "I will assimilate files"

    def test_act_passthrough_assimilate(self):
        """Backend returning assimilate should pass through."""
        action = Action(name="assimilate", params={"src": "file::x.csv", "dst": "docs"})
        backend = self._make_backend(action=action)
        agent = IngestorAgent(backend, default_format="arrow")
        obs = Observation(text="ingest x.csv")
        result = agent.act(obs)

        assert result.name == "assimilate"
        assert result.params["src"] == "file::x.csv"
        assert result.params["dst"] == "docs"
        assert result.params["format"] == "arrow"

    def test_act_overrides_non_assimilate_action(self):
        """Backend returning query should be overridden to assimilate."""
        action = Action(name="query", params={"tag_pattern": "*"})
        backend = self._make_backend(action=action)
        agent = IngestorAgent(backend, default_tag="my_tag")
        obs = Observation(text="do something with file::/data/test.csv")
        result = agent.act(obs)

        assert result.name == "assimilate"
        assert result.params["dst"] == "my_tag"
        assert result.params["format"] == "arrow"

    def test_act_overrides_retrieve_action(self):
        """Backend returning retrieve should be overridden to assimilate."""
        action = Action(name="retrieve", params={"tag": "x", "blob_name": "y"})
        backend = self._make_backend(action=action)
        agent = IngestorAgent(backend, default_tag="docs")
        obs = Observation(text="load folder::./data into tag: uploads")
        result = agent.act(obs)

        assert result.name == "assimilate"
        assert result.params["src"] == "folder::./data"
        assert result.params["dst"] == "uploads"

    def test_default_tag_used_when_no_tag_in_text(self):
        """When no tag found in text, default_tag should be used."""
        action = Action(name="query", params={})
        backend = self._make_backend(action=action)
        agent = IngestorAgent(backend, default_tag="my_default")
        obs = Observation(text="just do something")
        result = agent.act(obs)

        assert result.name == "assimilate"
        assert result.params["dst"] == "my_default"

    def test_default_format_applied(self):
        action = Action(name="assimilate", params={"src": "file::x"})
        backend = self._make_backend(action=action)
        agent = IngestorAgent(backend, default_format="parquet")
        obs = Observation(text="ingest")
        result = agent.act(obs)

        assert result.params["format"] == "parquet"

    def test_assimilate_preserves_existing_format(self):
        """If backend already sets format, default_format fills in only if missing."""
        action = Action(name="assimilate", params={"src": "file::x", "format": "csv"})
        backend = self._make_backend(action=action)
        agent = IngestorAgent(backend, default_format="arrow")
        obs = Observation(text="ingest")
        result = agent.act(obs)

        # format was already set by backend, should not be overridden
        assert result.params["format"] == "csv"

    def test_with_real_iowarp_agent_backend(self):
        """Integration: IngestorAgent wrapping a real IOWarpAgent."""
        from agent_factory.agents.iowarp_agent import IOWarpAgent

        backend = IOWarpAgent()
        agent = IngestorAgent(backend, default_tag="docs")
        obs = Observation(text="ingest folder::./data into tag: reports")
        result = agent.act(obs)

        assert result.name == "assimilate"
        assert result.params["src"] == "folder::./data"
        assert result.params["dst"] == "reports"

    def test_with_iowarp_backend_no_match(self):
        """IOWarpAgent defaults to query, IngestorAgent overrides to assimilate."""
        from agent_factory.agents.iowarp_agent import IOWarpAgent

        backend = IOWarpAgent()
        agent = IngestorAgent(backend, default_tag="fallback")
        obs = Observation(text="xyz nonsense")
        result = agent.act(obs)

        assert result.name == "assimilate"
        assert result.params["dst"] == "fallback"
