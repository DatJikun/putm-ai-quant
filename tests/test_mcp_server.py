"""The MCP stdio server end to end: a real subprocess speaking Content-Length framed JSON-RPC."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "tests" / "fixtures" / "ask-pack"


class Client:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "ingest.mcp_server", str(PACK)],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._next_id = 0

    def send_raw(self, body: bytes, length: int | None = None) -> None:
        length = len(body) if length is None else length
        self.proc.stdin.write(f"Content-Length: {length}\r\n\r\n".encode("ascii") + body)
        self.proc.stdin.flush()

    def send(self, message: dict) -> None:
        self.send_raw(json.dumps(message, ensure_ascii=False).encode("utf-8"))

    def receive(self) -> dict:
        length = None
        while True:
            line = self.proc.stdout.readline()
            assert line, "server closed stdout: " + self.proc.stderr.read().decode(errors="replace")
            if line in (b"\r\n", b"\n"):
                break
            key, _, value = line.decode("ascii").partition(":")
            if key.lower() == "content-length":
                length = int(value)
        assert length is not None
        return json.loads(self.proc.stdout.read(length))

    def call(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        message = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)
        reply = self.receive()
        assert reply["id"] == self._next_id
        return reply

    def tool(self, name: str, arguments: dict | None = None) -> dict:
        return self.call("tools/call", {"name": name, "arguments": arguments or {}})["result"]

    def close(self) -> int:
        self.proc.stdin.close()
        code = self.proc.wait(timeout=10)
        self.proc.stdout.close()
        self.proc.stderr.close()
        return code


@pytest.fixture
def client():
    conn = Client()
    yield conn
    if conn.proc.poll() is None:
        conn.proc.kill()
        conn.proc.wait()
        conn.proc.stdout.close()
        conn.proc.stderr.close()


def test_initialize_announces_tools(client):
    result = client.call("initialize", {})["result"]
    assert result["serverInfo"]["name"] == "fsae-aero"
    assert result["protocolVersion"]
    assert "tools" in result["capabilities"]


def test_tools_list_describes_every_tool(client):
    tools = client.call("tools/list")["result"]["tools"]
    assert [tool["name"] for tool in tools] == ["get_forces", "get_part", "get_device", "get_slice"]
    for tool in tools:
        assert tool["description"]
        assert tool["inputSchema"]["type"] == "object"
    by_name = {tool["name"]: tool for tool in tools}
    assert by_name["get_part"]["inputSchema"]["required"] == ["part"]
    assert by_name["get_slice"]["inputSchema"]["required"] == ["axis", "station"]
    assert "required" not in by_name["get_device"]["inputSchema"]


def test_tool_call_returns_the_pack_answer_as_text(client):
    result = client.tool("get_forces")
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["case"] == "FIX1"
    assert payload["cd"] == 1.186


def test_device_tool_lists_and_returns_cards(client):
    listing = json.loads(client.tool("get_device")["content"][0]["text"])
    assert [item["id"] for item in listing["urzadzenia"]] == ["fw-main", "rw-main"]
    card = json.loads(client.tool("get_device", {"device": "fw-main"})["content"][0]["text"])
    assert card["le"] == {"xMm": -885.95, "zMm": 82.92}


def test_tool_errors_are_results_with_is_error(client):
    unknown_part = client.tool("get_part", {"part": "zzz"})
    assert unknown_part["isError"] is True
    assert unknown_part["content"][0]["text"] == "brak części zzz"
    bad_station = client.tool("get_slice", {"axis": "x", "station": "abc"})
    assert bad_station["isError"] is True
    unknown_tool = client.tool("get_nothing")
    assert unknown_tool["isError"] is True
    assert "nieznane pytanie" in unknown_tool["content"][0]["text"]


def test_non_ascii_arguments_survive_the_byte_length_framing(client):
    result = client.tool("get_part", {"part": "łożysko"})
    assert result["isError"] is True
    assert result["content"][0]["text"] == "brak części łożysko"


def test_notifications_get_no_reply_and_ping_is_answered(client):
    client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    client.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {}})
    assert client.call("ping")["result"] == {}


def test_unknown_method_is_a_json_rpc_error(client):
    reply = client.call("resources/list")
    assert reply["error"]["code"] == -32601


def test_bad_frames_get_an_error_and_the_server_keeps_going(client):
    client.send_raw(b"{not json")
    assert client.receive()["error"]["code"] == -32700
    client.send_raw(b"[1, 2]")
    assert client.receive()["error"]["code"] == -32600
    client.send_raw(b"", length=0)
    assert client.receive()["error"]["code"] == -32700
    client.send({"jsonrpc": "2.0", "id": 99, "method": "tools/call", "params": ["not", "a", "dict"]})
    assert client.receive()["id"] == 99
    assert client.tool("get_forces")["isError"] is False


def test_server_exits_cleanly_when_the_client_disconnects(client):
    client.call("initialize", {})
    assert client.close() == 0
