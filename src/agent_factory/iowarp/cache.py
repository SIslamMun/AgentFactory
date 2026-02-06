"""BlobCache — memcached cache-aside layer for IOWarp blob data.

Key format: ``iowarp:{tag}:{blob_name}`` (SHA-256 hashed if >250 bytes).

Supports both single-server and distributed (multi-server) caching:
  - Single host  → ``pymemcache.Client``
  - Multiple hosts → ``pymemcache.HashClient`` (consistent-hash sharding)
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from pymemcache.client.base import Client
from pymemcache.client.hash import HashClient

from agent_factory.core.errors import CacheError

log = logging.getLogger(__name__)

_MAX_KEY_LEN = 250


def _make_key(prefix: str, tag: str, blob_name: str) -> str:
    """Build a memcached key, hashing if it would exceed the 250-byte limit."""
    raw = f"{prefix}:{tag}:{blob_name}"
    if len(raw.encode()) <= _MAX_KEY_LEN:
        return raw
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return f"{prefix}:h:{hashed}"


class BlobCache:
    """Cache-aside wrapper around memcached for IOWarp blob data.

    Provides get/put/delete plus tag-level invalidation.
    Tracks hit/miss counts for reward computation.

    When *hosts* contains more than one entry, keys are automatically
    distributed across servers using consistent hashing
    (``pymemcache.HashClient``).
    """

    def __init__(
        self,
        hosts: list[tuple[str, int]] | None = None,
        *,
        host: str = "127.0.0.1",
        port: int = 11211,
        key_prefix: str = "iowarp",
        default_ttl: int = 3600,
    ) -> None:
        if hosts:
            self._hosts = list(hosts)
        else:
            self._hosts = [(host, port)]
        self._prefix = key_prefix
        self._default_ttl = default_ttl
        self._client: Client | HashClient | None = None

        # Stats
        self.hits = 0
        self.misses = 0

    @property
    def node_count(self) -> int:
        """Number of cache nodes configured."""
        return len(self._hosts)

    # -- lifecycle -----------------------------------------------------------

    def connect(self) -> None:
        try:
            if len(self._hosts) == 1:
                self._client = Client(
                    self._hosts[0],
                    connect_timeout=5,
                    timeout=5,
                )
            else:
                self._client = HashClient(
                    self._hosts,
                    connect_timeout=5,
                    timeout=5,
                    use_pooling=True,
                )
            # Smoke-test the connection
            self._client.set(f"{self._prefix}:__probe__", b"1", expire=10)
            val = self._client.get(f"{self._prefix}:__probe__")
            if val is None:
                raise CacheError("Memcached probe failed — no value returned")
            self._client.delete(f"{self._prefix}:__probe__")
            hosts_str = ", ".join(f"{h}:{p}" for h, p in self._hosts)
            log.info("Connected to memcached (%d node(s): %s)", len(self._hosts), hosts_str)
        except CacheError:
            raise
        except Exception as exc:
            raise CacheError(f"Memcached connection failed: {exc}") from exc

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    # -- cache operations ----------------------------------------------------

    def get(self, tag: str, blob_name: str) -> bytes | None:
        """Get cached blob data.  Returns None on miss."""
        if self._client is None:
            raise CacheError("Not connected — call connect() first")
        key = _make_key(self._prefix, tag, blob_name)
        try:
            val = self._client.get(key)
        except Exception as exc:
            log.warning("Cache get failed for %s: %s", key, exc)
            self.misses += 1
            return None
        if val is None:
            self.misses += 1
            return None
        self.hits += 1
        return val

    def put(
        self,
        tag: str,
        blob_name: str,
        data: bytes,
        ttl: int | None = None,
    ) -> None:
        """Store blob data in cache (write-through)."""
        if self._client is None:
            raise CacheError("Not connected — call connect() first")
        key = _make_key(self._prefix, tag, blob_name)
        expire = ttl if ttl is not None else self._default_ttl
        try:
            self._client.set(key, data, expire=expire)
        except Exception as exc:
            log.warning("Cache put failed for %s: %s", key, exc)
            raise CacheError(f"Cache put failed: {exc}") from exc

    def delete(self, tag: str, blob_name: str) -> bool:
        """Delete a single cached blob.  Returns True if key existed."""
        if self._client is None:
            raise CacheError("Not connected — call connect() first")
        key = _make_key(self._prefix, tag, blob_name)
        try:
            return self._client.delete(key, noreply=False)  # type: ignore[return-value]
        except Exception as exc:
            log.warning("Cache delete failed for %s: %s", key, exc)
            return False

    def invalidate_tag(self, tag: str, blob_names: list[str] | None = None) -> int:
        """Invalidate cached entries for a tag.

        If *blob_names* is provided, only those blobs are deleted.
        Otherwise this is a best-effort operation — call after a
        context_destroy / prune so stale data is evicted.

        Returns count of keys deleted.
        """
        if self._client is None:
            raise CacheError("Not connected — call connect() first")
        if blob_names is None:
            log.info("Tag-level invalidation requested for '%s' (no blob list)", tag)
            return 0
        count = 0
        for name in blob_names:
            if self.delete(tag, name):
                count += 1
        return count

    def query_keys(self, tag_pattern: str = "*") -> list[dict[str, str]]:
        """Query cached keys matching tag pattern.
        
        Returns list of {"tag": str, "blob_name": str} dicts.
        Uses stats cachedump to enumerate keys from memcached.
        """
        if self._client is None:
            raise CacheError("Not connected — call connect() first")
        
        import socket
        
        # For distributed cache, only query first node (limitation)
        if len(self._hosts) == 1:
            host, port = self._hosts[0]
        else:
            host, port = self._hosts[0]
            log.warning("query_keys on distributed cache queries only first node")
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))
            
            # Get slab IDs
            sock.send(b"stats items\r\n")
            response = b""
            while True:
                chunk = sock.recv(4096)
                response += chunk
                if b"END\r\n" in response:
                    break
            
            # Parse slab IDs
            slab_ids = set()
            for line in response.decode().split('\n'):
                if line.startswith('STAT items:'):
                    parts = line.split(':')
                    if len(parts) >= 2:
                        slab_id = parts[1].split(':')[0]
                        slab_ids.add(slab_id)
            
            # Get keys from each slab
            all_keys = []
            for slab_id in slab_ids:
                sock.send(f"stats cachedump {slab_id} 100\r\n".encode())
                response = b""
                while True:
                    chunk = sock.recv(4096)
                    response += chunk
                    if b"END\r\n" in response:
                        break
                
                for line in response.decode().split('\n'):
                    if line.startswith('ITEM'):
                        parts = line.split(' ')
                        if len(parts) >= 2:
                            key = parts[1]
                            all_keys.append(key)
            
            sock.close()
            
            # Parse keys matching our prefix and pattern
            matches = []
            for key in all_keys:
                # Keys are: iowarp:tag:blob_name or iowarp:h:hash
                if not key.startswith(f"{self._prefix}:"):
                    continue
                
                parts = key.split(':', 2)
                if len(parts) == 3 and parts[1] != 'h':  # Skip hashed keys
                    tag = parts[1]
                    blob_name = parts[2]
                    
                    # Filter by tag pattern
                    if tag_pattern == "*" or tag == tag_pattern or tag.startswith(tag_pattern.rstrip("*")):
                        matches.append({"tag": tag, "blob_name": blob_name})
            
            return matches
            
        except Exception as exc:
            log.error(f"query_keys failed: {exc}")
            return []

    def register_blob(self, tag: str, blob_name: str, data: bytes) -> None:
        """Alias for put() — used during assimilation write-through."""
        self.put(tag, blob_name, data)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def reset_stats(self) -> None:
        self.hits = 0
        self.misses = 0
