"""End-to-end test: the real AgentFactory workflow.

The idea:
    1. Agent ingests markdown files through IOWarp  (folder:: → assimilate)
    2. Memcached caches the blobs on write-through
    3. Agent retrieves data via cache-aside          (miss → IOWarp → cache, hit → cache)
    4. Agent uses the retrieved data to do its task  (summarise / answer questions)
    5. Agent prunes what it doesn't need

Runs without Docker by mocking the bridge (IOWarpClient).  The cache
write-through and cache-aside paths are fully exercised against real
file I/O — only the bridge RPC is stubbed.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent_factory.agents.iowarp_agent import IOWarpAgent
from agent_factory.core.types import Action, Observation, StepResult, TaskSpec, Trajectory
from agent_factory.environments.iowarp_env import IOWarpEnvironment, RewardConfig
from agent_factory.factory.builder import AgentBuilder
from agent_factory.factory.registry import BlueprintRegistry
from agent_factory.iowarp.cache import BlobCache
from agent_factory.iowarp.client import IOWarpClient
from agent_factory.iowarp.models import (
    BundleResult,
    DestroyResult,
    QueryResultModel,
    RetrieveResultModel,
)
from agent_factory.iowarp.uri_resolver import URIResolver

pytestmark = pytest.mark.e2e

# Path to the sample markdown docs shipped in the repo
SAMPLE_DOCS = Path(__file__).resolve().parents[2] / "data" / "sample_docs"


# ── helpers ────────────────────────────────────────────────────────────────


def _make_bridge_mock(tag: str, blob_names: list[str]) -> MagicMock:
    """Build an IOWarpClient mock that behaves like the real bridge."""
    client = MagicMock(spec=IOWarpClient)

    # assimilate succeeds
    client.context_bundle.return_value = BundleResult(status="ok", tag=tag)

    # query returns the blobs we ingested
    client.context_query.return_value = QueryResultModel(
        matches=[{"tag": tag, "blob": name} for name in blob_names],
    )

    # retrieve returns the raw content (hex-encoded, as the bridge does)
    def _retrieve(*, tag: str, blob_name: str) -> RetrieveResultModel:
        # Simulate: bridge reads blob bytes and returns hex
        path = SAMPLE_DOCS / blob_name
        if path.exists():
            return RetrieveResultModel(
                data=path.read_bytes().hex(), encoding="hex",
            )
        return RetrieveResultModel(data=None, encoding=None)

    client.context_retrieve.side_effect = _retrieve

    # prune succeeds
    client.context_destroy.return_value = DestroyResult(
        status="ok", destroyed=[tag],
    )
    return client


# ── the real workflow test ────────────────────────────────────────────────


class TestMarkdownIngestionWorkflow:
    """Demonstrates the full idea:

    ingest markdown → cache them → retrieve from cache → agent task → prune.
    """

    @pytest.fixture()
    def wired_stack(self, tmp_path):
        """Wire up all components.  Bridge is mocked; cache uses a mock
        that actually stores data in a dict so we can verify real
        write-through / cache-aside behaviour.
        """
        # Discover the markdown files we'll ingest
        md_files = sorted(SAMPLE_DOCS.glob("*.md"))
        blob_names = [f.name for f in md_files]

        # -- bridge mock (only RPC is stubbed) --
        client = _make_bridge_mock(tag="docs", blob_names=blob_names)

        # -- cache: dict-backed so write-through / cache-aside really work --
        store: dict[str, bytes] = {}
        cache = MagicMock(spec=BlobCache)
        cache.hits = 0
        cache.misses = 0

        def _cache_get(tag: str, blob_name: str) -> bytes | None:
            key = f"{tag}:{blob_name}"
            val = store.get(key)
            if val is not None:
                cache.hits += 1
            else:
                cache.misses += 1
            return val

        def _cache_put(tag: str, blob_name: str, data: bytes, ttl: int | None = None) -> None:
            store[f"{tag}:{blob_name}"] = data

        def _cache_delete(tag: str, blob_name: str) -> bool:
            return store.pop(f"{tag}:{blob_name}", None) is not None

        def _cache_invalidate(tag: str, blob_names: list[str] | None = None) -> int:
            if blob_names is None:
                return 0
            count = 0
            for b in blob_names:
                if store.pop(f"{tag}:{b}", None) is not None:
                    count += 1
            return count

        cache.get.side_effect = _cache_get
        cache.put.side_effect = _cache_put
        cache.delete.side_effect = _cache_delete
        cache.invalidate_tag.side_effect = _cache_invalidate
        cache.reset_stats.side_effect = lambda: None
        cache.hit_rate = property(lambda self: 0.0)

        resolver = URIResolver(cache=cache, temp_dir=str(tmp_path))
        env = IOWarpEnvironment(client=client, cache=cache, resolver=resolver)
        agent = IOWarpAgent()

        return env, agent, client, cache, store, blob_names

    # ------------------------------------------------------------------ #
    #  STEP 1: ingest markdown files through IOWarp                       #
    # ------------------------------------------------------------------ #
    def test_full_workflow(self, wired_stack):
        env, agent, client, cache, store, blob_names = wired_stack

        task = TaskSpec(
            task_id="md_ingest_01",
            instruction=(
                "Load the project documentation from folder::./data/sample_docs, "
                "retrieve each document, then prune unused data."
            ),
        )
        obs = env.reset(task)
        traj = Trajectory(task=task)

        # ── 1. Ingest: folder:: resolves to individual file:: URIs ─────
        assimilate = Action(
            name="assimilate",
            params={
                "src": f"folder::{SAMPLE_DOCS}",
                "dst": "docs",
                "format": "markdown",
            },
        )
        result = env.step(assimilate)
        traj = traj.append(assimilate, result)

        assert result.reward > 0, "assimilate should succeed"
        assert result.observation.data["files"] == len(blob_names)
        # write-through: every .md file is now in the cache dict
        assert result.observation.data["cached"] == len(blob_names)
        for name in blob_names:
            assert f"docs:{name}" in store, f"{name} should be cached after write-through"

        # ── 2. Query: see what was stored ──────────────────────────────
        query = Action(name="query", params={"tag_pattern": "docs"})
        result = env.step(query)
        traj = traj.append(query, result)

        assert result.reward > 0
        assert len(result.observation.data["matches"]) == len(blob_names)

        # ── 3. Retrieve: cache HIT (data is already there from step 1) ─
        retrieve_hit = Action(
            name="retrieve",
            params={"tag": "docs", "blob_name": "project_overview.md"},
        )
        result = env.step(retrieve_hit)
        traj = traj.append(retrieve_hit, result)

        assert result.reward > 0
        assert result.observation.data["cache_hit"] is True
        assert result.observation.data["size"] > 0
        # The bridge should NOT have been called for context_retrieve
        client.context_retrieve.assert_not_called()

        # ── 4. Simulate cache expiry, then retrieve: cache MISS ────────
        #    Remove one blob from the cache to simulate TTL expiry
        del store["docs:api_reference.md"]

        retrieve_miss = Action(
            name="retrieve",
            params={"tag": "docs", "blob_name": "api_reference.md"},
        )
        result = env.step(retrieve_miss)
        traj = traj.append(retrieve_miss, result)

        assert result.reward > 0
        assert result.observation.data["cache_hit"] is False
        # Bridge WAS called this time
        client.context_retrieve.assert_called_once_with(
            tag="docs", blob_name="api_reference.md",
        )
        # And the blob is now re-cached
        assert "docs:api_reference.md" in store

        # ── 5. Agent decides next step from observation ────────────────
        #    The rule-based agent reads the observation and picks an action
        thought = agent.think(result.observation)
        assert isinstance(thought, str)

        # Give the agent a new instruction-style observation
        task_obs = Observation(
            text="Delete tag: docs to clean up after task completion",
        )
        next_action = agent.act(task_obs)
        assert next_action.name == "prune"

        # ── 6. Prune: clean up selectively ─────────────────────────────
        prune = Action(
            name="prune",
            params={
                "tags": ["docs"],
                "blob_names": blob_names,  # selective: only these blobs
            },
        )
        result = env.step(prune)
        traj = traj.append(prune, result)

        assert result.reward > 0
        assert "pruned" in result.observation.text.lower()
        # Cache entries should be gone
        for name in blob_names:
            assert f"docs:{name}" not in store

        # ── Summary ────────────────────────────────────────────────────
        assert traj.length == 5
        assert traj.total_reward > 0
        print(
            f"\nTrajectory: {traj.length} steps, "
            f"total reward: {traj.total_reward:.2f}, "
            f"cache hits: {cache.hits}, misses: {cache.misses}"
        )


# ── blueprint → build → agent test ───────────────────────────────────────


class TestBlueprintBuild:
    """Building the full stack from the YAML blueprint works."""

    def test_build_from_registry(self):
        registry = BlueprintRegistry()
        registry.load()
        bp = registry.get("iowarp_agent")

        builder = AgentBuilder()
        built = builder.build(bp, connect=False)

        assert isinstance(built.client, IOWarpClient)
        assert isinstance(built.cache, BlobCache)
        assert isinstance(built.resolver, URIResolver)
        assert isinstance(built.environment, IOWarpEnvironment)
        assert isinstance(built.agent, IOWarpAgent)


# ── agent keyword → action mapping ───────────────────────────────────────


class TestAgentDecisions:
    """The rule-based agent correctly maps task text to IOWarp actions."""

    def test_load_instruction(self):
        agent = IOWarpAgent()
        obs = Observation(text="Load markdown files from folder::/data/docs into tag: docs")
        action = agent.act(obs)
        assert action.name == "assimilate"

    def test_search_instruction(self):
        agent = IOWarpAgent()
        obs = Observation(text="Search for all documentation blobs")
        action = agent.act(obs)
        assert action.name == "query"

    def test_get_instruction(self):
        agent = IOWarpAgent()
        obs = Observation(text="Get blob: api_reference.md from tag: docs")
        action = agent.act(obs)
        assert action.name == "retrieve"

    def test_delete_instruction(self):
        agent = IOWarpAgent()
        obs = Observation(text="Delete tag: old_docs to free space")
        action = agent.act(obs)
        assert action.name == "prune"

    def test_unknown_defaults_to_query(self):
        agent = IOWarpAgent()
        obs = Observation(text="What is the current status?")
        action = agent.act(obs)
        assert action.name == "query"
