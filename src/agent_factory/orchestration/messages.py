"""PipelineContext — accumulates StepOutput results during pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_factory.core.types import StepOutput


@dataclass
class PipelineContext:
    """Mutable context that accumulates step outputs during pipeline execution.

    Provides variable resolution for ``${step_name.key}`` references in
    step inputs.
    """

    pipeline_id: str
    task: str = ""
    outputs: dict[str, StepOutput] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)

    def store(self, output: StepOutput) -> None:
        """Record a step output and make its data available for resolution."""
        self.outputs[output.step_name] = output
        # Flatten step data into variables: step_name.key = value
        for key, value in output.data.items():
            self.variables[f"{output.step_name}.{key}"] = value

    def resolve(self, template: str) -> str:
        """Resolve ``${step_name.key}`` references in a template string.

        Also supports ``${pipeline.key}`` for pipeline-level variables.
        Unresolved references are left as-is.
        """
        import re

        def _replace(match: re.Match[str]) -> str:
            ref = match.group(1)
            if ref in self.variables:
                return str(self.variables[ref])
            return match.group(0)  # leave unresolved

        return re.sub(r"\$\{([^}]+)\}", _replace, template)

    def resolve_inputs(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Resolve all string values in an inputs dict."""
        resolved: dict[str, Any] = {}
        for key, value in inputs.items():
            if isinstance(value, str):
                resolved[key] = self.resolve(value)
            else:
                resolved[key] = value
        return resolved
