"""Tests for BlobCache with mocked memcached client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent_factory.core.errors import CacheError
from agent_factory.iowarp.cache import BlobCache, _make_key


class TestMakeKey:
    def test_short_key(self):
        key = _make_key("iowarp", "tag1", "blob1")
        assert key == "iowarp:tag1:blob1"

    def test_long_key_is_hashed(self):
        long_tag = "a" * 200
        long_blob = "b" * 200
        key = _make_key("iowarp", long_tag, long_blob)
        assert key.startswith("iowarp:h:")
        assert len(key) <= 250


class TestBlobCache:
    @pytest.fixture()
    def cache_with_mock(self):
        """BlobCache with a mocked pymemcache Client."""
        cache = BlobCache(hosts=[("127.0.0.1", 11211)])
        mock_client = MagicMock()
        cache._client = mock_client
        return cache, mock_client

    def test_get_hit(self, cache_with_mock):
        cache, mock_client = cache_with_mock
        mock_client.get.return_value = b"some data"

        result = cache.get("tag1", "blob1")

        assert result == b"some data"
        assert cache.hits == 1
        assert cache.misses == 0

    def test_get_miss(self, cache_with_mock):
        cache, mock_client = cache_with_mock
        mock_client.get.return_value = None

        result = cache.get("tag1", "blob1")

        assert result is None
        assert cache.hits == 0
        assert cache.misses == 1

    def test_get_exception_counts_as_miss(self, cache_with_mock):
        cache, mock_client = cache_with_mock
        mock_client.get.side_effect = ConnectionError("down")

        result = cache.get("tag1", "blob1")

        assert result is None
        assert cache.misses == 1

    def test_put(self, cache_with_mock):
        cache, mock_client = cache_with_mock
        cache.put("tag1", "blob1", b"data", ttl=120)
        mock_client.set.assert_called_once()
        args = mock_client.set.call_args
        assert args[0][1] == b"data"
        assert args[1]["expire"] == 120

    def test_put_default_ttl(self, cache_with_mock):
        cache, mock_client = cache_with_mock
        cache._default_ttl = 3600
        cache.put("tag1", "blob1", b"data")
        args = mock_client.set.call_args
        assert args[1]["expire"] == 3600

    def test_put_error_raises(self, cache_with_mock):
        cache, mock_client = cache_with_mock
        mock_client.set.side_effect = ConnectionError("down")
        with pytest.raises(CacheError, match="Cache put failed"):
            cache.put("tag1", "blob1", b"data")

    def test_delete(self, cache_with_mock):
        cache, mock_client = cache_with_mock
        mock_client.delete.return_value = True
        assert cache.delete("tag1", "blob1") is True

    def test_invalidate_tag_with_names(self, cache_with_mock):
        cache, mock_client = cache_with_mock
        mock_client.delete.return_value = True
        count = cache.invalidate_tag("tag1", blob_names=["a", "b", "c"])
        assert count == 3

    def test_invalidate_tag_without_names(self, cache_with_mock):
        cache, mock_client = cache_with_mock
        count = cache.invalidate_tag("tag1")
        assert count == 0  # best-effort, no blob list

    def test_register_blob(self, cache_with_mock):
        cache, mock_client = cache_with_mock
        cache.register_blob("tag1", "blob1", b"data")
        mock_client.set.assert_called_once()

    def test_hit_rate(self, cache_with_mock):
        cache, _ = cache_with_mock
        assert cache.hit_rate == 0.0
        cache.hits = 7
        cache.misses = 3
        assert abs(cache.hit_rate - 0.7) < 1e-9

    def test_reset_stats(self, cache_with_mock):
        cache, _ = cache_with_mock
        cache.hits = 10
        cache.misses = 5
        cache.reset_stats()
        assert cache.hits == 0
        assert cache.misses == 0

    def test_not_connected_raises(self):
        cache = BlobCache()
        with pytest.raises(CacheError, match="Not connected"):
            cache.get("t", "b")
        with pytest.raises(CacheError, match="Not connected"):
            cache.put("t", "b", b"x")


class TestBlobCacheDistributed:
    """Tests for multi-node BlobCache (HashClient path)."""

    def test_single_host_node_count(self):
        cache = BlobCache(hosts=[("127.0.0.1", 11211)])
        assert cache.node_count == 1

    def test_multi_host_node_count(self):
        cache = BlobCache(hosts=[("node1", 11211), ("node2", 11212)])
        assert cache.node_count == 2

    def test_backward_compat_host_port(self):
        cache = BlobCache(host="10.0.0.1", port=11299)
        assert cache._hosts == [("10.0.0.1", 11299)]
        assert cache.node_count == 1

    def test_hosts_overrides_host_port(self):
        cache = BlobCache(
            hosts=[("a", 1), ("b", 2)],
            host="ignored",
            port=9999,
        )
        assert cache._hosts == [("a", 1), ("b", 2)]

    @patch("agent_factory.iowarp.cache.HashClient")
    def test_multi_host_uses_hash_client(self, mock_hash_cls):
        mock_instance = MagicMock()
        mock_instance.get.return_value = b"1"
        mock_hash_cls.return_value = mock_instance

        cache = BlobCache(hosts=[("a", 11211), ("b", 11212)])
        cache.connect()

        mock_hash_cls.assert_called_once()
        call_args = mock_hash_cls.call_args
        assert ("a", 11211) in call_args[0][0]
        assert ("b", 11212) in call_args[0][0]

    @patch("agent_factory.iowarp.cache.Client")
    def test_single_host_uses_base_client(self, mock_client_cls):
        mock_instance = MagicMock()
        mock_instance.get.return_value = b"1"
        mock_client_cls.return_value = mock_instance

        cache = BlobCache(hosts=[("127.0.0.1", 11211)])
        cache.connect()

        mock_client_cls.assert_called_once()

    def test_multi_host_operations_with_mock(self):
        cache = BlobCache(hosts=[("a", 1), ("b", 2)])
        mock_client = MagicMock()
        cache._client = mock_client

        mock_client.get.return_value = b"data"
        assert cache.get("tag", "blob") == b"data"
        assert cache.hits == 1

        cache.put("tag", "blob2", b"data2")
        mock_client.set.assert_called_once()
