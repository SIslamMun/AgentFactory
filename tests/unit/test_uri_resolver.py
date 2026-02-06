"""Tests for URI resolver with mocked filesystem and cache."""

from __future__ import annotations

import os
import tempfile

import pytest

from agent_factory.core.errors import URIResolveError
from agent_factory.iowarp.cache import BlobCache
from agent_factory.iowarp.uri_resolver import URIResolver


class TestFileScheme:
    def test_passthrough(self):
        resolver = URIResolver()
        result = resolver.resolve("file::/data/test.csv")
        assert result == ["file::/data/test.csv"]

    def test_hdf5_passthrough(self):
        resolver = URIResolver()
        result = resolver.resolve("hdf5::/data/test.h5")
        assert result == ["hdf5::/data/test.h5"]


class TestFolderScheme:
    def test_resolves_files(self, tmp_path):
        # Create a mini directory tree
        (tmp_path / "a.csv").write_text("data_a")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.csv").write_text("data_b")

        resolver = URIResolver()
        result = resolver.resolve(f"folder::{tmp_path}")

        assert len(result) == 2
        assert all(r.startswith("file::") for r in result)
        names = [r.split("/")[-1] for r in result]
        assert "a.csv" in names
        assert "b.csv" in names

    def test_empty_folder(self, tmp_path):
        resolver = URIResolver()
        result = resolver.resolve(f"folder::{tmp_path}")
        assert result == []

    def test_nonexistent_dir(self):
        resolver = URIResolver()
        with pytest.raises(URIResolveError, match="not a directory"):
            resolver.resolve("folder::/nonexistent/path")


class TestMemScheme:
    def test_resolves_from_cache(self, tmp_path, mock_cache):
        mock_cache.get.return_value = b"cached data"

        resolver = URIResolver(cache=mock_cache, temp_dir=str(tmp_path))
        result = resolver.resolve("mem::my_tag/my_blob")

        assert len(result) == 1
        assert result[0].startswith("file::")
        # Check the file was written
        fpath = result[0][len("file::"):]
        assert os.path.exists(fpath)
        with open(fpath, "rb") as f:
            assert f.read() == b"cached data"

    def test_cache_miss_raises(self, mock_cache):
        mock_cache.get.return_value = None
        resolver = URIResolver(cache=mock_cache)
        with pytest.raises(URIResolveError, match="not found in cache"):
            resolver.resolve("mem::tag/blob")

    def test_no_cache_raises(self):
        resolver = URIResolver(cache=None)
        with pytest.raises(URIResolveError, match="requires a BlobCache"):
            resolver.resolve("mem::tag/blob")

    def test_bad_format_raises(self, mock_cache):
        resolver = URIResolver(cache=mock_cache)
        with pytest.raises(URIResolveError, match="must be mem::tag/blob_name"):
            resolver.resolve("mem::no_slash_here")


class TestUnsupportedScheme:
    def test_raises(self):
        resolver = URIResolver()
        with pytest.raises(URIResolveError, match="Unsupported URI scheme"):
            resolver.resolve("s3::bucket/key")


class TestMultipleURIs:
    def test_mixed_list(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        resolver = URIResolver()
        result = resolver.resolve([
            "file::/data/x.csv",
            f"folder::{tmp_path}",
        ])
        assert len(result) == 2
        assert result[0] == "file::/data/x.csv"
        assert result[1].startswith("file::")
