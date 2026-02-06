"""Unit tests for PipelineDAG validation and topological sort."""

from __future__ import annotations

import pytest

from agent_factory.core.errors import PipelineError
from agent_factory.core.types import PipelineSpec, PipelineStep
from agent_factory.orchestration.dag import PipelineDAG


class TestPipelineDAGFromDict:
    """Tests for PipelineDAG.from_dict parsing."""

    def test_basic_parsing(self):
        cfg = {
            "pipeline_id": "test",
            "description": "A test pipeline",
            "steps": [
                {"name": "step1", "agent": "ingestor"},
                {"name": "step2", "agent": "retriever", "depends_on": ["step1"]},
            ],
        }
        dag = PipelineDAG.from_dict(cfg)
        assert dag.spec.pipeline_id == "test"
        assert len(dag.execution_order) == 2

    def test_step_fields_parsed(self):
        cfg = {
            "pipeline_id": "test",
            "steps": [
                {
                    "name": "ingest",
                    "agent": "ingestor",
                    "inputs": {"src": "${pipeline.src}"},
                    "outputs": ["tag"],
                    "depends_on": [],
                },
            ],
        }
        dag = PipelineDAG.from_dict(cfg)
        step = dag.execution_order[0]
        assert step.name == "ingest"
        assert step.agent_role == "ingestor"
        assert step.inputs == {"src": "${pipeline.src}"}
        assert step.outputs == ["tag"]

    def test_empty_pipeline(self):
        cfg = {"pipeline_id": "empty", "steps": []}
        dag = PipelineDAG.from_dict(cfg)
        assert dag.execution_order == []


class TestPipelineDAGValidation:
    """Tests for DAG validation."""

    def test_missing_dependency_raises(self):
        cfg = {
            "pipeline_id": "test",
            "steps": [
                {"name": "step1", "agent": "a", "depends_on": ["nonexistent"]},
            ],
        }
        with pytest.raises(PipelineError, match="unknown step 'nonexistent'"):
            PipelineDAG.from_dict(cfg)

    def test_unknown_agent_role_raises(self):
        cfg = {
            "pipeline_id": "test",
            "steps": [
                {"name": "step1", "agent": "unknown_role"},
            ],
        }
        with pytest.raises(PipelineError, match="unknown agent role"):
            PipelineDAG.from_dict(cfg, known_roles=frozenset({"ingestor", "retriever"}))

    def test_known_roles_not_checked_when_empty(self):
        """If known_roles is empty/None, agent role validation is skipped."""
        cfg = {
            "pipeline_id": "test",
            "steps": [
                {"name": "step1", "agent": "anything_goes"},
            ],
        }
        dag = PipelineDAG.from_dict(cfg)
        assert len(dag.execution_order) == 1

    def test_duplicate_step_names_raises(self):
        spec = PipelineSpec(
            pipeline_id="test",
            description="",
            steps=(
                PipelineStep(name="dup", agent_role="a"),
                PipelineStep(name="dup", agent_role="b"),
            ),
        )
        with pytest.raises(PipelineError, match="Duplicate step names"):
            PipelineDAG(spec, frozenset())


class TestPipelineDAGSort:
    """Tests for topological sort."""

    def test_linear_order(self):
        cfg = {
            "pipeline_id": "test",
            "steps": [
                {"name": "a", "agent": "x"},
                {"name": "b", "agent": "x", "depends_on": ["a"]},
                {"name": "c", "agent": "x", "depends_on": ["b"]},
            ],
        }
        dag = PipelineDAG.from_dict(cfg)
        names = [s.name for s in dag.execution_order]
        assert names == ["a", "b", "c"]

    def test_diamond_dependency(self):
        """Diamond: a -> b, a -> c, b -> d, c -> d."""
        cfg = {
            "pipeline_id": "test",
            "steps": [
                {"name": "a", "agent": "x"},
                {"name": "b", "agent": "x", "depends_on": ["a"]},
                {"name": "c", "agent": "x", "depends_on": ["a"]},
                {"name": "d", "agent": "x", "depends_on": ["b", "c"]},
            ],
        }
        dag = PipelineDAG.from_dict(cfg)
        names = [s.name for s in dag.execution_order]

        # a must come first, d must come last
        assert names[0] == "a"
        assert names[-1] == "d"
        # b and c can be in any order between a and d
        assert set(names[1:3]) == {"b", "c"}

    def test_cycle_detected(self):
        cfg = {
            "pipeline_id": "test",
            "steps": [
                {"name": "a", "agent": "x", "depends_on": ["b"]},
                {"name": "b", "agent": "x", "depends_on": ["a"]},
            ],
        }
        with pytest.raises(PipelineError, match="Cycle detected"):
            PipelineDAG.from_dict(cfg)

    def test_self_cycle_detected(self):
        cfg = {
            "pipeline_id": "test",
            "steps": [
                {"name": "a", "agent": "x", "depends_on": ["a"]},
            ],
        }
        with pytest.raises(PipelineError, match="Cycle detected"):
            PipelineDAG.from_dict(cfg)

    def test_independent_steps_both_included(self):
        """Steps with no dependencies should all be in the output."""
        cfg = {
            "pipeline_id": "test",
            "steps": [
                {"name": "x", "agent": "a"},
                {"name": "y", "agent": "b"},
                {"name": "z", "agent": "c"},
            ],
        }
        dag = PipelineDAG.from_dict(cfg)
        names = [s.name for s in dag.execution_order]
        assert set(names) == {"x", "y", "z"}
