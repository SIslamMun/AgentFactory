"""ZeroMQ REP bridge wrapping the wrp_cee Python API.

Runs inside the IOWarp container.  Exposes a JSON-RPC-style interface
over ZeroMQ so the host-side AgentFactory can drive the context engine
without needing wrp_cee installed locally.

Supported methods:
    ping              → {"result": "pong"}
    context_bundle    → assimilate data into the context engine
    context_query     → query for tags/blobs matching patterns
    context_retrieve  → retrieve blob data
    context_destroy   → destroy a context (tag set)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback

import zmq

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [bridge] %(levelname)s %(message)s",
)
log = logging.getLogger("bridge")

# ---------------------------------------------------------------------------
# wrp_cee import — only available inside the IOWarp container
# ---------------------------------------------------------------------------
try:
    import wrp_cee
    HAS_WRP = True
    log.info("wrp_cee imported successfully")
except ImportError:
    HAS_WRP = False
    log.warning("wrp_cee not available — bridge will return stub responses")


# ---------------------------------------------------------------------------
# Handler functions
# ---------------------------------------------------------------------------

def handle_ping(params: dict) -> dict:
    return {"result": "pong"}


def handle_context_bundle(params: dict) -> dict:
    """Assimilate data into the context engine.

    Expected params:
        src: str | list[str]  — source URI(s) (file::, hdf5::, etc.)
        dst: str              — destination tag
        format: str           — data format hint (arrow, csv, json, ...)
    """
    src = params["src"]
    dst = params["dst"]
    fmt = params.get("format", "arrow")

    # Call stub or real wrp_cee function
    result = wrp_cee.context_bundle(src=src, dst=dst, format=fmt)
    
    # If stub returns a dict with details, use it; otherwise create simple response
    if isinstance(result, dict):
        return {"result": result}
    else:
        stub_marker = {"stub": True} if not HAS_WRP else {}
        return {"result": {"status": "ok", "tag": dst, **stub_marker}}


def handle_context_query(params: dict) -> dict:
    """Query the context engine for matching tags/blobs.

    Expected params:
        tag_pattern: str   — glob pattern for tags
        blob_pattern: str  — glob pattern for blob names (optional)
    """
    tag_pattern = params.get("tag_pattern", "*")
    blob_pattern = params.get("blob_pattern", "*")

    # Call stub or real wrp_cee function
    matches = wrp_cee.context_query(
        tag_pattern=tag_pattern,
        blob_pattern=blob_pattern,
    )
    # matches may be a list of dicts or custom objects — normalise to dicts
    normalised = []
    for m in matches:
        if isinstance(m, dict):
            normalised.append(m)
        else:
            normalised.append({"tag": str(m)})
    
    stub_marker = {"stub": True} if not HAS_WRP else {}
    return {"result": {"matches": normalised, **stub_marker}}


def handle_context_retrieve(params: dict) -> dict:
    """Retrieve blob data from the context engine.

    Expected params:
        tag: str        — context tag
        blob_name: str  — blob identifier within the tag
    """
    tag = params["tag"]
    blob_name = params["blob_name"]

    # Call stub or real wrp_cee function
    data = wrp_cee.context_retrieve(tag=tag, blob_name=blob_name)

    # Encode bytes as hex for JSON transport; caller decodes
    if isinstance(data, (bytes, bytearray)):
        stub_marker = {"stub": True} if not HAS_WRP else {}
        return {"result": {"data": data.hex(), "encoding": "hex", **stub_marker}}
    
    stub_marker = {"stub": True} if not HAS_WRP else {}
    return {"result": {"data": data, **stub_marker}}


def handle_context_destroy(params: dict) -> dict:
    """Destroy a context (tag set).

    Expected params:
        tags: str | list[str]  — tag(s) to destroy
    """
    tags = params["tags"]
    if isinstance(tags, str):
        tags = [tags]

    # Call wrp_cee with tags (not tag) - wrp_cee handles the loop internally
    result = wrp_cee.context_destroy(tags)
    
    # Add stub marker if needed
    if not HAS_WRP and isinstance(result, dict):
        result["stub"] = True
    return {"result": result}


def handle_stub_state(params: dict) -> dict:
    """Debug handler to inspect storage state (stub or real backend)."""
    return {"result": wrp_cee.get_stub_state()}


DISPATCH = {
    "ping": handle_ping,
    "context_bundle": handle_context_bundle,
    "context_query": handle_context_query,
    "context_retrieve": handle_context_retrieve,
    "context_destroy": handle_context_destroy,
    "stub_state": handle_stub_state,
}


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    port = int(os.environ.get("BRIDGE_PORT", "5560"))
    ctx = zmq.Context()
    socket = ctx.socket(zmq.REP)
    socket.bind(f"tcp://*:{port}")
    log.info("Bridge listening on tcp://*:%d", port)

    while True:
        try:
            raw = socket.recv_json()
        except Exception:
            log.error("Failed to receive/parse message:\n%s", traceback.format_exc())
            continue

        method = raw.get("method", "")
        params = raw.get("params", {})
        req_id = raw.get("id")
        
        log.info(f"Received: method={method}, params={params}")

        handler = DISPATCH.get(method)
        if handler is None:
            resp = {"error": f"unknown method: {method}"}
        else:
            try:
                resp = handler(params)
                log.info(f"Handler {method} result: {list(resp.keys()) if isinstance(resp, dict) else type(resp)}")
            except Exception as exc:
                log.error("Handler %s failed:\n%s", method, traceback.format_exc())
                resp = {"error": str(exc)}

        if req_id is not None:
            resp["id"] = req_id

        socket.send_json(resp)


if __name__ == "__main__":
    main()
