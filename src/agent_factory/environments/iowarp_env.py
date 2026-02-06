"""IOWarp environment — implements the Environment protocol.

Wraps IOWarpClient + BlobCache + URIResolver to provide a step-based
interface.  Tracks cache hit rate for reward shaping.

Supported actions:
    assimilate  — ingest data (resolves URIs, write-through cache)
    query       — find blobs matching patterns
    retrieve    — cache-aside retrieval
    prune       — selectively delete blobs or tags + invalidate cache
    list_blobs  — list stored blobs for a tag pattern
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agent_factory.core.errors import IOWarpError
from agent_factory.core.types import Action, Observation, StepResult, TaskSpec
from agent_factory.iowarp.cache import BlobCache
from agent_factory.iowarp.client import IOWarpClient
from agent_factory.iowarp.uri_resolver import URIResolver

log = logging.getLogger(__name__)


@dataclass
class RewardConfig:
    """Reward values for each outcome."""

    cache_hit: float = 0.3
    cache_miss: float = 0.2
    assimilate_success: float = 0.1
    query_success: float = 0.1
    prune_success: float = 0.05
    error: float = -0.5


class IOWarpEnvironment:
    """Step-based environment wrapping IOWarp + memcached.

    Satisfies the ``Environment`` protocol from
    ``agent_factory.core.protocols``.
    """

    def __init__(
        self,
        client: IOWarpClient,
        cache: BlobCache,
        resolver: URIResolver,
        default_format: str = "arrow",
        reward_config: RewardConfig | None = None,
    ) -> None:
        self._client = client
        self._cache = cache
        self._resolver = resolver
        self._default_format = default_format
        self._rewards = reward_config or RewardConfig()

        self._task: TaskSpec | None = None
        self._last_obs: Observation = Observation(text="Environment not yet reset.")

    # -- Environment protocol ------------------------------------------------

    def reset(self, task: TaskSpec) -> Observation:
        self._task = task
        self._cache.reset_stats()
        self._last_obs = Observation(
            text=f"Environment ready. Task: {task.instruction}",
            data={"task_id": task.task_id},
        )
        return self._last_obs

    def step(self, action: Action) -> StepResult:
        handler = {
            "assimilate": self._do_assimilate,
            "query": self._do_query,
            "retrieve": self._do_retrieve,
            "prune": self._do_prune,
            "destroy": self._do_destroy,
            "list_blobs": self._do_list_blobs,
        }.get(action.name)

        if handler is None:
            obs = Observation(text=f"Unknown action: {action.name}")
            self._last_obs = obs
            return StepResult(observation=obs, reward=self._rewards.error)

        try:
            return handler(action.params)
        except IOWarpError as exc:
            obs = Observation(text=f"IOWarp error: {exc}")
            self._last_obs = obs
            return StepResult(observation=obs, reward=self._rewards.error)
        except Exception as exc:
            obs = Observation(text=f"Unexpected error: {exc}")
            self._last_obs = obs
            return StepResult(observation=obs, reward=self._rewards.error)

    def observe(self) -> Observation:
        return self._last_obs

    def close(self) -> None:
        self._client.close()
        self._cache.close()

    # -- action handlers -----------------------------------------------------

    def _do_assimilate(self, params: dict[str, Any]) -> StepResult:
        src = params["src"]
        dst = params["dst"]
        fmt = params.get("format", self._default_format)

        # Resolve extended URIs
        resolved = self._resolver.resolve(src)

        # Call bridge
        result = self._client.context_bundle(src=resolved, dst=dst, format=fmt)

        # Write-through cache: store raw source data for each resolved URI
        # (only for local files — remote URIs are not cached this way)
        cached_count = 0
        for uri in resolved:
            if uri.startswith("file::"):
                path = uri[len("file::"):]
                try:
                    with open(path, "rb") as f:
                        blob_data = f.read()
                    blob_name = path.rsplit("/", 1)[-1]
                    self._cache.put(dst, blob_name, blob_data)
                    cached_count += 1
                except (OSError, Exception) as exc:
                    log.warning("Write-through cache failed for %s: %s", path, exc)

        obs = Observation(
            text=f"Assimilated {len(resolved)} file(s) into tag '{dst}'. "
                 f"Cached {cached_count} blob(s).",
            data={"tag": result.tag, "files": len(resolved), "cached": cached_count},
        )
        self._last_obs = obs
        return StepResult(
            observation=obs,
            reward=self._rewards.assimilate_success,
        )

    def _do_query(self, params: dict[str, Any]) -> StepResult:
        tag_pattern = params.get("tag_pattern", "*")
        blob_pattern = params.get("blob_pattern", "*")

        # Query memcached directly since IOWarp query returns 0 in stub mode
        try:
            matches = self._cache.query_keys(tag_pattern)
            count = len(matches)
            obs = Observation(
                text=f"Query returned {count} match(es) from cache.",
                data={"matches": matches},
            )
            self._last_obs = obs
            return StepResult(
                observation=obs,
                reward=self._rewards.query_success,
            )
        except Exception as exc:
            log.warning(f"Cache query failed, falling back to IOWarp: {exc}")
            # Fallback to IOWarp
            result = self._client.context_query(
                tag_pattern=tag_pattern,
                blob_pattern=blob_pattern,
            )
            obs = Observation(
                text=f"Query returned {len(result.matches)} match(es).",
                data={"matches": result.matches},
            )
            self._last_obs = obs
            return StepResult(
                observation=obs,
                reward=self._rewards.query_success,
            )

    def _do_retrieve(self, params: dict[str, Any]) -> StepResult:
        tag = params["tag"]
        blob_name = params["blob_name"]

        # Cache-aside: check cache first
        cached = self._cache.get(tag, blob_name)
        if cached is not None:
            obs = Observation(
                text=f"Retrieved '{blob_name}' from cache (hit).",
                data={"tag": tag, "blob_name": blob_name, "cache_hit": True,
                      "size": len(cached)},
            )
            self._last_obs = obs
            return StepResult(
                observation=obs,
                reward=self._rewards.cache_hit,
            )

        # Cache miss — fetch from IOWarp
        result = self._client.context_retrieve(tag=tag, blob_name=blob_name)

        # Decode hex-encoded bytes if needed
        data = result.data
        if isinstance(data, str) and result.encoding == "hex":
            data = bytes.fromhex(data)

        # Populate cache
        if isinstance(data, (bytes, bytearray)):
            self._cache.put(tag, blob_name, data)

        obs = Observation(
            text=f"Retrieved '{blob_name}' from IOWarp (cache miss, now cached).",
            data={"tag": tag, "blob_name": blob_name, "cache_hit": False,
                  "size": len(data) if data else 0},
        )
        self._last_obs = obs
        return StepResult(
            observation=obs,
            reward=self._rewards.cache_miss,
        )

    def _do_prune(self, params: dict[str, Any]) -> StepResult:
        """Prune (evict) specific blobs from cache only.

        This is cache management - removes entries from memcached but
        keeps data in IOWarp persistent storage. Data will be re-cached
        on next access (cache miss → IOWarp fallback).

        Requires ``blob_names`` parameter - cannot prune without specifying
        which blobs to evict.
        """
        tag = params["tag"]
        blob_names: list[str] | None = params.get("blob_names")

        if not blob_names:
            obs = Observation(
                text="Prune requires 'blob_names' parameter. Use 'destroy' to delete entire tags.",
            )
            self._last_obs = obs
            return StepResult(observation=obs, reward=self._rewards.error)

        # Evict from cache only (IOWarp data remains)
        invalidated = self._cache.invalidate_tag(tag, blob_names=blob_names)

        obs = Observation(
            text=f"Pruned {invalidated} blob(s) from cache. Data remains in IOWarp.",
            data={"tag": tag, "pruned": blob_names, "evicted": invalidated},
        )
        self._last_obs = obs
        return StepResult(
            observation=obs,
            reward=self._rewards.prune_success,
        )

    def _do_destroy(self, params: dict[str, Any]) -> StepResult:
        """Destroy entire tag(s) from both IOWarp and cache.

        This is permanent deletion - removes from persistent storage (IOWarp)
        and invalidates all cache entries for the tag(s).
        """
        tags = params["tags"]
        if isinstance(tags, str):
            tags = [tags]

        # First, enumerate cached blobs for these tags so we can invalidate them
        blobs_to_invalidate: dict[str, list[str]] = {}
        for tag in tags:
            try:
                matches = self._cache.query_keys(tag_pattern=tag)
                blob_names = [m["blob_name"] for m in matches if m["tag"] == tag]
                if blob_names:
                    blobs_to_invalidate[tag] = blob_names
            except Exception as exc:
                log.warning(f"Could not query cache for tag '{tag}': {exc}")

        # Destroy from IOWarp persistent storage
        result = self._client.context_destroy(tags=tags)

        # Invalidate all cache entries for these tags
        total_invalidated = 0
        for tag in tags:
            blob_names = blobs_to_invalidate.get(tag)
            if blob_names:
                total_invalidated += self._cache.invalidate_tag(tag, blob_names=blob_names)

        obs = Observation(
            text=f"Destroyed {len(result.destroyed)} tag(s) from IOWarp. Invalidated {total_invalidated} cache entries.",
            data={"destroyed": result.destroyed, "cache_invalidated": total_invalidated},
        )
        self._last_obs = obs
        return StepResult(
            observation=obs,
            reward=self._rewards.prune_success,
        )

    def _do_list_blobs(self, params: dict[str, Any]) -> StepResult:
        tag_pattern = params.get("tag_pattern", "*")

        result = self._client.context_query(
            tag_pattern=tag_pattern,
            blob_pattern="*",
        )

        obs = Observation(
            text=f"Listed blobs: {len(result.matches)} match(es).",
            data={"matches": result.matches},
        )
        self._last_obs = obs
        return StepResult(
            observation=obs,
            reward=self._rewards.query_success,
        )

    # -- stats ---------------------------------------------------------------

    @property
    def cache_hit_rate(self) -> float:
        return self._cache.hit_rate
