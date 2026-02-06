"""PipelineExecutor — runs agents through a DAG in topological order.

Not an Agent itself — coordinates specialized agents sharing the same
IOWarpEnvironment.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_factory.core.errors import PipelineError
from agent_factory.core.types import Action, Observation, StepOutput
from agent_factory.orchestration.dag import PipelineDAG
from agent_factory.orchestration.messages import PipelineContext

log = logging.getLogger(__name__)


class PipelineExecutor:
    """Executes pipeline steps in topological order.

    Each step:
      1. Resolves ``${step_name.key}`` input references from prior outputs.
      2. Builds an Observation from resolved inputs.
      3. Calls ``agent.think(obs)`` then ``agent.act(obs)``.
      4. Calls ``environment.step(action)``.
      5. Stores ``StepOutput`` in context.
    """

    def __init__(
        self,
        environment: Any,
        agents: dict[str, Any],
    ) -> None:
        self._environment = environment
        self._agents = agents

    def execute(
        self,
        dag: PipelineDAG,
        task: str,
        *,
        fail_fast: bool = True,
        initial_vars: dict[str, Any] | None = None,
    ) -> PipelineContext:
        """Run the pipeline and return the accumulated context.

        *initial_vars* are injected into the context as ``pipeline.*``
        variables before execution starts (e.g. ``pipeline.src``).
        """
        context = PipelineContext(
            pipeline_id=dag.spec.pipeline_id,
            task=task,
        )

        # Inject pipeline-level variables
        if initial_vars:
            for key, value in initial_vars.items():
                context.variables[f"pipeline.{key}"] = value

        for step in dag.execution_order:
            log.info("Pipeline step: %s (agent=%s)", step.name, step.agent_role)

            agent = self._agents.get(step.agent_role)
            if agent is None:
                msg = (
                    f"No agent registered for role '{step.agent_role}' "
                    f"(step '{step.name}')"
                )
                if fail_fast:
                    raise PipelineError(msg)
                log.error(msg)
                continue

            try:
                step_output = self._execute_step(step, agent, context)
                context.store(step_output)
            except Exception as exc:
                log.error("Step '%s' failed: %s", step.name, exc)
                if fail_fast:
                    raise PipelineError(
                        f"Step '{step.name}' failed: {exc}"
                    ) from exc
                # Store error output
                error_output = StepOutput(
                    step_name=step.name,
                    observation=Observation(text=f"Error: {exc}"),
                    data={"error": str(exc)},
                )
                context.store(error_output)

        return context

    def _execute_step(
        self,
        step: Any,
        agent: Any,
        context: PipelineContext,
    ) -> StepOutput:
        """Execute a single pipeline step."""
        # 1. Resolve input references
        resolved_inputs = context.resolve_inputs(step.inputs)

        # 2. Build observation from resolved inputs
        input_text = " | ".join(
            f"{k}={v}" for k, v in resolved_inputs.items()
        )
        obs = Observation(text=input_text, data=resolved_inputs)

        # 3. Think
        thought = agent.think(obs)
        log.debug("Step '%s' thought: %s", step.name, thought)

        # 4. Act
        action = agent.act(obs)
        log.debug("Step '%s' action: %s(%s)", step.name, action.name, action.params)

        # 5. Environment step
        result = self._environment.step(action)

        # 6. Build output data from declared outputs
        data: dict[str, Any] = {}
        result_data = result.observation.data
        for key in step.outputs:
            if key in result_data:
                data[key] = result_data[key]
            elif key in action.params:
                data[key] = action.params[key]

        # Always include the action params for downstream reference
        if "tag" in action.params and "tag" not in data:
            data["tag"] = action.params["tag"]
        if "dst" in action.params and "tag" not in data:
            data["tag"] = action.params["dst"]
        if "matches" in result_data and "matches" not in data:
            data["matches"] = result_data["matches"]

        return StepOutput(
            step_name=step.name,
            observation=result.observation,
            data=data,
        )
