"""Minimal MCP stdio server. The model asks for one thing; it does not receive the whole pack.

Run: python -m ingest.mcp_server PACK_DIR
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ingest.ask import answer


class _BadFrame(Exception):
    """A frame the client sent wrongly. It gets an error reply; the server keeps running."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _read_message() -> dict | None:
    """Next message, or None once the client has closed the stream."""
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        key, _, value = line.decode("utf-8", "replace").partition(":")
        headers[key.strip().lower()] = value.strip()
    try:
        length = int(headers.get("content-length", ""))
    except ValueError:
        raise _BadFrame(-32700, "brak albo zły nagłówek Content-Length") from None
    if length < 0:
        raise _BadFrame(-32700, "ujemny Content-Length")
    body = sys.stdin.buffer.read(length)
    if len(body) < length:
        return None
    try:
        message = json.loads(body.decode("utf-8"))
    except ValueError as exc:
        raise _BadFrame(-32700, f"zły JSON: {exc}") from None
    if not isinstance(message, dict):
        raise _BadFrame(-32600, "wiadomość musi być obiektem JSON")
    return message


def _write(payload: dict) -> None:
    raw = json.dumps(payload).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


TOOLS = [
    {
        "name": "get_forces",
        "description": "Siły, docisk i moment z jednej paczki. Bez zdjęć.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_part",
        "description": "Podsumowanie profilu jednej części: fw, rw albo ut. Bez pełnej chmury punktów.",
        "inputSchema": {
            "type": "object",
            "properties": {"part": {"type": "string"}},
            "required": ["part"],
        },
    },
    {
        "name": "get_device",
        "description": (
            "Karta jednego urządzenia aero z geometry.yaml: profil, cięciwa, rozpiętość, kąt, LE/TE. "
            "Bez device zwraca listę dostępnych id."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"device": {"type": "string"}},
        },
    },
    {
        "name": "get_slice",
        "description": "Jedna klatka najbliższa stacji. Zwraca nazwę pliku i części, nie piksele.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "axis": {"type": "string"},
                "station": {"type": "number"},
                "field": {"type": "string"},
            },
            "required": ["axis", "station"],
        },
    },
]


def main() -> None:
    pack = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path("packs")
    while True:
        try:
            message = _read_message()
        except _BadFrame as exc:
            _write({"jsonrpc": "2.0", "id": None, "error": {"code": exc.code, "message": str(exc)}})
            continue
        if message is None:
            return
        method = message.get("method")
        msg_id = message.get("id")
        if method == "initialize":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "fsae-aero", "version": "1"},
                    },
                }
            )
        elif method == "notifications/initialized":
            continue
        elif method == "ping":
            _write({"jsonrpc": "2.0", "id": msg_id, "result": {}})
        elif method == "tools/list":
            _write({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            params = message.get("params")
            if not isinstance(params, dict):
                params = {}
            name = params.get("name")
            args = params.get("arguments") or {}
            try:
                payload = answer(pack, name, args)
                text = json.dumps(payload, ensure_ascii=False, indent=2)
                result = {"content": [{"type": "text", "text": text}], "isError": False}
            except Exception as exc:
                result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
            _write({"jsonrpc": "2.0", "id": msg_id, "result": result})
        elif msg_id is not None:
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"nieznane: {method}"},
                }
            )


if __name__ == "__main__":
    main()
