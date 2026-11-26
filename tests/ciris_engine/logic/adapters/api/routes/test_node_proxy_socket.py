"""A call's frames socket opened on the agent's listener reaches the node (2.23.2).

The desktop app points CIRIS_NODE_URL at the agent (desktop_launcher), so a call's HTTP join was forwarded but its
frames WebSocket answered 403: the app left at once and every call ended ``why="left"`` with nothing published
(Eric's laptop, 2026-11-21). These run the proxy against a real WebSocket server standing in for the node.
"""

from __future__ import annotations

import asyncio
import socket
import threading
from typing import Any, Dict, List, Optional

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient, WebSocketDenialResponse

from ciris_engine.logic.adapters.api.routes import node_proxy

ROOM = "chat:pair:v1:" + "ab" * 32


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class FakeNode:
    """A WebSocket server on loopback: echoes frames, records what it was sent, refuses without a ticket."""

    def __init__(self) -> None:
        self.port = _free_port()
        self.seen: Dict[str, Any] = {}
        self.closes: List[Optional[int]] = []
        self.loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._stop: Optional[asyncio.Future[None]] = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    async def _handler(self, ws: Any) -> None:
        from websockets.exceptions import ConnectionClosed

        self.seen["path"] = ws.request.path
        self.seen["authorization"] = ws.request.headers.get("Authorization")
        try:
            async for message in ws:
                if message == "close-from-node":
                    await ws.close(code=4001, reason="node hung up")
                    return
                await ws.send(message)
        except ConnectionClosed:
            pass
        self.closes.append(ws.close_code)

    def _process_request(self, connection: Any, request: Any) -> Any:
        if "ticket=" not in request.path:
            return connection.respond(401, "ticket required\n")
        return None

    async def _main(self) -> None:
        from websockets.asyncio.server import serve

        self._stop = self.loop.create_future()
        async with serve(self._handler, "127.0.0.1", self.port, process_request=self._process_request):
            self._ready.set()
            await self._stop

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._main())

    def __enter__(self) -> "FakeNode":
        self.thread.start()
        assert self._ready.wait(5)
        return self

    def __exit__(self, *exc: Any) -> None:
        self.loop.call_soon_threadsafe(lambda: self._stop is not None and self._stop.set_result(None))
        self.thread.join(5)


@pytest.fixture
def node(monkeypatch: pytest.MonkeyPatch) -> Any:
    with FakeNode() as fake:
        monkeypatch.setattr(node_proxy, "NODE_FOLD_PORT", fake.port)
        yield fake


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(node_proxy.router, prefix="/v1")
    return TestClient(app)


def test_the_frames_socket_reaches_the_node_with_its_ticket_and_credential(node: FakeNode, client: TestClient) -> None:
    with client.websocket_connect(
        f"/v1/chat/{ROOM}/call/frames?ticket=t-123", headers={"Authorization": "Bearer sess:abc"}
    ) as ws:
        ws.send_bytes(b"\x00\x01frame")
        assert ws.receive_bytes() == b"\x00\x01frame"
        ws.send_text("hello")
        assert ws.receive_text() == "hello"
    assert node.seen["path"] == f"/v1/chat/{ROOM}/call/frames?ticket=t-123"
    assert node.seen["authorization"] == "Bearer sess:abc"


def test_the_share_socket_is_forwarded_too(node: FakeNode, client: TestClient) -> None:
    with client.websocket_connect(f"/v1/chat/{ROOM}/call/share/frames?ticket=s-1") as ws:
        ws.send_bytes(b"screen")
        assert ws.receive_bytes() == b"screen"


def test_the_nodes_refusal_is_its_own_status_never_403(node: FakeNode, client: TestClient) -> None:
    """No ticket: the node answers 401, and the app sees 401, not the agent's 403."""
    with pytest.raises(WebSocketDenialResponse) as denied:
        with client.websocket_connect(f"/v1/chat/{ROOM}/call/frames"):
            pass
    assert denied.value.status_code == 401


def test_a_close_from_the_app_reaches_the_node_as_a_close(node: FakeNode, client: TestClient) -> None:
    """The node reads a close as why="left" and an error as "lost": the app's hang-up must arrive as a close."""
    with client.websocket_connect(f"/v1/chat/{ROOM}/call/frames?ticket=t") as ws:
        ws.send_text("ping")
        assert ws.receive_text() == "ping"
        ws.close(code=1000)
    for _ in range(50):
        if node.closes:
            break
        threading.Event().wait(0.05)
    assert node.closes == [1000]


def test_the_nodes_close_reaches_the_app_with_its_code(node: FakeNode, client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect(f"/v1/chat/{ROOM}/call/frames?ticket=t") as ws:
        ws.send_text("close-from-node")
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_text()
    assert closed.value.code == 4001


@pytest.mark.parametrize("path", ["/v1/agent/elsewhere", f"/v1/chat/{ROOM}/messages", "/v1/chat/a/../call/frames"])
def test_only_node_socket_paths_are_forwarded(node: FakeNode, client: TestClient, path: str) -> None:
    with pytest.raises(WebSocketDenialResponse) as denied:
        with client.websocket_connect(path + "?ticket=t"):
            pass
    assert denied.value.status_code in (400, 404)
    assert "path" not in node.seen, "nothing reached the node"


def test_an_unreachable_node_is_502(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    monkeypatch.setattr(node_proxy, "NODE_FOLD_PORT", _free_port())
    with pytest.raises(WebSocketDenialResponse) as denied:
        with client.websocket_connect(f"/v1/chat/{ROOM}/call/frames?ticket=t"):
            pass
    assert denied.value.status_code == 502
