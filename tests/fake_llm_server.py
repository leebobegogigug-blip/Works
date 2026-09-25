# -*- coding: utf-8 -*-
"""테스트용 OpenAI 호환 가짜 LLM 서버.

python fake_llm_server.py PORT MODE
  MODE=native : tools 파라미터로 tool_calls 반환
  MODE=json   : tools 파라미터가 오면 400 (vLLM 자동 도구 미설정 흉내) → 본문 JSON으로 도구 호출
  MODE=qwen   : tools 무시, <tool_call> 텍스트 + <think> 로 응답
"""
import http.server
import json
import re
import sys
from datetime import datetime, timedelta

PORT = int(sys.argv[1])
MODE = sys.argv[2] if len(sys.argv) > 2 else "native"
WD = "월화수목금토일"
STATS = {"requests": 0, "with_tools": 0}


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M")


def next_weekday(d, wd):
    d = d + timedelta(days=1)
    while d.weekday() != wd:
        d += timedelta(days=1)
    return d


def line(e):
    if e.get("all_day"):
        d = datetime.strptime(e["start"], "%Y-%m-%d")
        return f"{d:%m-%d}({WD[d.weekday()]}) 종일 {e['title']}"
    s = datetime.strptime(e["start"], "%Y-%m-%dT%H:%M")
    en = datetime.strptime(e["end"], "%Y-%m-%dT%H:%M")
    loc = f" @{e['location']}" if e.get("location") else ""
    return f"{s:%m-%d}({WD[s.weekday()]}) {s:%H:%M}–{en:%H:%M} {e['title']}{loc}"


def plan(messages):
    last = messages[-1]
    users = [m for m in messages if m["role"] == "user" and not str(m["content"]).startswith("[도구 결과")]
    utext = re.sub(r"^\[알림\].*?\n\n", "", users[-1]["content"] if users else "", flags=re.S)
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    is_result = last["role"] == "tool" or str(last["content"]).startswith("[도구 결과")
    if is_result:
        body = last["content"]
        if last["role"] != "tool":
            body = body.split("\n", 1)[1].split("\n\n이 결과로")[0]
        data = json.loads(body)
        if "error" in data:
            return ("text", "처리하지 못했습니다: " + data["error"])
        if "proposal_id" in data:
            if data.get("conflicts"):
                return ("text", "겹치는 일정이 있습니다 → " + ", ".join(data["conflicts"]) + "\n그래도 괜찮으면 확정을 눌러주세요.")
            return ("text", "제안했습니다. 확정을 눌러주세요.")
        if "events" in data:
            evs = data["events"]
            if "옮겨" in utext and evs:
                target = next((e for e in evs if e["title"][:2] in utext), evs[0])
                s = datetime.strptime(target["start"], "%Y-%m-%dT%H:%M") + timedelta(hours=1)
                return ("tool", "propose_update", {"event_id": target["id"], "start": iso(s)})
            if "남은" in utext:
                evs = [e for e in evs if e["end"] > iso(now)]
            return ("text", "\n".join(line(e) for e in evs) if evs else "일정이 없습니다.")
        if "slots" in data:
            return ("text", "1시간 비는 시간:\n" + "\n".join(s["label"] for s in data["slots"][:4]))
        if "saved" in data:
            return ("text", f"기억했습니다 · {data['id']}" if data["saved"] else "이미 있는 규칙입니다.")
        return ("text", "처리했습니다.")
    if "앞으로" in utext or "기억해" in utext:
        rule = re.sub(r"\s*(기억해|학습해)[.!]*\s*$", "", utext.replace("앞으로", "")).strip()
        return ("tool", "remember_rule", {"rule": rule})
    if "잡아" in utext:
        day = next_weekday(today, 0) if "월요일" in utext else today + timedelta(days=1)
        hour = 15 if "3시" in utext else 10
        return ("tool", "propose_create", {
            "title": "김과장 미팅" if "김과장" in utext else "기획 회의",
            "start": iso(day.replace(hour=hour)), "location": "3A" if "3A" in utext else ""})
    if "빈 시간" in utext or "비는 시간" in utext:
        return ("tool", "find_free_slots", {"start": iso(now), "end": iso(today + timedelta(days=7)), "duration_minutes": 60})
    if "옮겨" in utext or "일정" in utext:
        s, e = today, today + timedelta(days=1)
        if "내일" in utext:
            s, e = today + timedelta(days=1), today + timedelta(days=2)
        if "이번 주" in utext:
            e = today + timedelta(days=7 - today.weekday())
        return ("tool", "list_events", {"start": iso(s), "end": iso(e)})
    return ("text", "네, 말씀하세요.")


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send_json(self, code, obj):
        out = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        self.send_json(200, STATS)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(n).decode("utf-8"))
        STATS["requests"] += 1
        if payload.get("tools"):
            STATS["with_tools"] += 1
        system = payload["messages"][0]["content"] if payload["messages"][0]["role"] == "system" else ""
        STATS["rules_in_prompt"] = "[학습된 규칙]" in system
        STATS["last_rules"] = system.split("[학습된 규칙]")[-1].strip()[:300] if STATS["rules_in_prompt"] else ""
        if MODE == "json" and payload.get("tools"):
            return self.send_json(400, {"error": {"message": '"auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser to be set'}})
        kind, *rest = plan(payload["messages"])
        msg = {"role": "assistant", "content": None}
        if kind == "text":
            msg["content"] = ("<think>사용자 의도 파악…</think>\n" if MODE == "qwen" else "") + rest[0]
        elif MODE == "native":
            msg["tool_calls"] = [{"id": f"call_{STATS['requests']}", "type": "function",
                                  "function": {"name": rest[0], "arguments": json.dumps(rest[1], ensure_ascii=False)}}]
        elif MODE == "json":
            msg["content"] = json.dumps({"tool": rest[0], "args": rest[1]}, ensure_ascii=False)
        else:
            msg["content"] = "<think>도구가 필요함</think>\n<tool_call>\n" + json.dumps(
                {"name": rest[0], "arguments": rest[1]}, ensure_ascii=False) + "\n</tool_call>"
        self.send_json(200, {"id": "x", "object": "chat.completion", "model": payload.get("model"),
                             "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}]})


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
