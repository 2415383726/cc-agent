"""A local MCP protocol peer; no Dify SDK or production services."""

import base64
import json
import queue
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@contextmanager
def mcp_server():
    channels = {}
    stopped = threading.Event()
    requests = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):
            pass

        def reply(self, code, payload=None, session_id=None):
            body = json.dumps(payload).encode() if payload is not None else b""
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if session_id:
                self.send_header("Mcp-Session-Id", session_id)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path != "/sse":
                self.reply(405)
                return
            channel = str(len(channels))
            messages = queue.Queue()
            channels[channel] = messages
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(f"event: endpoint\ndata: /messages/{channel}\n\n".encode())
            self.wfile.flush()
            while not stopped.is_set():
                try:
                    payload = messages.get(timeout=0.1)
                except queue.Empty:
                    continue
                try:
                    self.wfile.write(
                        b"event: message\ndata: " + json.dumps(payload).encode() + b"\n\n"
                    )
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
            self.close_connection = True

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((data, dict(self.headers)))
            if "id" not in data:
                self.reply(202)
                return
            method = data["method"]
            if method == "initialize":
                result = {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "test", "version": "1"},
                }
            elif method == "tools/list":
                result = {
                    "tools": [
                        {
                            "name": "echo",
                            "description": "Echo test input",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"text": {"type": "string"}},
                                "required": ["text"],
                            },
                        }
                    ]
                }
            elif method == "tools/call":
                if data["params"]["arguments"]["text"] == "timeout":
                    self.reply(202)
                    return
                result = {
                    "content": [{"type": "text", "text": data["params"]["arguments"]["text"]}]
                }
                if data["params"]["arguments"]["text"] == "binary":
                    result = {
                        "content": [
                            {
                                "type": "image",
                                "mimeType": "image/png",
                                "data": base64.b64encode(b"runtime image").decode(),
                            }
                        ]
                    }
            else:
                result = {}
            response = {"jsonrpc": "2.0", "id": data["id"], "result": result}
            if self.path.startswith("/messages/"):
                channels[self.path.rsplit("/", 1)[1]].put(response)
                self.reply(202)
            else:
                self.reply(
                    200, response, session_id="test-session" if method == "initialize" else None
                )

        def do_DELETE(self):
            requests.append(({"method": "DELETE"}, dict(self.headers)))
            self.reply(200, {})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        stopped.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
