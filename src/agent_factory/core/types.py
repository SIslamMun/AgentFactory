"""Core data types for AgentFactory.

All types are frozen dataclasses — immutable value objects that flow
through the Environment / Agent loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TaskSpec:
    """Describes a task the agent should carry out."""

    task_id: str
    instruction: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Observation:
    """What the environment shows the agent after each step."""

    text: str
    data: dict[str, Any] = field(default_factory=dict)
    done: bool = False


@dataclass(frozen=True)
class Action:
    """An action the agent wants to perform on the environment."""

    name: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StepResult:
    """Outcome of a single environment step."""

    observation: Observation
    reward: float = 0.0
    done: bool = False
    info: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Trajectory:
    """A sequence of (action, step_result) pairs from a single episode."""

    task: TaskSpec
    steps: tuple[tuple[Action, StepResult], ...] = ()

    def append(self, action: Action, result: StepResult) -> Trajectory:
        """Return a new Trajectory with one more step appended."""
        return Trajectory(task=self.task, steps=self.steps + ((action, result),))

    @property
    def total_reward(self) -> float:
        return sum(sr.reward for _, sr in self.steps)

    @property
    def length(self) -> int:
        return len(self.steps)


@dataclass(frozen=True)
class AssimilationRequest:
    """Parameters for ingesting data into the context engine."""

    src: str | list[str]
    dst: str
    format: str = "arrow"


@dataclass(frozen=True)
class QueryResult:
    """Result of a context query."""

    matches: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class RetrieveResult:
    """Result of a context retrieve."""

    tag: str
    blob_name: str
    data: Any = None
    cache_hit: bool = False


# ── Pipeline orchestration types ──────────────────────────────────────────


@dataclass(frozen=True)
class PipelineStep:
    """A single step in a pipeline DAG."""

    name: str
    agent_role: str
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PipelineSpec:
    """Full specification of a pipeline (parsed from YAML)."""

    pipeline_id: str
    description: str
    steps: tuple[PipelineStep, ...] = ()


@dataclass(frozen=True)
class StepOutput:
    """Result of executing a single pipeline step."""

    step_name: str
    observation: Observation
    data: dict[str, Any] = field(default_factory=dict)
