"""Synthetic HTTP protocol fixture. This is not a model or production fallback."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "symsoil-synthetic-test:latest"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def send_json(self, code, data):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path != "/api/tags":
            return self.send_json(404, {"error": "fixture has no such endpoint"})
        self.send_json(200, {"models": [{"name": MODEL, "model": MODEL, "size": 1, "digest": "synthetic-protocol-fixture-only"}]})

    def do_POST(self):
        if self.path != "/api/chat":
            return self.send_json(404, {"error": "fixture has no such endpoint"})
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            if data.get("model") != MODEL or data.get("stream") is not False or not isinstance(data.get("format"), dict) or data.get("tools"):
                raise ValueError("protocol does not match")
            messages = data["messages"]
            if [message["role"] for message in messages] != ["system", "user"]:
                raise ValueError("unexpected history")
            supplied = json.loads(messages[-1]["content"])
            if set(supplied) == {"original", "context", "target_context", "purpose"}:
                result = {"candidates": [
                    {"kind": "everyday", "text": "合成模型协议样本：我希望先把清理工具与责任说清楚；尚未接受任务。"},
                    {"kind": "discussion", "text": "合成模型协议样本：请在活动前核实清理范围、工具及承担条件，不将此表达视为劳动承诺。"},
                ], "clarifications": ["合成模型协议样本：你希望谁负责确认工具？"]}
            elif set(supplied) == {"question", "sources"}:
                sources = supplied["sources"]
                if not sources or any(set(source) != {"citation_id", "title", "source", "quote"} for source in sources):
                    raise ValueError("unexpected citation fields")
                result = {"answer": "合成问答协议样本：请根据获准资料核对清理工具与条件；这不是实际模型质量证明。", "citation_ids": [sources[0]["citation_id"]]}
            else:
                raise ValueError("unexpected user fields")
            self.server.chat_calls += 1
            self.send_json(200, {"model": MODEL, "done": True, "message": {"role": "assistant", "content": json.dumps(result, ensure_ascii=False)}})
        except (ValueError, KeyError, TypeError):
            self.send_json(400, {"error": "synthetic protocol request invalid"})


def make_server():
    server = ThreadingHTTPServer(("127.0.0.1", 11435), Handler)
    server.chat_calls = 0
    return server
