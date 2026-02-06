"""PipelineDAG — validates and topologically sorts pipeline steps.

Uses Kahn's algorithm for topological ordering and detects cycles,
missing dependency references, and unknown agent roles.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from agent_factory.core.errors import PipelineError
from agent_factory.core.types import PipelineSpec, PipelineStep


class PipelineDAG:
    """Directed acyclic graph of pipeline steps.

    Validates the pipeline definition and provides a topologically sorted
    execution order.
    """

    def __init__(self, spec: PipelineSpec, known_roles: frozenset[str]) -> None:
        self._spec = spec
        self._steps_by_name: dict[str, PipelineStep] = {s.name: s for s in spec.steps}
        self._validate(known_roles)
        self._order = self._topological_sort()

    @classmethod
    def from_dict(
        cls,
        yaml_dict: dict[str, Any],
        known_roles: frozenset[str] | None = None,
    ) -> PipelineDAG:
        """Parse a pipeline config dict into a validated DAG.

        *yaml_dict* should have top-level keys: ``pipeline_id``,
        ``description``, ``steps``.  Each step dict has ``name``,
        ``agent`` (mapped to agent_role), optional ``inputs``,
        ``outputs``, ``depends_on``.
        """
        if known_roles is None:
            known_roles = frozenset()

        steps = []
        for raw in yaml_dict.get("steps", []):
            step = PipelineStep(
                name=raw["name"],
                agent_role=raw.get("agent", raw.get("agent_role", "")),
                inputs=raw.get("inputs", {}),
                outputs=raw.get("outputs", []),
                depends_on=raw.get("depends_on", []),
            )
            steps.append(step)

        spec = PipelineSpec(
            pipeline_id=yaml_dict.get("pipeline_id", "unnamed"),
            description=yaml_dict.get("description", ""),
            steps=tuple(steps),
        )
        return cls(spec, known_roles)

    def _validate(self, known_roles: frozenset[str]) -> None:
        """Validate the pipeline definition."""
        names = set(self._steps_by_name.keys())

        # Check for duplicate names
        if len(names) != len(self._spec.steps):
            raise PipelineError("Duplicate step names in pipeline definition")

        # Check depends_on references exist
        for step in self._spec.steps:
            for dep in step.depends_on:
                if dep not in names:
                    raise PipelineError(
                        f"Step '{step.name}' depends on unknown step '{dep}'"
                    )

        # Check agent roles are known (if known_roles provided)
        if known_roles:
            for step in self._spec.steps:
                if step.agent_role not in known_roles:
                    raise PipelineError(
                        f"Step '{step.name}' references unknown agent role "
                        f"'{step.agent_role}'. Known roles: {sorted(known_roles)}"
                    )

    def _topological_sort(self) -> list[PipelineStep]:
        """Kahn's algorithm for topological ordering.

        Raises PipelineError if a cycle is detected.
        """
        # Build adjacency and in-degree
        in_degree: dict[str, int] = {s.name: 0 for s in self._spec.steps}
        successors: dict[str, list[str]] = {s.name: [] for s in self._spec.steps}

        for step in self._spec.steps:
            for dep in step.depends_on:
                successors[dep].append(step.name)
                in_degree[step.name] += 1

        # Start with nodes that have no dependencies
        queue: deque[str] = deque()
        for name, degree in in_degree.items():
            if degree == 0:
                queue.append(name)

        order: list[PipelineStep] = []
        while queue:
            name = queue.popleft()
            order.append(self._steps_by_name[name])
            for succ in successors[name]:
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

        if len(order) != len(self._spec.steps):
            raise PipelineError(
                "Cycle detected in pipeline — steps cannot be topologically sorted"
            )

        return order

    @property
    def execution_order(self) -> list[PipelineStep]:
        """Return steps in topological order."""
        return list(self._order)

    @property
    def spec(self) -> PipelineSpec:
        return self._spec
