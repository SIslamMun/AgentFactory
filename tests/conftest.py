"""Shared fixtures for all test levels."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock

import pytest

from agent_factory.iowarp.cache import BlobCache
from agent_factory.iowarp.client import IOWarpClient
from agent_factory.iowarp.models import (
    BundleResult,
    DestroyResult,
    QueryResultModel,
    RetrieveResultModel,
)


# ---------------------------------------------------------------------------
# Docker readiness helpers
# ---------------------------------------------------------------------------

def _is_docker_running() -> bool:
    """Check if Docker services are available."""
    return os.environ.get("AGENT_FACTORY_DOCKER", "0") == "1"


docker_required = pytest.mark.skipif(
    not _is_docker_running(),
    reason="Docker services not available (set AGENT_FACTORY_DOCKER=1)",
)


# ---------------------------------------------------------------------------
# Mock IOWarp client
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_iowarp_client() -> IOWarpClient:
    """Return an IOWarpClient with all bridge methods mocked."""
    client = MagicMock(spec=IOWarpClient)

    client.context_bundle.return_value = BundleResult(
        status="ok", tag="test_tag", stub=True,
    )
    client.context_query.return_value = QueryResultModel(
        matches=[{"tag": "test_tag", "blob": "data.arrow"}],
        stub=True,
    )
    client.context_retrieve.return_value = RetrieveResultModel(
        data="48656c6c6f",  # "Hello" in hex
        encoding="hex",
        stub=True,
    )
    client.context_destroy.return_value = DestroyResult(
        status="ok", destroyed=["test_tag"], stub=True,
    )
    return client


# ---------------------------------------------------------------------------
# Mock cache
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_cache() -> BlobCache:
    """Return a BlobCache with mocked memcached client."""
    cache = MagicMock(spec=BlobCache)
    cache.hits = 0
    cache.misses = 0
    cache.hit_rate = 0.0
    cache.get.return_value = None  # default: miss
    cache.put.return_value = None
    cache.delete.return_value = True
    cache.invalidate_tag.return_value = 0
    return cache


# ---------------------------------------------------------------------------
# Sample blueprint
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_blueprint() -> dict[str, Any]:
    """Minimal valid blueprint dict."""
    return {
        "blueprint": {
            "name": "test_agent",
            "version": "0.1.0",
        },
        "iowarp": {
            "bridge_endpoint": "tcp://127.0.0.1:5560",
            "connect_timeout_ms": 1000,
            "request_timeout_ms": 5000,
        },
        "cache": {
            "hosts": [{"host": "127.0.0.1", "port": 11211}],
            "key_prefix": "test",
            "default_ttl": 60,
        },
        "uri_resolver": {
            "temp_dir": "/tmp/agent-factory-test/uri-cache",
        },
        "environment": {
            "type": "iowarp",
            "default_format": "arrow",
            "reward": {
                "cache_hit": 0.3,
                "cache_miss": 0.2,
                "assimilate_success": 0.1,
                "query_success": 0.1,
                "prune_success": 0.05,
                "error": -0.5,
            },
        },
        "agent": {
            "type": "rule_based",
        },
    }


@pytest.fixture()
def distributed_blueprint() -> dict[str, Any]:
    """Multi-node blueprint dict for distributed tests."""
    return {
        "blueprint": {
            "name": "test_distributed",
            "version": "0.1.0",
        },
        "iowarp": {
            "bridge_endpoints": [
                "tcp://127.0.0.1:5560",
                "tcp://127.0.0.1:5561",
            ],
            "connect_timeout_ms": 1000,
            "request_timeout_ms": 5000,
        },
        "cache": {
            "hosts": [
                {"host": "127.0.0.1", "port": 11211},
                {"host": "127.0.0.1", "port": 11212},
            ],
            "key_prefix": "test",
            "default_ttl": 60,
        },
        "uri_resolver": {
            "temp_dir": "/tmp/agent-factory-test/uri-cache",
        },
        "environment": {
            "type": "iowarp",
            "default_format": "arrow",
            "reward": {
                "cache_hit": 0.3,
                "cache_miss": 0.2,
                "assimilate_success": 0.1,
                "query_success": 0.1,
                "prune_success": 0.05,
                "error": -0.5,
            },
        },
        "agent": {
            "type": "rule_based",
        },
    }
