"""Integration test: real memcached (requires Docker)."""

from __future__ import annotations

import pytest

from agent_factory.iowarp.cache import BlobCache

pytestmark = pytest.mark.integration


@pytest.fixture()
def cache():
    """Live BlobCache connected to Docker memcached."""
    c = BlobCache(host="127.0.0.1", port=11211, key_prefix="test", default_ttl=60)
    c.connect()
    yield c
    c.close()


class TestMemcachedSetGet:
    def test_round_trip(self, cache):
        cache.put("tag1", "blob1", b"hello world")
        result = cache.get("tag1", "blob1")
        assert result == b"hello world"
        assert cache.hits == 1

    def test_miss(self, cache):
        result = cache.get("nonexistent", "nope")
        assert result is None
        assert cache.misses == 1

    def test_delete(self, cache):
        cache.put("tag1", "blob_del", b"to_delete")
        assert cache.get("tag1", "blob_del") == b"to_delete"
        cache.delete("tag1", "blob_del")
        assert cache.get("tag1", "blob_del") is None

    def test_hit_rate_tracking(self, cache):
        cache.put("tag1", "hr_blob", b"data")
        cache.get("tag1", "hr_blob")      # hit
        cache.get("tag1", "hr_blob")      # hit
        cache.get("tag1", "no_blob")      # miss
        assert cache.hits == 2
        assert cache.misses == 1
        assert abs(cache.hit_rate - 2 / 3) < 1e-9

    def test_large_blob(self, cache):
        """Test with a 1MB blob."""
        data = b"x" * (1024 * 1024)
        cache.put("tag1", "big_blob", data)
        result = cache.get("tag1", "big_blob")
        assert result == data

    def test_markdown_content(self, cache):
        """Store and retrieve actual markdown text."""
        md = b"# Hello\n\nThis is **markdown** with `code`.\n"
        cache.put("docs", "readme.md", md)
        result = cache.get("docs", "readme.md")
        assert result == md
