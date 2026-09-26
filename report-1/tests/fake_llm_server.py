"""OpenAI 호환 가짜 LLM 서버 — 사내 LLM 없이 Report–1 의 초안 흐름을 돌린다 (테스트 · E2E · 스크린샷용).

  python tests/fake_llm_server.py [포트]      혼자 띄우기 (기본 18975, mode=good)

모드 (FakeLLM.mode):
  good     근거 목록에서 줄을 만들고 줄마다 refs 를 단다
  lie      good + 근거 없는 실적 한 줄 ('성과 30% 향상') — Report–1 이 ERR 로 막아야 한다
  fence    good 을 ```json … ``` 울타리와 앞뒤 말로 감싼다
  garbage  JSON 이 아닌 답 (두 번째 요청부터는 good) — 다시 요청하는지 본다
  error    HTTP 500
받은 요청의 본문은 requests 에 쌓인다 (체크를 푼 근거가 보내지지 않았는지 확인용).
"""
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeLLM:
    def __init__(self, port: int = 0, mode: str = "good"):
        self.mode = mode
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path.rstrip("/").endswith("/models"):
                    return self._send(200, {"data": [{"id": "fake-model"}]})
                self._send(404, {"error": "not found"})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                outer.requests.append(body)
                if outer.mode == "error":
                    return self._send(500, {"error": {"message": "boom"}})
                self._send(200, {"choices": [{"message": {"role": "assistant", "content": outer.answer(body)}}]})

            def _send(self, code, obj):
                data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def answer(self, body):
        text = "\n".join(str(m.get("content", "")) for m in body.get("messages", []))
        if "연결 확인" in text:
            return "확인"
        if self.mode == "garbage" and len(self.requests) == 1:
            return "주간보고를 정리해 드리겠습니다. 이번 주에는 많은 일을 하셨네요!"
        src = re.findall(r"^\[([a-z]\d+)\] (\S+) (커밋|일정|일지|다음 일정)(?: · ([^·\n]+))? · (.+)$", text, re.M)
        done, nxt = [], []
        commits = {}
        for sid, _, kind, where, title in src:
            if kind == "커밋":
                commits.setdefault((where or "").strip(), []).append((sid, title.strip()))
            elif kind == "일지":
                done.append({"text": title.strip() + " 완료", "refs": [sid]})
            elif kind == "일정":
                done.append({"text": f"{title.strip()} 참석", "refs": [sid]})
            elif kind == "다음 일정":
                nxt.append({"text": f"{title.strip()} 준비", "refs": [sid]})
        for repo, cs in commits.items():
            done.insert(0, {"text": f"{repo} {cs[-1][1]} 등 {len(cs)}건 반영", "refs": [c[0] for c in cs]})
        if self.mode == "lie":
            done.append({"text": "성과 30% 향상", "refs": []})
        out = json.dumps({"sections": [{"lines": done}, {"lines": nxt}, {"lines": []}]}, ensure_ascii=False)
        if self.mode == "fence":
            return f"다음과 같이 정리했습니다.\n```json\n{out}\n```\n확인 부탁드립니다."
        return out


if __name__ == "__main__":
    srv = FakeLLM(int(sys.argv[1]) if len(sys.argv) > 1 else 18975)
    print(f"가짜 LLM: {srv.url}  (Ctrl+C 로 끄기)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.close()
