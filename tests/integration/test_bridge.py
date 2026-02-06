"""Integration test: real ZeroMQ to bridge (requires Docker)."""

from __future__ import annotations

import pytest

from agent_factory.iowarp.client import IOWarpClient

pytestmark = pytest.mark.integration


@pytest.fixture()
def client():
    """Live IOWarpClient connected to the Docker bridge."""
    c = IOWarpClient(
        endpoint="tcp://127.0.0.1:5560",
        connect_timeout_ms=5000,
        request_timeout_ms=10000,
    )
    c.connect()
    yield c
    c.close()


class TestBridgePing:
    def test_ping(self, client):
        # connect() already pings — if we got here, the bridge is alive
        assert client is not None


class TestBridgeBundle:
    def test_bundle_stub(self, client):
        result = client.context_bundle(
            src="file::/data/test.csv", dst="test_tag", format="csv",
        )
        assert result.status == "ok"
        assert result.tag == "test_tag"


class TestBridgeQuery:
    def test_query(self, client):
        result = client.context_query(tag_pattern="*")
        assert hasattr(result, "matches")
        assert isinstance(result.matches, list)


class TestBridgeRetrieve:
    def test_retrieve(self, client):
        result = client.context_retrieve(tag="test_tag", blob_name="data")
        assert hasattr(result, "data")


class TestBridgeDestroy:
    def test_destroy(self, client):
        result = client.context_destroy(tags="test_tag")
        assert result.status == "ok"
