"""Tests for frozen dataclass types."""

from __future__ import annotations

import pytest

from agent_factory.core.types import (
    Action,
    AssimilationRequest,
    Observation,
    QueryResult,
    RetrieveResult,
    StepResult,
    TaskSpec,
    Trajectory,
)


class TestTaskSpec:
    def test_creation(self):
        t = TaskSpec(task_id="t1", instruction="do something")
        assert t.task_id == "t1"
        assert t.instruction == "do something"
        assert t.metadata == {}

    def test_frozen(self):
        t = TaskSpec(task_id="t1", instruction="x")
        with pytest.raises(AttributeError):
            t.task_id = "t2"  # type: ignore[misc]


class TestObservation:
    def test_defaults(self):
        o = Observation(text="hello")
        assert o.text == "hello"
        assert o.data == {}
        assert o.done is False

    def test_frozen(self):
        o = Observation(text="x")
        with pytest.raises(AttributeError):
            o.text = "y"  # type: ignore[misc]


class TestAction:
    def test_creation(self):
        a = Action(name="query", params={"tag_pattern": "*"})
        assert a.name == "query"
        assert a.params == {"tag_pattern": "*"}


class TestStepResult:
    def test_defaults(self):
        obs = Observation(text="ok")
        sr = StepResult(observation=obs)
        assert sr.reward == 0.0
        assert sr.done is False


class TestTrajectory:
    def test_empty(self):
        task = TaskSpec(task_id="t1", instruction="x")
        traj = Trajectory(task=task)
        assert traj.length == 0
        assert traj.total_reward == 0.0

    def test_append(self):
        task = TaskSpec(task_id="t1", instruction="x")
        traj = Trajectory(task=task)
        action = Action(name="query")
        result = StepResult(observation=Observation(text="ok"), reward=0.5)
        traj2 = traj.append(action, result)
        assert traj.length == 0  # original unchanged (frozen)
        assert traj2.length == 1
        assert traj2.total_reward == 0.5

    def test_multiple_steps(self):
        task = TaskSpec(task_id="t1", instruction="x")
        traj = Trajectory(task=task)
        for i in range(3):
            action = Action(name="query")
            result = StepResult(observation=Observation(text=f"step {i}"), reward=0.1)
            traj = traj.append(action, result)
        assert traj.length == 3
        assert abs(traj.total_reward - 0.3) < 1e-9


class TestAssimilationRequest:
    def test_single_src(self):
        r = AssimilationRequest(src="file::/data/x.csv", dst="my_tag")
        assert r.src == "file::/data/x.csv"
        assert r.format == "arrow"

    def test_list_src(self):
        r = AssimilationRequest(
            src=["file::/a.csv", "file::/b.csv"], dst="tag", format="csv",
        )
        assert isinstance(r.src, list)
        assert len(r.src) == 2


class TestQueryResult:
    def test_defaults(self):
        qr = QueryResult()
        assert qr.matches == []


class TestRetrieveResult:
    def test_cache_hit(self):
        rr = RetrieveResult(tag="t", blob_name="b", data=b"hello", cache_hit=True)
        assert rr.cache_hit is True
        assert rr.data == b"hello"
