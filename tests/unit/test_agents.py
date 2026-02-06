"""Unit tests for all agent implementations."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agent_factory.core.types import Action, Observation
from agent_factory.agents.iowarp_agent import IOWarpAgent
from agent_factory.agents.llm_agent import LLMAgent, _parse_llm_response


# ===========================================================================
# IOWarpAgent (rule-based)
# ===========================================================================

class TestIOWarpAgent:
    """Tests for the rule-based IOWarpAgent."""

    def setup_method(self):
        self.agent = IOWarpAgent()

    def test_think_returns_string(self):
        obs = Observation(text="ingest some files")
        result = self.agent.think(obs)
        assert isinstance(result, str)
        assert "assimilate" in result

    def test_act_returns_action(self):
        obs = Observation(text="load the data")
        action = self.agent.act(obs)
        assert isinstance(action, Action)
        assert action.name == "assimilate"

    @pytest.mark.parametrize("text,expected_action", [
        ("ingest the files", "assimilate"),
        ("assimilate folder::./data into tag: docs", "assimilate"),
        ("import data from file::/data/x.csv", "assimilate"),
        ("load the CSV files", "assimilate"),
        ("find all tags matching *", "query"),
        ("search for data tagged 'docs'", "query"),
        ("query tag: docs", "query"),
        ("list everything stored", "list_blobs"),
        ("get the file readme.md", "retrieve"),
        ("retrieve blob: readme.md from tag: docs", "retrieve"),
        ("fetch the data", "retrieve"),
        ("read the stored document", "retrieve"),
        ("prune tag: old_data", "prune"),
        ("delete tag: temp", "prune"),
        ("remove old entries", "prune"),
        ("clean up the storage", "prune"),
    ])
    def test_keyword_to_action_mapping(self, text, expected_action):
        obs = Observation(text=text)
        action = self.agent.act(obs)
        assert action.name == expected_action

    def test_default_action_on_no_match(self):
        obs = Observation(text="something completely unrelated xyz")
        action = self.agent.act(obs)
        assert action.name == "query"
        assert action.params.get("tag_pattern") == "*"

    def test_word_boundary_prevents_substring_match(self):
        """'ingest' should not match inside 'ingestion'."""
        obs = Observation(text="The ingestion process completed")
        action = self.agent.act(obs)
        # "ingestion" should NOT trigger assimilate
        assert action.name != "assimilate"

    def test_extract_uri_from_text(self):
        obs = Observation(text="load folder::./data/docs into tag: docs")
        action = self.agent.act(obs)
        assert action.params["src"] == "folder::./data/docs"

    def test_extract_tag_from_text(self):
        obs = Observation(text="ingest file::/data/x.csv into tag: my_tag")
        action = self.agent.act(obs)
        assert action.params["dst"] == "my_tag"

    def test_extract_blob_from_retrieve(self):
        obs = Observation(text="retrieve blob: readme.md from tag: docs")
        action = self.agent.act(obs)
        assert action.params["blob_name"] == "readme.md"
        assert action.params["tag"] == "docs"


# ===========================================================================
# LLMAgent (Ollama)
# ===========================================================================

class TestParseResponse:
    """Tests for _parse_llm_response helper."""

    def test_plain_json(self):
        raw = '{"thought": "thinking", "action": "query", "params": {"tag_pattern": "*"}}'
        result = _parse_llm_response(raw)
        assert result["action"] == "query"
        assert result["thought"] == "thinking"

    def test_json_with_markdown_fences(self):
        raw = '```json\n{"thought": "t", "action": "query", "params": {}}\n```'
        result = _parse_llm_response(raw)
        assert result["action"] == "query"

    def test_json_with_whitespace(self):
        raw = '  \n  {"thought": "t", "action": "prune", "params": {"tags": "x"}}  \n  '
        result = _parse_llm_response(raw)
        assert result["action"] == "prune"

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_llm_response("this is not json at all")


class TestLLMAgent:
    """Tests for the Ollama-backed LLMAgent."""

    def _make_ollama_response(self, content: str):
        """Create a mock Ollama chat response."""
        mock_msg = MagicMock()
        mock_msg.content = content
        mock_result = MagicMock()
        mock_result.message = mock_msg
        return mock_result

    @patch("agent_factory.agents.llm_agent.ollama")
    def test_think_returns_thought(self, mock_ollama):
        response_json = json.dumps({
            "thought": "I should query all tags",
            "action": "query",
            "params": {"tag_pattern": "*"},
        })
        mock_ollama.chat.return_value = self._make_ollama_response(response_json)

        agent = LLMAgent(model="test-model")
        obs = Observation(text="show me what's stored")
        thought = agent.think(obs)

        assert thought == "I should query all tags"
        mock_ollama.chat.assert_called_once()

    @patch("agent_factory.agents.llm_agent.ollama")
    def test_act_returns_action(self, mock_ollama):
        response_json = json.dumps({
            "thought": "User wants to ingest data",
            "action": "assimilate",
            "params": {"src": "folder::./data", "dst": "docs", "format": "markdown"},
        })
        mock_ollama.chat.return_value = self._make_ollama_response(response_json)

        agent = LLMAgent(model="test-model")
        obs = Observation(text="ingest folder::./data into tag: docs")
        action = agent.act(obs)

        assert isinstance(action, Action)
        assert action.name == "assimilate"
        assert action.params["src"] == "folder::./data"
        assert action.params["dst"] == "docs"

    @patch("agent_factory.agents.llm_agent.ollama")
    def test_think_then_act_reuses_response(self, mock_ollama):
        """Calling think() then act() should only call the LLM once."""
        response_json = json.dumps({
            "thought": "Will retrieve data",
            "action": "retrieve",
            "params": {"tag": "docs", "blob_name": "readme.md"},
        })
        mock_ollama.chat.return_value = self._make_ollama_response(response_json)

        agent = LLMAgent(model="test-model")
        obs = Observation(text="get readme.md from docs")

        thought = agent.think(obs)
        action = agent.act(obs)

        assert thought == "Will retrieve data"
        assert action.name == "retrieve"
        # Only one LLM call should have been made
        assert mock_ollama.chat.call_count == 1

    @patch("agent_factory.agents.llm_agent.ollama")
    def test_invalid_action_defaults_to_query(self, mock_ollama):
        response_json = json.dumps({
            "thought": "confused",
            "action": "invalid_action",
            "params": {},
        })
        mock_ollama.chat.return_value = self._make_ollama_response(response_json)

        agent = LLMAgent(model="test-model")
        obs = Observation(text="do something")
        action = agent.act(obs)

        assert action.name == "query"
        assert action.params == {"tag_pattern": "*"}

    @patch("agent_factory.agents.llm_agent.ollama")
    def test_json_parse_error_handled(self, mock_ollama):
        mock_ollama.chat.return_value = self._make_ollama_response("not valid json!")

        agent = LLMAgent(model="test-model")
        obs = Observation(text="do something")
        action = agent.act(obs)

        # Should fall back to default query
        assert action.name == "query"

    @patch("agent_factory.agents.llm_agent.ollama")
    def test_ollama_exception_handled(self, mock_ollama):
        mock_ollama.chat.side_effect = ConnectionError("Ollama not running")

        agent = LLMAgent(model="test-model")
        obs = Observation(text="do something")
        action = agent.act(obs)

        # Should fall back to default query
        assert action.name == "query"

    @patch("agent_factory.agents.llm_agent.ollama")
    def test_all_valid_actions_accepted(self, mock_ollama):
        agent = LLMAgent(model="test-model")

        for action_name in ("assimilate", "query", "retrieve", "prune", "list_blobs"):
            response_json = json.dumps({
                "thought": f"doing {action_name}",
                "action": action_name,
                "params": {},
            })
            mock_ollama.chat.return_value = self._make_ollama_response(response_json)

            obs = Observation(text=f"test {action_name}")
            action = agent.act(obs)
            assert action.name == action_name

    def test_custom_system_prompt(self):
        agent = LLMAgent(model="test", system_prompt="Custom prompt")
        assert agent._system_prompt == "Custom prompt"

    def test_default_system_prompt(self):
        agent = LLMAgent(model="test")
        assert "ACTIONS YOU CAN TAKE" in agent._system_prompt


# ===========================================================================
# ClaudeAgent (CLI) — tested with mocks for subprocess
# ===========================================================================

class TestClaudeAgent:
    """Tests for ClaudeAgent (mocked subprocess calls)."""

    @patch("shutil.which", return_value=None)
    def test_runtime_error_when_cli_missing(self, mock_which):
        """ClaudeAgent raises RuntimeError if claude CLI is not found."""
        from agent_factory.agents.claude_agent import ClaudeAgent as CA
        with pytest.raises(RuntimeError, match="Claude Code CLI not found"):
            CA()

    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run")
    def test_think_returns_thought(self, mock_run, mock_which):
        from agent_factory.agents.claude_agent import ClaudeAgent as CA
        response_json = json.dumps({
            "thought": "I should query all tags",
            "action": "query",
            "params": {"tag_pattern": "*"},
        })
        mock_run.return_value = MagicMock(returncode=0, stdout=response_json, stderr="")

        agent = CA()
        obs = Observation(text="show me what's stored")
        thought = agent.think(obs)

        assert thought == "I should query all tags"
        mock_run.assert_called_once()

    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run")
    def test_act_returns_action(self, mock_run, mock_which):
        from agent_factory.agents.claude_agent import ClaudeAgent as CA
        response_json = json.dumps({
            "thought": "User wants to ingest data",
            "action": "assimilate",
            "params": {"src": "folder::./data", "dst": "docs", "format": "arrow"},
        })
        mock_run.return_value = MagicMock(returncode=0, stdout=response_json, stderr="")

        agent = CA()
        obs = Observation(text="ingest folder::./data into tag: docs")
        action = agent.act(obs)

        assert isinstance(action, Action)
        assert action.name == "assimilate"
        assert action.params["src"] == "folder::./data"

    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run")
    def test_think_then_act_reuses_response(self, mock_run, mock_which):
        """Calling think() then act() should only call claude CLI once."""
        from agent_factory.agents.claude_agent import ClaudeAgent as CA
        response_json = json.dumps({
            "thought": "Will retrieve data",
            "action": "retrieve",
            "params": {"tag": "docs", "blob_name": "readme.md"},
        })
        mock_run.return_value = MagicMock(returncode=0, stdout=response_json, stderr="")

        agent = CA()
        obs = Observation(text="get readme.md from docs")

        thought = agent.think(obs)
        action = agent.act(obs)

        assert thought == "Will retrieve data"
        assert action.name == "retrieve"
        assert mock_run.call_count == 1

    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run")
    def test_invalid_action_defaults_to_query(self, mock_run, mock_which):
        from agent_factory.agents.claude_agent import ClaudeAgent as CA
        response_json = json.dumps({
            "thought": "confused",
            "action": "invalid_action",
            "params": {},
        })
        mock_run.return_value = MagicMock(returncode=0, stdout=response_json, stderr="")

        agent = CA()
        obs = Observation(text="do something")
        action = agent.act(obs)

        assert action.name == "query"
        assert action.params == {"tag_pattern": "*"}

    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run")
    def test_cli_error_handled(self, mock_run, mock_which):
        from agent_factory.agents.claude_agent import ClaudeAgent as CA
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error occurred")

        agent = CA()
        obs = Observation(text="do something")
        action = agent.act(obs)

        assert action.name == "query"


# ===========================================================================
# Builder agent type selection
# ===========================================================================

class TestBuilderAgentSelection:
    """Tests for AgentBuilder._build_agent type dispatch."""

    def test_rule_based_type(self):
        from agent_factory.factory.builder import AgentBuilder
        agent = AgentBuilder._build_agent({"type": "rule_based"})
        assert isinstance(agent, IOWarpAgent)

    def test_default_type_is_rule_based(self):
        from agent_factory.factory.builder import AgentBuilder
        agent = AgentBuilder._build_agent({})
        assert isinstance(agent, IOWarpAgent)

    @patch("agent_factory.agents.llm_agent.ollama")
    def test_llm_type(self, mock_ollama):
        from agent_factory.factory.builder import AgentBuilder
        agent = AgentBuilder._build_agent({
            "type": "llm",
            "model": "llama3.2:latest",
            "temperature": 0.2,
        })
        assert isinstance(agent, LLMAgent)
        assert agent._model == "llama3.2:latest"
        assert agent._temperature == 0.2

    def test_unknown_type_raises(self):
        from agent_factory.factory.builder import AgentBuilder
        from agent_factory.core.errors import BlueprintError
        with pytest.raises(BlueprintError, match="Unknown agent type"):
            AgentBuilder._build_agent({"type": "nonexistent"})
