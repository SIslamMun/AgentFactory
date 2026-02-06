"""Unit tests for PipelineExecutor (mocked environment)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent_factory.core.errors import PipelineError
from agent_factory.core.types import Action, Observation, StepResult
from agent_factory.orchestration.dag import PipelineDAG
from agent_factory.orchestration.executor import PipelineExecutor
from agent_factory.orchestration.messages import PipelineContext


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_agent(action_name: str = "query", params: dict | None = None):
    """Create a mock agent that returns a fixed action."""
    agent = MagicMock()
    agent.think.return_value = f"thinking about {action_name}"
    agent.act.return_value = Action(
        name=action_name, params=params or {}
    )
    return agent


def _make_env(observation_text: str = "ok", data: dict | None = None):
    """Create a mock environment that returns a fixed StepResult."""
    env = MagicMock()
    env.step.return_value = StepResult(
        observation=Observation(text=observation_text, data=data or {}),
        reward=0.1,
    )
    return env


def _simple_dag():
    """A two-step linear pipeline: step_a -> step_b."""
    return PipelineDAG.from_dict({
        "pipeline_id": "test",
        "description": "test pipeline",
        "steps": [
            {
                "name": "step_a",
                "agent": "agent_a",
                "inputs": {"src": "${pipeline.src}"},
                "outputs": ["tag"],
            },
            {
                "name": "step_b",
                "agent": "agent_b",
                "inputs": {"tag_pattern": "${step_a.tag}"},
                "outputs": ["matches"],
                "depends_on": ["step_a"],
            },
        ],
    })


# ── Tests ────────────────────────────────────────────────────────────────

class TestPipelineExecutor:
    """Tests for PipelineExecutor.execute."""

    def test_executes_steps_in_order(self):
        dag = _simple_dag()
        env = _make_env("success", {"tag": "docs"})
        agent_a = _make_agent("assimilate", {"dst": "docs"})
        agent_b = _make_agent("query", {"tag_pattern": "docs"})
        agents = {"agent_a": agent_a, "agent_b": agent_b}

        executor = PipelineExecutor(env, agents)
        ctx = executor.execute(dag, "test task", initial_vars={"src": "/data"})

        # Both agents should have been called
        assert agent_a.think.call_count == 1
        assert agent_a.act.call_count == 1
        assert agent_b.think.call_count == 1
        assert agent_b.act.call_count == 1
        # Both steps in context
        assert "step_a" in ctx.outputs
        assert "step_b" in ctx.outputs

    def test_initial_vars_injected(self):
        dag = _simple_dag()
        env = _make_env("ok", {"tag": "docs"})
        agent_a = _make_agent("assimilate", {"dst": "docs"})
        agent_b = _make_agent("query")
        agents = {"agent_a": agent_a, "agent_b": agent_b}

        executor = PipelineExecutor(env, agents)
        ctx = executor.execute(dag, "test", initial_vars={"src": "/data/files"})

        # The first agent should receive resolved input with pipeline.src
        call_obs = agent_a.think.call_args[0][0]
        assert "/data/files" in call_obs.text

    def test_step_output_resolution(self):
        """Step B should see resolved values from Step A's output."""
        dag = _simple_dag()
        env = _make_env("ok", {"tag": "my_tag"})
        agent_a = _make_agent("assimilate", {"dst": "my_tag"})
        agent_b = _make_agent("query")
        agents = {"agent_a": agent_a, "agent_b": agent_b}

        executor = PipelineExecutor(env, agents)
        ctx = executor.execute(dag, "test", initial_vars={"src": "/data"})

        # Step B should have received resolved tag from Step A
        call_obs_b = agent_b.think.call_args[0][0]
        assert "my_tag" in call_obs_b.text

    def test_missing_agent_fail_fast(self):
        dag = _simple_dag()
        env = _make_env()
        agents = {"agent_a": _make_agent()}  # Missing agent_b

        executor = PipelineExecutor(env, agents)
        with pytest.raises(PipelineError, match="No agent registered"):
            executor.execute(dag, "test")

    def test_missing_agent_no_fail_fast(self):
        dag = _simple_dag()
        env = _make_env("ok", {})
        agents = {"agent_a": _make_agent("assimilate", {"dst": "x"})}

        executor = PipelineExecutor(env, agents)
        ctx = executor.execute(dag, "test", fail_fast=False)

        # step_a should succeed, step_b should be skipped
        assert "step_a" in ctx.outputs
        assert "step_b" not in ctx.outputs

    def test_env_step_failure_fail_fast(self):
        dag = _simple_dag()
        env = MagicMock()
        env.step.side_effect = RuntimeError("bridge down")
        agents = {"agent_a": _make_agent(), "agent_b": _make_agent()}

        executor = PipelineExecutor(env, agents)
        with pytest.raises(PipelineError, match="Step 'step_a' failed"):
            executor.execute(dag, "test")

    def test_env_step_failure_no_fail_fast(self):
        dag = _simple_dag()
        env = MagicMock()
        env.step.side_effect = RuntimeError("bridge down")
        agents = {"agent_a": _make_agent(), "agent_b": _make_agent()}

        executor = PipelineExecutor(env, agents)
        ctx = executor.execute(dag, "test", fail_fast=False)

        # Both steps should have error outputs
        assert "error" in ctx.outputs["step_a"].data
        assert "error" in ctx.outputs["step_b"].data

    def test_single_step_pipeline(self):
        dag = PipelineDAG.from_dict({
            "pipeline_id": "single",
            "steps": [{"name": "only", "agent": "a", "outputs": ["result"]}],
        })
        env = _make_env("done", {"result": 42})
        agents = {"a": _make_agent()}

        executor = PipelineExecutor(env, agents)
        ctx = executor.execute(dag, "test")

        assert "only" in ctx.outputs
        assert ctx.outputs["only"].data.get("result") == 42

    def test_context_pipeline_id_set(self):
        dag = PipelineDAG.from_dict({
            "pipeline_id": "my_pipeline",
            "steps": [{"name": "s", "agent": "a"}],
        })
        env = _make_env()
        agents = {"a": _make_agent()}

        executor = PipelineExecutor(env, agents)
        ctx = executor.execute(dag, "test")

        assert ctx.pipeline_id == "my_pipeline"


class TestPipelineContext:
    """Tests for PipelineContext variable resolution."""

    def test_resolve_simple(self):
        ctx = PipelineContext(pipeline_id="test")
        ctx.variables["step1.tag"] = "docs"
        assert ctx.resolve("${step1.tag}") == "docs"

    def test_resolve_unresolved_left_as_is(self):
        ctx = PipelineContext(pipeline_id="test")
        assert ctx.resolve("${unknown.key}") == "${unknown.key}"

    def test_resolve_multiple(self):
        ctx = PipelineContext(pipeline_id="test")
        ctx.variables["a.x"] = "hello"
        ctx.variables["b.y"] = "world"
        result = ctx.resolve("${a.x} ${b.y}")
        assert result == "hello world"

    def test_resolve_inputs(self):
        ctx = PipelineContext(pipeline_id="test")
        ctx.variables["pipeline.src"] = "/data"
        inputs = {"src": "${pipeline.src}", "count": 5}
        resolved = ctx.resolve_inputs(inputs)
        assert resolved == {"src": "/data", "count": 5}

    def test_store_makes_data_available(self):
        from agent_factory.core.types import StepOutput
        ctx = PipelineContext(pipeline_id="test")
        output = StepOutput(
            step_name="ingest",
            observation=Observation(text="ok"),
            data={"tag": "docs", "files": 10},
        )
        ctx.store(output)
        assert ctx.resolve("${ingest.tag}") == "docs"
        assert ctx.resolve("${ingest.files}") == "10"
