"""URI resolver — expands extended URI schemes into file:: URIs.

Supported schemes:
    file::/path     → passthrough (native IOWarp)
    hdf5::/path     → passthrough (native IOWarp)
    folder::/dir    → rglob("*") → list of file:: URIs
    mem::tag/blob   → read from cache → write temp file → file::/tmp/...
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from agent_factory.core.errors import URIResolveError
from agent_factory.iowarp.cache import BlobCache

log = logging.getLogger(__name__)

# Schemes handled natively by IOWarp — just pass through
_PASSTHROUGH_SCHEMES = ("file::", "hdf5::")


class URIResolver:
    """Resolves extended URI schemes into file:: URIs the bridge understands."""

    def __init__(
        self,
        cache: BlobCache | None = None,
        temp_dir: str = "/tmp/agent-factory/uri-cache",
    ) -> None:
        self._cache = cache
        self._temp_dir = temp_dir
        os.makedirs(self._temp_dir, exist_ok=True)

    def resolve(self, src: str | list[str]) -> list[str]:
        """Resolve one or more URIs into a flat list of file:: URIs.

        Accepts ``str | list[str]`` per the professor's extended API.
        """
        if isinstance(src, str):
            src = [src]

        resolved: list[str] = []
        for uri in src:
            resolved.extend(self._resolve_single(uri))
        return resolved

    # -- private dispatch ----------------------------------------------------

    def _resolve_single(self, uri: str) -> list[str]:
        if uri.startswith("folder::"):
            return self._resolve_folder(uri)
        if uri.startswith("mem::"):
            return self._resolve_mem(uri)
        for scheme in _PASSTHROUGH_SCHEMES:
            if uri.startswith(scheme):
                return [uri]
        raise URIResolveError(f"Unsupported URI scheme: {uri!r}")

    def _resolve_folder(self, uri: str) -> list[str]:
        """folder::/some/dir → recursive list of file:: URIs."""
        dir_path = uri[len("folder::"):]
        p = Path(dir_path)
        if not p.is_dir():
            raise URIResolveError(f"folder:: target is not a directory: {dir_path}")

        results: list[str] = []
        for child in sorted(p.rglob("*")):
            if child.is_file():
                results.append(f"file::{child}")
        if not results:
            log.warning("folder:: resolved to zero files: %s", dir_path)
        return results

    def _resolve_mem(self, uri: str) -> list[str]:
        """mem::tag/blob → read from cache → write temp file → file:: URI."""
        if self._cache is None:
            raise URIResolveError("mem:: scheme requires a BlobCache but none provided")

        rest = uri[len("mem::"):]
        parts = rest.split("/", 1)
        if len(parts) != 2:
            raise URIResolveError(
                f"mem:: URI must be mem::tag/blob_name, got: {uri!r}"
            )
        tag, blob_name = parts

        data = self._cache.get(tag, blob_name)
        if data is None:
            raise URIResolveError(
                f"mem:: blob not found in cache: tag={tag!r}, blob={blob_name!r}"
            )

        # Write to temp file
        safe_name = blob_name.replace("/", "_").replace("\\", "_")
        tmp_path = os.path.join(self._temp_dir, f"{tag}__{safe_name}")
        with open(tmp_path, "wb") as f:
            f.write(data)

        return [f"file::{tmp_path}"]
