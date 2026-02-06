"""Unit tests for RetrieverAgent."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent_factory.core.types import Action, Observation, StepResult
from agent_factory.agents.retriever_agent import RetrieverAgent


class TestRetrieverAgent:
    """Tests for RetrieverAgent action constraining."""

    def _make_backend(self, action: Action | None = None, thought: str = "thinking"):
        backend = MagicMock()
        backend.think.return_value = thought
        if action is not None:
            backend.act.return_value = action
        return backend

    def test_think_prepends_retriever_context(self):
        backend = self._make_backend()
        agent = RetrieverAgent(backend)
        obs = Observation(text="search for docs")
        agent.think(obs)

        call_args = backend.think.call_args[0]
        assert "data-access specialist" in call_args[0].text
        assert "search for docs" in call_args[0].text

    def test_think_returns_backend_result(self):
        backend = self._make_backend(thought="I will query tags")
        agent = RetrieverAgent(backend)
        obs = Observation(text="find tags")
        result = agent.think(obs)
        assert result == "I will query tags"

    @pytest.mark.parametrize("action_name", ["query", "retrieve", "list_blobs"])
    def test_allowed_actions_pass_through(self, action_name):
        """query, retrieve, and list_blobs should pass through unchanged."""
        action = Action(name=action_name, params={"some": "param"})
        backend = self._make_backend(action=action)
        agent = RetrieverAgent(backend)
        obs = Observation(text="do something")
        result = agent.act(obs)

        assert result.name == action_name
        assert result.params == {"some": "param"}

    def test_disallowed_action_defaults_to_query(self):
        """assimilate should be overridden to query."""
        action = Action(name="assimilate", params={"src": "file::x", "dst": "y"})
        backend = self._make_backend(action=action)
        agent = RetrieverAgent(backend, default_tag_pattern="docs*")
        obs = Observation(text="ingest something")
        result = agent.act(obs)

        assert result.name == "query"
        assert result.params["tag_pattern"] == "docs*"

    def test_prune_action_overridden(self):
        """prune should be overridden to query."""
        action = Action(name="prune", params={"tags": "old"})
        backend = self._make_backend(action=action)
        agent = RetrieverAgent(backend)
        obs = Observation(text="delete old data")
        result = agent.act(obs)

        assert result.name == "query"

    def test_default_tag_pattern(self):
        action = Action(name="assimilate", params={})
        backend = self._make_backend(action=action)
        agent = RetrieverAgent(backend, default_tag_pattern="my_pattern")
        obs = Observation(text="xyz")
        result = agent.act(obs)

        assert result.params["tag_pattern"] == "my_pattern"

    def test_with_real_iowarp_agent_backend(self):
        """Integration: RetrieverAgent wrapping a real IOWarpAgent."""
        from agent_factory.agents.iowarp_agent import IOWarpAgent

        backend = IOWarpAgent()
        agent = RetrieverAgent(backend)
        obs = Observation(text="query tag: docs")
        result = agent.act(obs)

        assert result.name == "query"

    def test_iowarp_backend_retrieve_allowed(self):
        from agent_factory.agents.iowarp_agent import IOWarpAgent

        backend = IOWarpAgent()
        agent = RetrieverAgent(backend)
        obs = Observation(text="retrieve blob: readme.md from tag: docs")
        result = agent.act(obs)

        assert result.name == "retrieve"

    def test_iowarp_backend_list_allowed(self):
        from agent_factory.agents.iowarp_agent import IOWarpAgent

        backend = IOWarpAgent()
        agent = RetrieverAgent(backend)
        obs = Observation(text="list everything")
        result = agent.act(obs)

        assert result.name == "list_blobs"


class TestRetrieverActCompound:
    """Tests for RetrieverAgent.act_compound."""

    def test_act_compound_queries_then_retrieves(self):
        backend = MagicMock()
        agent = RetrieverAgent(backend, default_tag_pattern="*")

        mock_env = MagicMock()
        query_obs = Observation(
            text="Found 2 matches",
            data={
                "matches": [
                    {"tag": "docs", "blobs": ["a.md", "b.md"]},
                ]
            },
        )
        query_result = StepResult(observation=query_obs)

        retrieve_obs = Observation(text="Retrieved blob")
        retrieve_result = StepResult(observation=retrieve_obs)

        mock_env.step.side_effect = [query_result, retrieve_result, retrieve_result]

        obs = Observation(text="get all docs")
        results = agent.act_compound(obs, mock_env)

        assert len(results) == 2
        # First call is query, next two are retrieves
        assert mock_env.step.call_count == 3

        calls = mock_env.step.call_args_list
        assert calls[0][0][0].name == "query"
        assert calls[1][0][0].name == "retrieve"
        assert calls[1][0][0].params["blob_name"] == "a.md"
        assert calls[2][0][0].name == "retrieve"
        assert calls[2][0][0].params["blob_name"] == "b.md"

    def test_act_compound_no_matches(self):
        backend = MagicMock()
        agent = RetrieverAgent(backend)

        mock_env = MagicMock()
        query_obs = Observation(text="No matches", data={"matches": []})
        mock_env.step.return_value = StepResult(observation=query_obs)

        obs = Observation(text="find something")
        results = agent.act_compound(obs, mock_env)

        assert results == []
        assert mock_env.step.call_count == 1
