"""Integration test: full IOWarp environment lifecycle against live services."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_factory.core.types import Action, TaskSpec
from agent_factory.environments.iowarp_env import IOWarpEnvironment
from agent_factory.iowarp.cache import BlobCache
from agent_factory.iowarp.client import IOWarpClient
from agent_factory.iowarp.uri_resolver import URIResolver

pytestmark = pytest.mark.integration

SAMPLE_DOCS = Path(__file__).resolve().parents[2] / "data" / "sample_docs"


@pytest.fixture()
def env(tmp_path):
    """Live IOWarpEnvironment connected to Docker services."""
    client = IOWarpClient(endpoint="tcp://127.0.0.1:5560")
    cache = BlobCache(host="127.0.0.1", port=11211, key_prefix="inttest")
    resolver = URIResolver(cache=cache, temp_dir=str(tmp_path))

    client.connect()
    cache.connect()

    environment = IOWarpEnvironment(
        client=client, cache=cache, resolver=resolver,
    )
    yield environment
    environment.close()


class TestEnvironmentLifecycle:
    def test_reset_and_observe(self, env):
        task = TaskSpec(task_id="int1", instruction="integration test")
        obs = env.reset(task)
        assert "ready" in obs.text.lower()

        current = env.observe()
        assert current.text == obs.text

    def test_assimilate_markdown_files(self, env):
        """Ingest real markdown files via folder:: URI."""
        task = TaskSpec(task_id="int2", instruction="ingest docs")
        env.reset(task)

        action = Action(
            name="assimilate",
            params={
                "src": f"folder::{SAMPLE_DOCS}",
                "dst": "int_docs",
                "format": "markdown",
            },
        )
        result = env.step(action)
        assert result.reward > 0
        assert result.observation.data["files"] == 3
        assert result.observation.data["cached"] == 3

    def test_query_after_assimilate(self, env):
        task = TaskSpec(task_id="int3", instruction="query docs")
        env.reset(task)

        # assimilate first
        env.step(Action(
            name="assimilate",
            params={"src": f"folder::{SAMPLE_DOCS}", "dst": "int_docs2"},
        ))

        # then query
        result = env.step(Action(
            name="query", params={"tag_pattern": "int_docs*"},
        ))
        assert result.reward > 0

    def test_retrieve_from_cache(self, env):
        """After assimilate, retrieve should be a cache hit."""
        task = TaskSpec(task_id="int4", instruction="retrieve from cache")
        env.reset(task)

        # assimilate writes through to cache
        env.step(Action(
            name="assimilate",
            params={"src": f"folder::{SAMPLE_DOCS}", "dst": "int_docs3"},
        ))

        # retrieve — should hit cache
        result = env.step(Action(
            name="retrieve",
            params={"tag": "int_docs3", "blob_name": "project_overview.md"},
        ))
        assert result.reward > 0
        assert result.observation.data["cache_hit"] is True
        assert result.observation.data["size"] > 0

    def test_unknown_action(self, env):
        task = TaskSpec(task_id="int5", instruction="test bad action")
        env.reset(task)

        action = Action(name="nonexistent", params={})
        result = env.step(action)
        assert result.reward < 0
