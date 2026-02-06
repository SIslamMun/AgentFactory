"""PEP 544 structural protocols for AgentFactory components."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_factory.core.types import Action, Observation, StepResult, TaskSpec


@runtime_checkable
class Environment(Protocol):
    """An environment the agent interacts with."""

    def reset(self, task: TaskSpec) -> Observation:
        """Reset the environment for a new task and return initial observation."""
        ...

    def step(self, action: Action) -> StepResult:
        """Execute an action and return the resulting step."""
        ...

    def observe(self) -> Observation:
        """Return the current observation without taking an action."""
        ...

    def close(self) -> None:
        """Release resources held by the environment."""
        ...


@runtime_checkable
class Agent(Protocol):
    """An agent that thinks and acts given observations."""

    def think(self, observation: Observation) -> str:
        """Produce a reasoning trace from an observation."""
        ...

    def act(self, observation: Observation) -> Action:
        """Choose an action given an observation."""
        ...


@runtime_checkable
class RewardFunction(Protocol):
    """Computes reward for a given step."""

    def __call__(self, action: Action, result: StepResult) -> float:
        ...
