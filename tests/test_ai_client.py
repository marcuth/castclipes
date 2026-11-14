"""Testa o AiSdkClient contra um servidor local que imita a API de chat completions."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from jaguar_xiv_missao.ai.factory import create_llm_client
from jaguar_xiv_missao.analysis.triage import LLMVideoTriage, TriageVerdict
from jaguar_xiv_missao.config import Settings
from jaguar_xiv_missao.models import SourceVideo

REQUESTS: list[dict] = []


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        REQUESTS.append({"path": self.path, "auth": self.headers.get("Authorization"), **body})
        content = json.dumps({"score": 0.9, "reason": "entrevista longa com Renan Santos"})
        chunks = [
            {"choices": [{"index": 0, "delta": {"role": "assistant", "content": content}}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for chunk in chunks:
            payload = {"id": "c1", "object": "chat.completion.chunk", "model": "m", **chunk}
            self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    REQUESTS.clear()
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}/v1"
    httpd.shutdown()


def test_structured_output_via_ai_sdk(server):
    settings = Settings(
        _env_file=None, ai_provider="openai", ai_base_url=server, ai_api_key="k", ai_model="m"
    )
    client = create_llm_client(settings)
    try:
        # duas chamadas seguidas: garantem que o event loop persistente funciona
        first = client.generate("sistema", "usuário", TriageVerdict)
        second = client.generate("sistema", "usuário", TriageVerdict)
    finally:
        client.close()
    assert first.score == 0.9 and "Renan" in second.reason
    assert REQUESTS[0]["auth"] == "Bearer k"
    assert "json_schema" in json.dumps(REQUESTS[0])  # saída estruturada pedida ao provedor


def test_triage_uses_client(server):
    settings = Settings(_env_file=None, ai_base_url=server, ai_api_key="k", ai_model="m")
    client = create_llm_client(settings)
    try:
        result = LLMVideoTriage(client, 0.7).evaluate(SourceVideo(id="x", title="Entrevista"))
    finally:
        client.close()
    assert result.approved and result.score == 0.9
