"""
wrp_cee wrapper module - provides simple function interface to IOWarp CTE.

Uses the cte_helper C++ binary (subprocess) to communicate with the real
IOWarp CTE runtime. The nanobind Python extension (wrp_cte_core_ext) has an
ABI conflict (libc++ vs libstdc++) causing std::bad_cast on import, so we
bypass it entirely by talking to a long-running C++ helper process via
stdin/stdout JSON lines.

Falls back to in-memory stub when cte_helper is unavailable.
"""
import json
import os
import logging
import subprocess
import threading
import fnmatch

logger = logging.getLogger("wrp_cee")

# ---------------------------------------------------------------------------
# CTE Helper subprocess management
# ---------------------------------------------------------------------------
_CTE_HELPER_PATH = "/usr/local/bin/cte_helper"

_helper_proc = None
_helper_lock = threading.Lock()
_initialized = False
_use_stub = False


def _ensure_initialized():
    """Start the cte_helper subprocess if not already running."""
    global _helper_proc, _initialized, _use_stub

    if _initialized:
        return

    if not os.path.isfile(_CTE_HELPER_PATH):
        logger.warning(f"cte_helper not found at {_CTE_HELPER_PATH} - using stub")
        _initialized = True
        _use_stub = True
        return

    try:
        _helper_proc = subprocess.Popen(
            [_CTE_HELPER_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,  # line-buffered
        )

        # Read lines until we get the JSON ready message
        # (cte_helper may emit C++ log lines before the JSON)
        ready = None
        for _ in range(50):  # max 50 lines of log output
            ready_line = _helper_proc.stdout.readline().strip()
            if not ready_line:
                continue
            if ready_line.startswith("{"):
                ready = json.loads(ready_line)
                break
            else:
                logger.debug(f"cte_helper startup: {ready_line}")

        if ready is None:
            raise RuntimeError("cte_helper produced no JSON ready message")
        if ready.get("status") != "ready":
            raise RuntimeError(f"cte_helper init failed: {ready}")

        targets = ready.get("targets", [])
        target_count = ready.get("target_count", 0)
        logger.info(f"CTE helper ready: {target_count} storage target(s): {targets}")

        if target_count == 0:
            logger.warning("No storage targets - CTE operations may fail")

        _initialized = True
        _use_stub = False

    except Exception as e:
        logger.warning(f"cte_helper init failed: {e} - using stub")
        if _helper_proc and _helper_proc.poll() is None:
            _helper_proc.kill()
        _helper_proc = None
        _initialized = True
        _use_stub = True


def _send_command(cmd_dict):
    """Send a JSON command to cte_helper and return the parsed response."""
    global _helper_proc, _use_stub

    with _helper_lock:
        if _helper_proc is None or _helper_proc.poll() is not None:
            # Helper died — mark as stub
            logger.error("cte_helper process died - falling back to stub")
            _use_stub = True
            _helper_proc = None
            return None

        try:
            line = json.dumps(cmd_dict, separators=(',', ':'))
            _helper_proc.stdin.write(line + "\n")
            _helper_proc.stdin.flush()

            resp_line = _helper_proc.stdout.readline().strip()
            if not resp_line:
                raise RuntimeError("Empty response from cte_helper")

            return json.loads(resp_line)
        except Exception as e:
            logger.error(f"cte_helper communication error: {e}")
            _use_stub = True
            if _helper_proc and _helper_proc.poll() is None:
                _helper_proc.kill()
            _helper_proc = None
            return None


# ---------------------------------------------------------------------------
# Stub storage (fallback when C++ helper unavailable)
# ---------------------------------------------------------------------------
_stub_storage = {}


def _stub_context_bundle(src, dst, format="arrow"):
    sources = [src] if isinstance(src, str) else src
    if dst not in _stub_storage:
        _stub_storage[dst] = {}

    stored_count = 0
    for source in sources:
        if source.startswith("file::"):
            path = source[6:]
            try:
                with open(path, 'rb') as f:
                    blob_name = path.split('/')[-1]
                    content = f.read()
                    _stub_storage[dst][blob_name] = content
                    stored_count += 1
                    logger.info(f"[STUB] Stored {blob_name} in tag '{dst}' ({len(content)} bytes)")
            except Exception as e:
                logger.error(f"[STUB] Failed to store {path}: {e}")

    return {"status": "ok", "tag": dst, "stub": True, "stored": stored_count}


def _stub_context_query(tag_pattern="*", blob_pattern="*"):
    results = []
    for tag_name, blobs in _stub_storage.items():
        if not fnmatch.fnmatch(tag_name, tag_pattern):
            continue
        for blob_name in blobs.keys():
            if fnmatch.fnmatch(blob_name, blob_pattern):
                results.append({
                    "tag": tag_name,
                    "blob": blob_name,
                    "size": len(blobs[blob_name])
                })
    return results


def _stub_context_retrieve(tag, blob_name):
    if tag in _stub_storage and blob_name in _stub_storage[tag]:
        return _stub_storage[tag][blob_name]
    return None


def _stub_context_destroy(tags):
    tag_list = [tags] if isinstance(tags, str) else tags
    for tag in tag_list:
        if tag in _stub_storage:
            del _stub_storage[tag]
    return {"status": "ok", "destroyed": tag_list, "stub": True}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def context_bundle(src, dst, format="arrow"):
    """Ingest data into IOWarp storage.

    Args:
        src: str or list[str] - source path(s) with scheme (file::, folder::)
        dst: str - destination tag name
        format: str - data format (arrow, binary, etc.)

    Returns:
        dict with status and tag info
    """
    _ensure_initialized()

    if _use_stub:
        return _stub_context_bundle(src, dst, format)

    sources = [src] if isinstance(src, str) else src
    stored_count = 0

    for source in sources:
        if source.startswith("file::"):
            path = source[6:]
            try:
                with open(path, 'rb') as f:
                    data = f.read()
                blob_name = os.path.basename(path)
                hex_data = data.hex()

                resp = _send_command({
                    "cmd": "put",
                    "tag": dst,
                    "blob": blob_name,
                    "data": hex_data,
                })

                if resp and resp.get("status") == "ok":
                    stored_count += 1
                    logger.info(f"[CTE] Stored {blob_name} in tag '{dst}' ({len(data)} bytes)")
                else:
                    err = resp.get("message", "unknown") if resp else "no response"
                    logger.error(f"[CTE] Failed to store {blob_name}: {err}")
            except Exception as e:
                logger.error(f"[CTE] Failed to store {path}: {e}")

    return {"status": "ok", "tag": dst, "stored": stored_count}


def context_query(tag_pattern="*", blob_pattern="*"):
    """Query for blobs matching patterns.

    Args:
        tag_pattern: str - glob pattern for tags
        blob_pattern: str - glob pattern for blob names

    Returns:
        list of dicts with tag/blob/size info
    """
    _ensure_initialized()

    if _use_stub:
        return _stub_context_query(tag_pattern, blob_pattern)

    # Convert glob to regex for CTE
    tag_regex = tag_pattern.replace("*", ".*").replace("?", ".")
    blob_regex = blob_pattern.replace("*", ".*").replace("?", ".")

    results = []
    try:
        # Get matching tags
        resp = _send_command({"cmd": "tag_query", "pattern": tag_regex})
        if not resp or resp.get("status") != "ok":
            return results

        tag_names = resp.get("tags", [])

        # For each tag, list blobs and filter
        import re
        for tag_name in tag_names:
            blob_resp = _send_command({"cmd": "list_blobs", "tag": tag_name})
            if not blob_resp or blob_resp.get("status") != "ok":
                continue

            for blob_name in blob_resp.get("blobs", []):
                if re.match(blob_regex, blob_name):
                    # Get blob size
                    size_resp = _send_command({
                        "cmd": "get_size",
                        "tag": tag_name,
                        "blob": blob_name,
                    })
                    size = size_resp.get("size", 0) if size_resp else 0
                    results.append({
                        "tag": tag_name,
                        "blob": blob_name,
                        "size": int(size),
                    })
    except Exception as e:
        logger.error(f"[CTE] Query failed: {e}")

    return results


def context_retrieve(tag, blob_name):
    """Retrieve blob data from IOWarp storage.

    Args:
        tag: str - tag name
        blob_name: str - blob identifier

    Returns:
        bytes - blob data, or None if not found
    """
    _ensure_initialized()

    if _use_stub:
        return _stub_context_retrieve(tag, blob_name)

    try:
        resp = _send_command({"cmd": "get", "tag": tag, "blob": blob_name})

        if not resp or resp.get("status") != "ok":
            err = resp.get("message", "unknown") if resp else "no response"
            logger.warning(f"[CTE] Retrieve '{tag}/{blob_name}' failed: {err}")
            return None

        hex_data = resp.get("data", "")
        data = bytes.fromhex(hex_data)
        logger.info(f"[CTE] Retrieved {len(data)} bytes from '{tag}/{blob_name}'")
        return data

    except Exception as e:
        logger.error(f"[CTE] Retrieve failed: {e}")
        return None


def context_destroy(tags):
    """Destroy context tag(s) and all their blobs.

    Args:
        tags: str or list[str] - tag(s) to destroy

    Returns:
        dict with status info
    """
    _ensure_initialized()

    if _use_stub:
        return _stub_context_destroy(tags)

    tag_list = [tags] if isinstance(tags, str) else tags
    destroyed = []

    for tag_name in tag_list:
        try:
            resp = _send_command({"cmd": "del_tag", "tag": tag_name})
            if resp and resp.get("status") == "ok":
                destroyed.append(tag_name)
                logger.info(f"[CTE] Destroyed tag '{tag_name}'")
            else:
                err = resp.get("message", "unknown") if resp else "no response"
                logger.error(f"[CTE] Failed to destroy tag '{tag_name}': {err}")
        except Exception as e:
            logger.error(f"[CTE] Failed to destroy tag '{tag_name}': {e}")

    return {"status": "ok", "destroyed": destroyed}


def get_stub_state():
    """Debug function to inspect storage state."""
    _ensure_initialized()

    if _use_stub:
        return {
            "backend": "stub",
            "tags": list(_stub_storage.keys()),
            "blobs": {tag: list(blobs.keys()) for tag, blobs in _stub_storage.items()},
            "total_size": sum(sum(len(v) for v in blobs.values()) for blobs in _stub_storage.values())
        }

    # Real backend - query CTE for state via helper
    try:
        resp = _send_command({"cmd": "tag_query", "pattern": ".*"})
        if not resp or resp.get("status") != "ok":
            return {"backend": "cte", "error": "tag_query failed"}

        tag_names = resp.get("tags", [])
        result = {"backend": "cte", "tags": tag_names, "blobs": {}}
        for tag_name in tag_names:
            blob_resp = _send_command({"cmd": "list_blobs", "tag": tag_name})
            if blob_resp and blob_resp.get("status") == "ok":
                result["blobs"][tag_name] = blob_resp.get("blobs", [])
        return result
    except Exception as e:
        return {"backend": "cte", "error": str(e)}


__all__ = ['context_bundle', 'context_query', 'context_retrieve', 'context_destroy', 'get_stub_state']
