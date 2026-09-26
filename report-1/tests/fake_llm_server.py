"""OpenAI 호환 가짜 LLM 서버 — 사내 LLM 없이 Report–1 의 초안 흐름을 돌린다 (테스트 · E2E · 스크린샷용).

  python tests/fake_llm_server.py [포트]      혼자 띄우기 (기본 18975, mode=good)

모드 (FakeLLM.mode):
  good     [자료] 조각에서 줄을 만들고 줄마다 refs 를 단다 (요약 = 추론, 칸마다 사실, 확인 한 줄, 빈칸 한 줄)
  lie      good + 근거 없는 사실 한 줄 ('성과 30% 향상') — Report–1 이 ERR 로 막아야 한다
  number   good + 근거 조각에 없는 숫자 한 줄 ('복구 시간 97분 단축') — '숫자?' 로 표시돼야 한다
           (lie · number 는 'lie number' 처럼 함께 쓸 수 있다)
  inline   refs 목록 대신 글 속에 [p1] 로 근거를 단다 — Report–1 이 근거로 옮겨야 한다
  fence    good 을 ```json … ``` 울타리와 앞뒤 말로 감싼다
  garbage  JSON 이 아닌 답 (두 번째 요청부터는 good) — 다시 요청하는지 본다
  length   잘린 JSON + finish_reason "length" — 다시 요청하지 않고 이유를 알려야 한다
  error    HTTP 500
받은 요청의 본문은 requests 에 쌓인다 (체크를 푼 조각이 보내지지 않았는지 확인용).
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
                content, finish = outer.answer(body)
                self._send(200, {"choices": [{"message": {"role": "assistant", "content": content},
                                              "finish_reason": finish}]})

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
        msgs = body.get("messages", [])
        text = "\n".join(str(m.get("content", "")) for m in msgs)
        if "연결 확인" in text:
            return "확인", "stop"
        if self.mode == "garbage" and len(self.requests) == 1:
            return "보고서를 정리해 드리겠습니다. 자료가 아주 많네요!", "stop"
        frags = re.findall(r"^\[(p\d+)\] \(자료 \d+ · [^)]*\) (.+)$", text, re.M)
        m = re.search(r"칸: ((?:'[^']+'(?: · )?)+) — 이 순서", text)
        secs = re.findall(r"'([^']+)'", m.group(1)) if m else ["요약", "내용"]
        topic = (re.search(r"^토픽: (.+)$", text, re.M) or [None, "보고서"])[1]
        out = {"title": topic if not topic.startswith("(") else "자료 정리", "sections": [{"name": s, "lines": []} for s in secs]}
        body_secs = [s for s in out["sections"] if s["name"] != "요약"] or out["sections"]
        for i, (fid, t) in enumerate(frags):
            first = max(t.split(" / "), key=lambda x: (not re.match(r"(보낸|받는) 사람|제목", x), len(x)))
            first = re.sub(r"^\s*(\[[^\]]*\]\s*)+", "", first).strip()    # [이름] [오후 2:10] 머리 떼기
            first = first if len(first) <= 42 else first[:42].rsplit(" ", 1)[0]
            if re.match(r"(안녕하세요|감사합니다|공유드립니다)", first):
                continue                                                   # 인사만 있는 조각은 보고서에 쓰지 않는다
            line = {"text": first, "refs": [fid], "kind": "fact", "level": 1 if i % 3 == 0 else 2}
            if self.mode == "inline":
                line = {"text": f"{first} [{fid}]", "kind": "fact", "level": line["level"]}
            body_secs[min(i // 3, len(body_secs) - 1)]["lines"].append(line)
        if out["sections"][0]["name"] == "요약" and frags:
            out["sections"][0]["lines"].append({"text": "자료를 종합하면 조치가 끝난 것으로 보임",
                                                "refs": [f[0] for f in frags[:2]], "kind": "infer", "level": 1})
        if len(frags) >= 2:
            body_secs[0]["lines"].append({"text": "자료마다 시각 표기가 다름", "refs": [frags[0][0], frags[1][0]],
                                          "kind": "check", "level": 1})
        body_secs[-1]["lines"].append({"text": "담당자", "refs": [], "kind": "gap", "level": 1})
        if "lie" in self.mode:
            body_secs[0]["lines"].append({"text": "성과 30% 향상", "refs": [], "kind": "fact", "level": 1})
        if "number" in self.mode and frags:
            body_secs[0]["lines"].append({"text": "복구 시간 97분 단축", "refs": [frags[0][0]], "kind": "fact", "level": 1})
        s = json.dumps(out, ensure_ascii=False)
        if self.mode == "length":
            return s[: len(s) // 2], "length"
        if self.mode == "fence":
            return f"다음과 같이 정리했습니다.\n```json\n{s}\n```\n확인 부탁드립니다.", "stop"
        return s, "stop"


if __name__ == "__main__":
    srv = FakeLLM(int(sys.argv[1]) if len(sys.argv) > 1 else 18975)
    print(f"가짜 LLM: {srv.url}  (Ctrl+C 로 끄기)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.close()
