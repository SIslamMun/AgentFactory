"""ZeroMQ REQ client that talks to the bridge running inside the IOWarp container.

Supports both single-endpoint and multi-endpoint (distributed) operation:
  - Single endpoint  → one REQ socket
  - Multiple endpoints → one REQ socket per endpoint, round-robin with fallback
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from typing import Any

import zmq

from agent_factory.core.errors import BridgeConnectionError, IOWarpError
from agent_factory.iowarp.models import (
    BridgeRequest,
    BridgeResponse,
    BundleParams,
    BundleResult,
    DestroyParams,
    DestroyResult,
    QueryParams,
    QueryResultModel,
    RetrieveParams,
    RetrieveResultModel,
)

log = logging.getLogger(__name__)


@dataclass
class _Peer:
    """A single bridge endpoint with its own ZeroMQ socket."""

    endpoint: str
    ctx: zmq.Context
    socket: zmq.Socket
    alive: bool = True


class IOWarpClient:
    """Client for the IOWarp ZeroMQ bridge.

    Supports one or more bridge endpoints.  When multiple endpoints are
    provided, requests are round-robined across them.  If a peer fails,
    it is skipped and the next peer is tried.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        endpoints: list[str] | None = None,
        connect_timeout_ms: int = 5000,
        request_timeout_ms: int = 30000,
    ) -> None:
        if endpoints:
            self._endpoints = list(endpoints)
        elif endpoint:
            self._endpoints = [endpoint]
        else:
            self._endpoints = ["tcp://127.0.0.1:5560"]

        self._connect_timeout_ms = connect_timeout_ms
        self._request_timeout_ms = request_timeout_ms
        self._peers: list[_Peer] = []
        self._current_idx = 0
        self._id_counter = itertools.count(1)

    @property
    def node_count(self) -> int:
        """Number of bridge endpoints configured."""
        return len(self._endpoints)

    # -- lifecycle -----------------------------------------------------------

    def connect(self) -> None:
        """Open ZeroMQ connections and verify each endpoint with a ping."""
        failed: list[str] = []
        for ep in self._endpoints:
            try:
                peer = self._connect_one(ep)
                self._peers.append(peer)
                log.info("Bridge at %s: OK", ep)
            except BridgeConnectionError as exc:
                log.warning("Bridge at %s: FAILED (%s)", ep, exc)
                failed.append(ep)

        if not self._peers:
            raise BridgeConnectionError(
                f"All bridge endpoints failed: {failed}"
            )

        if failed:
            log.warning(
                "%d of %d bridge endpoints unreachable: %s",
                len(failed), len(self._endpoints), failed,
            )

    def _connect_one(self, endpoint: str) -> _Peer:
        """Connect and ping a single endpoint. Returns a _Peer."""
        ctx = zmq.Context()
        sock = ctx.socket(zmq.REQ)
        sock.setsockopt(zmq.RCVTIMEO, self._connect_timeout_ms)
        sock.setsockopt(zmq.SNDTIMEO, self._connect_timeout_ms)
        sock.setsockopt(zmq.LINGER, 0)
        sock.connect(endpoint)

        # Verify with ping
        req = BridgeRequest(method="ping", params={}, id=0)
        try:
            sock.send_json(req.model_dump())
            raw = sock.recv_json()
        except (zmq.Again, zmq.ZMQError) as exc:
            sock.close()
            ctx.term()
            raise BridgeConnectionError(
                f"Bridge ping failed at {endpoint}: {exc}"
            ) from exc

        resp = BridgeResponse.model_validate(raw)
        if resp.error or resp.result != "pong":
            sock.close()
            ctx.term()
            raise BridgeConnectionError(
                f"Bridge ping failed at {endpoint}: {resp.error or resp.result}"
            )

        return _Peer(endpoint=endpoint, ctx=ctx, socket=sock)

    def close(self) -> None:
        """Tear down all ZeroMQ resources."""
        for peer in self._peers:
            try:
                peer.socket.close()
                peer.ctx.term()
            except Exception:
                pass
        self._peers.clear()
        log.info("Client closed (%d peers)", len(self._endpoints))

    # -- RPC helpers ---------------------------------------------------------

    def _next_peer(self) -> _Peer:
        """Pick the next alive peer via round-robin."""
        alive = [p for p in self._peers if p.alive]
        if not alive:
            raise BridgeConnectionError("No alive bridge peers")
        idx = self._current_idx % len(alive)
        self._current_idx = idx + 1
        return alive[idx]

    def _call(self, method: str, params: dict[str, Any] | None = None) -> BridgeResponse:
        if not self._peers:
            raise BridgeConnectionError("Not connected — call connect() first")

        req = BridgeRequest(
            method=method,
            params=params or {},
            id=next(self._id_counter),
        )

        # Try each alive peer (up to full rotation)
        last_exc: Exception | None = None
        alive_count = sum(1 for p in self._peers if p.alive)
        for _ in range(alive_count):
            peer = self._next_peer()
            peer.socket.setsockopt(zmq.RCVTIMEO, self._request_timeout_ms)
            try:
                peer.socket.send_json(req.model_dump())
                raw = peer.socket.recv_json()
                resp = BridgeResponse.model_validate(raw)
                if resp.error:
                    raise IOWarpError(f"Bridge error on '{method}': {resp.error}")
                return resp
            except (zmq.Again, zmq.ZMQError) as exc:
                log.warning("Peer %s failed: %s — trying next", peer.endpoint, exc)
                peer.alive = False
                last_exc = exc
                # Recreate socket for this peer (REQ socket is stuck after timeout)
                try:
                    peer.socket.close()
                    peer.socket = peer.ctx.socket(zmq.REQ)
                    peer.socket.setsockopt(zmq.LINGER, 0)
                    peer.socket.connect(peer.endpoint)
                    peer.alive = True  # mark alive again with fresh socket
                except Exception:
                    pass

        raise BridgeConnectionError(
            f"All peers failed for '{method}': {last_exc}"
        )

    # -- public API ----------------------------------------------------------

    def context_bundle(
        self,
        src: str | list[str],
        dst: str,
        format: str = "arrow",
    ) -> BundleResult:
        """Assimilate data into the context engine."""
        params = BundleParams(src=src, dst=dst, format=format)
        resp = self._call("context_bundle", params.model_dump())
        return BundleResult.model_validate(resp.result)

    def context_query(
        self,
        tag_pattern: str = "*",
        blob_pattern: str = "*",
    ) -> QueryResultModel:
        """Query for tags/blobs matching patterns."""
        params = QueryParams(tag_pattern=tag_pattern, blob_pattern=blob_pattern)
        resp = self._call("context_query", params.model_dump())
        return QueryResultModel.model_validate(resp.result)

    def context_retrieve(self, tag: str, blob_name: str) -> RetrieveResultModel:
        """Retrieve blob data from the context engine."""
        params = RetrieveParams(tag=tag, blob_name=blob_name)
        resp = self._call("context_retrieve", params.model_dump())
        return RetrieveResultModel.model_validate(resp.result)

    def context_destroy(self, tags: str | list[str]) -> DestroyResult:
        """Destroy context tag(s)."""
        params = DestroyParams(tags=tags)
        resp = self._call("context_destroy", params.model_dump())
        return DestroyResult.model_validate(resp.result)
