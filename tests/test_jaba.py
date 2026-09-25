# -*- coding: utf-8 -*-
"""jaba 단위·통합 테스트 (표준 라이브러리 unittest)."""
import bisect
import contextlib
import io
import json
import os
import re
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
import urllib.error
import urllib.request
import zlib
from datetime import datetime, timedelta, timezone

if hasattr(time, "tzset"):  # POSIX: 한국 시간 기준으로 고정 (Windows 는 PC 시간대 그대로)
    os.environ["TZ"] = "Asia/Seoul"
    time.tzset()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import jaba  # noqa: E402
from jaba import Event, LLMReply, ToolCall  # noqa: E402


def cfg_for(db_path, **over):
    cfg = jaba.deep_merge(jaba.DEFAULT_CONFIG, {"calendar": {"backend": "local", "local_db": db_path},
                                                "llm": {"base_url": "http://x/v1", "model": "m"},
                                                "learn_file": os.path.join(os.path.dirname(db_path), "rules.json"),
                                                "alerts": {"windows_toast": False}})  # 테스트 중 진짜 윈도우 알림 금지
    cfg = jaba.deep_merge(cfg, over)
    jaba.validate_config(cfg)
    return cfg


class ScriptLLM:
    """Agent 테스트용 가짜 LLM: 스크립트(함수 목록)를 차례로 실행."""

    def __init__(self, steps, mode="native"):
        self.steps = list(steps)
        self.mode = "auto"
        self.active_mode = mode
        self.ready = True
        self.last_ok = None
        self.last_error = ""
        self.model = "fake"
        self.base_url = "http://fake/v1"
        self.calls = []

    def complete(self, messages, use_tools=True, allow_switch=False):
        self.calls.append([dict(m) for m in messages])
        if not self.steps:
            raise AssertionError("LLM이 예상보다 많이 호출됨")
        step = self.steps.pop(0)
        out = step(messages, self) if callable(step) else step
        self.last_ok = True
        return out


def tc(name, **args):
    return LLMReply(text="", tool_calls=[ToolCall(id="c_" + name, name=name, args=args)])


def say(text):
    return LLMReply(text=text, tool_calls=[])


def next_weekday(d, wd):
    d = d + timedelta(days=1)
    while d.weekday() != wd:
        d += timedelta(days=1)
    return d


# ───────────────────────────────────────────── 날짜 유틸

class TestDates(unittest.TestCase):
    def test_parse_variants(self):
        p = jaba.parse_dt
        self.assertEqual(p("2026-09-25T15:00"), datetime(2026, 9, 25, 15, 0))
        self.assertEqual(p("2026-09-25 15:00"), datetime(2026, 9, 25, 15, 0))
        self.assertEqual(p("2026/9/5 9:05"), datetime(2026, 9, 5, 9, 5))
        self.assertEqual(p("2026.09.25. 15:00"), datetime(2026, 9, 25, 15, 0))
        self.assertEqual(p("2026-09-25"), datetime(2026, 9, 25))
        self.assertEqual(p("2026-09-25T15:00:30.123"), datetime(2026, 9, 25, 15, 0, 30))
        self.assertEqual(p("2026-09-25T24:00"), datetime(2026, 9, 26, 0, 0))

    def test_parse_timezones(self):
        def local(aware):  # 시간대 붙은 시각 → 이 PC 로컬 시각 (어느 시간대에서 돌려도 통과)
            return aware.astimezone().replace(tzinfo=None)
        utc6 = datetime(2026, 9, 25, 6, 0, tzinfo=timezone.utc)
        kst15 = datetime(2026, 9, 25, 15, 0, tzinfo=timezone(timedelta(hours=9)))
        self.assertEqual(jaba.parse_dt("2026-09-25T06:00:00Z"), local(utc6))
        self.assertEqual(jaba.parse_dt("2026-09-25T15:00+09:00"), local(kst15))
        self.assertEqual(jaba.parse_dt("2026-09-25T15:00+0900"), local(kst15))
        self.assertEqual(jaba.parse_dt(utc6), local(utc6))

    def test_parse_errors(self):
        for bad in ("내일 3시", "2026-13-01", "", None, "15:00"):
            with self.assertRaises(ValueError):
                jaba.parse_dt(bad)

    def test_format(self):
        s, e = datetime(2026, 9, 28, 15), datetime(2026, 9, 28, 16)
        self.assertEqual(jaba.fmt_range(s, e), "09-28(월) 15:00–16:00")
        self.assertEqual(jaba.fmt_range(datetime(2026, 9, 28), datetime(2026, 9, 29), True), "09-28(월) 종일")
        self.assertEqual(jaba.fmt_range(datetime(2026, 9, 28), datetime(2026, 9, 30), True), "09-28(월)~09-29(화) 종일")
        self.assertEqual(jaba.fmt_range(datetime(2026, 9, 28, 23), datetime(2026, 9, 29)), "09-28(월) 23:00–24:00")
        self.assertIn("–", jaba.fmt_range(datetime(2026, 9, 28, 22), datetime(2026, 9, 29, 2)))

    def test_ceil(self):
        self.assertEqual(jaba.ceil_minutes(datetime(2026, 9, 25, 10, 47)), datetime(2026, 9, 25, 11, 0))
        self.assertEqual(jaba.ceil_minutes(datetime(2026, 9, 25, 10, 30)), datetime(2026, 9, 25, 10, 30))
        self.assertEqual(jaba.ceil_minutes(datetime(2026, 9, 25, 10, 30, 5)), datetime(2026, 9, 25, 11, 0))
        self.assertEqual(jaba.ceil_minutes(datetime(2026, 9, 25, 23, 50)), datetime(2026, 9, 26, 0, 0))


class TestConfig(unittest.TestCase):
    def test_create_and_merge(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            cfg, created = jaba.load_config(path)
            self.assertTrue(created and os.path.exists(path))
            self.assertEqual(cfg["calendar"]["backend"], "local")
            self.assertEqual(cfg["theme"], "dark")
            with open(path, "w", encoding="utf-8-sig") as f:  # 메모장 BOM 저장 대응
                json.dump({"llm": {"model": "사내모델"}, "work_hours": {"start": "08:30"}}, f, ensure_ascii=False)
            cfg, created = jaba.load_config(path)
            self.assertFalse(created)
            self.assertEqual(cfg["llm"]["model"], "사내모델")
            self.assertEqual(cfg["work_hours"]["start"], "08:30")
            self.assertEqual(cfg["work_hours"]["end"], "18:00")

    def test_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{ broken json")
            with self.assertRaises(jaba.ConfigError):
                jaba.load_config(path)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"work_hours": {"start": "18:00", "end": "09:00"}}, f)
            with self.assertRaises(jaba.ConfigError):
                jaba.load_config(path)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"calendar": {"backend": "google"}}, f)
            with self.assertRaises(jaba.ConfigError):
                jaba.load_config(path)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"theme": "neon"}, f)
            with self.assertRaises(jaba.ConfigError):
                jaba.load_config(path)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"theme": " System "}, f)
            self.assertEqual(jaba.load_config(path)[0]["theme"], "system")

    def test_env_override(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["JABA_API_KEY"] = "secret-from-env"
            try:
                cfg, _ = jaba.load_config(os.path.join(d, "config.json"))
                self.assertEqual(cfg["llm"]["api_key"], "secret-from-env")
            finally:
                del os.environ["JABA_API_KEY"]


class TestFreeSlots(unittest.TestCase):
    def ev(self, s, e, busy=True):
        return Event(id=s, title="x", start=jaba.parse_dt(s), end=jaba.parse_dt(e), busy=busy)

    def test_gaps(self):
        evs = [self.ev("2026-09-25T10:00", "2026-09-25T11:00"),
               self.ev("2026-09-25T13:00", "2026-09-25T14:30"),
               self.ev("2026-09-25T15:00", "2026-09-25T15:30", busy=False)]
        slots = jaba.free_slots(evs, datetime(2026, 9, 25, 9), datetime(2026, 9, 25, 18), 60,
                                jaba.parse_hhmm("09:00"), jaba.parse_hhmm("18:00"), [0, 1, 2, 3, 4])
        self.assertEqual([(a.strftime("%H:%M"), b.strftime("%H:%M")) for a, b in slots],
                         [("09:00", "10:00"), ("11:00", "13:00"), ("14:30", "18:00")])

    def test_weekend_and_rounding(self):
        # 금 16:47 시작 → 17:00 부터, 주말 건너뛰고 월요일
        slots = jaba.free_slots([], datetime(2026, 9, 25, 16, 47), datetime(2026, 9, 28, 12), 45,
                                jaba.parse_hhmm("09:00"), jaba.parse_hhmm("18:00"), [0, 1, 2, 3, 4])
        self.assertEqual(slots[0], (datetime(2026, 9, 25, 17, 0), datetime(2026, 9, 25, 18, 0)))
        self.assertEqual(slots[1], (datetime(2026, 9, 28, 9, 0), datetime(2026, 9, 28, 12, 0)))
        self.assertEqual(len(slots), 2)

    def test_overlapping_busy(self):
        evs = [self.ev("2026-09-25T09:00", "2026-09-25T12:00"),
               self.ev("2026-09-25T10:00", "2026-09-25T11:00"),
               self.ev("2026-09-25T11:30", "2026-09-25T17:40")]
        slots = jaba.free_slots(evs, datetime(2026, 9, 25, 9), datetime(2026, 9, 25, 18), 30,
                                jaba.parse_hhmm("09:00"), jaba.parse_hhmm("18:00"), [4])
        self.assertEqual(slots, [])


# ───────────────────────────────────────────── 로컬 캘린더

class TestLocalCalendar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cal = jaba.LocalCalendar(os.path.join(self.tmp.name, "t.db"))

    def tearDown(self):
        self.cal.db.close()
        self.tmp.cleanup()

    def test_crud(self):
        e = self.cal.create_event("주간회의", datetime(2026, 9, 28, 10), datetime(2026, 9, 28, 11), "3A", "메모")
        self.assertTrue(e.id.startswith("L"))
        self.assertEqual((e.title, e.location, e.notes, e.busy), ("주간회의", "3A", "메모", True))
        day = self.cal.list_events(datetime(2026, 9, 28), datetime(2026, 9, 29))
        self.assertEqual([x.title for x in day], ["주간회의"])
        self.assertEqual(self.cal.list_events(datetime(2026, 9, 28, 11), datetime(2026, 9, 28, 12)), [])
        u = self.cal.update_event(e.id, {"start": datetime(2026, 9, 28, 14), "end": datetime(2026, 9, 28, 15)})
        self.assertEqual(u.start, datetime(2026, 9, 28, 14))
        self.assertEqual(u.title, "주간회의")
        self.cal.delete_event(e.id)
        with self.assertRaises(KeyError):
            self.cal.get_event(e.id)
        with self.assertRaises(KeyError):
            self.cal.delete_event(e.id)

    def test_all_day_not_busy(self):
        e = self.cal.create_event("창립기념일", datetime(2026, 10, 1), datetime(2026, 10, 2), all_day=True)
        self.assertTrue(e.all_day)
        self.assertFalse(e.busy)


# ───────────────────────────────────────────── 에이전트

class AgentBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = cfg_for(os.path.join(self.tmp.name, "a.db"))
        self.cal = jaba.CalendarService(self.cfg)
        self.assertTrue(self.cal.ok, self.cal.error)
        self.day = next_weekday(jaba.start_of_day(datetime.now()), 0)  # 다음 월요일

    def tearDown(self):
        self.cal.close()  # Windows 는 열린 DB 파일이 있으면 임시 폴더를 못 지운다
        self.tmp.cleanup()

    def agent(self, steps, mode="native"):
        self.llm = ScriptLLM(steps, mode)
        return jaba.Agent(self.cfg, self.cal, self.llm)

    def iso(self, h, m=0, day=None):
        d = day or self.day
        return jaba.fmt_iso(d.replace(hour=h, minute=m))


class TestAgentNative(AgentBase):
    def test_create_confirm_and_notice(self):
        ag = self.agent([
            tc("propose_create", title="김과장 미팅", start=self.iso(15), location="3A"),
            say("월요일 15:00 김과장 미팅을 제안했습니다. 확정을 눌러주세요."),
            lambda msgs, llm: say("네"),
        ])
        r = ag.chat("월요일 3시 김과장 미팅 잡아줘 3A에서")
        self.assertEqual(len(r["proposals"]), 1)
        p = r["proposals"][0]
        self.assertEqual((p["id"], p["kind"], p["status"]), ("p1", "create", "pending"))
        self.assertEqual(p["rows"][1][1], jaba.fmt_range(self.day.replace(hour=15), self.day.replace(hour=16)))
        self.assertEqual(r["activity"][0]["tool"], "propose_create")
        self.assertEqual(self.cal.list_events(self.day, self.day + timedelta(days=1)), [])  # 확정 전엔 없음
        # 두 번째 LLM 호출 직전 메시지: assistant(tool_calls) + tool 결과
        second = self.llm.calls[1]
        self.assertEqual(second[-2]["role"], "assistant")
        self.assertEqual(second[-2]["tool_calls"][0]["function"]["name"], "propose_create")
        self.assertEqual(second[-1]["role"], "tool")
        self.assertIn("pending_user_confirmation", second[-1]["content"])
        done = ag.confirm("p1")
        self.assertEqual(done["status"], "done")
        evs = self.cal.list_events(self.day, self.day + timedelta(days=1))
        self.assertEqual([(e.title, e.location, e.end - e.start) for e in evs], [("김과장 미팅", "3A", timedelta(hours=1))])
        self.assertEqual(ag.confirm("p1")["status"], "done")  # 두 번 눌러도 한 번만
        self.assertEqual(len(self.cal.list_events(self.day, self.day + timedelta(days=1))), 1)
        ag.chat("고마워")
        last_user = self.llm.calls[-1][-1]
        self.assertTrue(last_user["content"].startswith("[알림] p1 확정 → 등록됨"))
        self.assertEqual(ag.notices, [])

    def test_quick_yes_no(self):
        ag = self.agent([tc("propose_create", title="A", start=self.iso(10)), say("확정해 주세요"),
                         tc("propose_create", title="B", start=self.iso(11)), say("확정해 주세요")])
        ag.chat("A 잡아")
        r = ag.chat("ㅇㅇ")  # LLM 호출 없이 확정
        self.assertEqual(r["reply"], "확정했습니다.")
        self.assertEqual(r["updated"][0]["status"], "done")
        self.assertEqual(len(self.llm.calls), 2)
        ag.chat("B 잡아")
        r = ag.chat("취소")
        self.assertEqual(r["updated"][0]["status"], "cancelled")
        titles = [e.title for e in self.cal.list_events(self.day, self.day + timedelta(days=1))]
        self.assertEqual(titles, ["A"])

    def test_yes_with_two_pending_goes_to_llm(self):
        ag = self.agent([
            LLMReply(text="", tool_calls=[
                ToolCall(id="1", name="propose_create", args={"title": "A", "start": self.iso(10)}),
                ToolCall(id="2", name="propose_create", args={"title": "B", "start": self.iso(13)})]),
            say("둘 다 제안했습니다"), say("어느 쪽을 확정할까요?")])
        r = ag.chat("A랑 B 잡아")
        self.assertEqual([p["id"] for p in r["proposals"]], ["p1", "p2"])
        r = ag.chat("응")
        self.assertEqual(r["reply"], "어느 쪽을 확정할까요?")

    def test_conflict_and_warnings(self):
        self.cal.create_event(title="분기 계획", start=self.day.replace(hour=14, minute=30),
                              end=self.day.replace(hour=15, minute=30))
        sat = next_weekday(self.day, 5)
        ag = self.agent([tc("propose_create", title="김과장 미팅", start=self.iso(15)), say("겹칩니다"),
                         tc("propose_create", title="주말 약속", start=self.iso(15, day=sat)), say("ok"),
                         tc("propose_create", title="야근", start=self.iso(19)), say("ok")])
        r = ag.chat("월요일 3시 김과장")
        self.assertEqual(len(r["proposals"][0]["conflicts"]), 1)
        self.assertIn("분기 계획", r["proposals"][0]["conflicts"][0])
        tool_msg = self.llm.calls[1][-1]["content"]
        self.assertIn("conflicts", tool_msg)
        self.assertIn("업무일이 아닙니다", ag.chat("토요일")["proposals"][0]["warnings"])
        self.assertIn("업무시간 밖입니다", ag.chat("야근")["proposals"][0]["warnings"])

    def test_update_via_alias_keeps_duration(self):
        self.cal.create_event(title="코드리뷰", start=self.day.replace(hour=16), end=self.day.replace(hour=17, minute=30))

        def propose(msgs, llm):
            data = json.loads(msgs[-1]["content"])
            eid = data["events"][0]["id"]
            self.assertEqual(eid, "e1")
            return tc("propose_update", event_id=eid, start=self.iso(17))

        ag = self.agent([tc("list_events", start=self.iso(0), end=self.iso(23, 59)), propose, say("변경 제안")])
        r = ag.chat("코드리뷰 5시로 옮겨줘")
        p = r["proposals"][0]
        self.assertEqual(p["kind"], "update")
        self.assertTrue(p["rows"][1][2])  # 시간 행 변경 표시
        self.assertIn("→", p["rows"][1][1])
        self.assertEqual(ag.confirm(p["id"])["status"], "done")
        ev = self.cal.list_events(self.day, self.day + timedelta(days=1))[0]
        self.assertEqual((ev.start.hour, ev.end - ev.start), (17, timedelta(minutes=90)))

    def test_delete_and_forget(self):
        self.cal.create_event(title="취소될 회의", start=self.day.replace(hour=9), end=self.day.replace(hour=10))
        ag = self.agent([tc("list_events", start=self.iso(0), end=self.iso(23)),
                         tc("propose_delete", event_id="e1"), say("삭제 제안"),
                         tc("propose_delete", event_id="e1"), say("없음")])
        r = ag.chat("그 회의 지워")
        self.assertEqual(r["proposals"][0]["kind"], "delete")
        self.assertEqual(ag.confirm("p1")["status"], "done")
        self.assertEqual(self.cal.list_events(self.day, self.day + timedelta(days=1)), [])
        r = ag.chat("다시 지워")  # 지운 별칭은 잊힘 → 오류가 도구 결과로 전달
        self.assertFalse(r["activity"][0]["ok"])
        self.assertIn("알 수 없는 id", self.llm.calls[-1][-1]["content"])

    def test_locked_event_refused(self):
        ag = self.agent([tc("propose_delete", event_id="e1"), say("반복 일정은 못 지웁니다")])
        ag.alias["e1"] = "X|2026"
        ag.rev["X|2026"] = "e1"
        ag.snap["e1"] = Event(id="X|2026", title="매주 스탠드업", start=self.day.replace(hour=9),
                              end=self.day.replace(hour=9, minute=15), recurring=True, editable=False,
                              lock_reason="반복 일정")
        r = ag.chat("스탠드업 지워")
        self.assertEqual(r["proposals"], [])
        self.assertFalse(r["activity"][0]["ok"])
        self.assertIn("반복 일정", r["activity"][0]["text"])

    def test_bad_args_and_unknown_tool(self):
        ag = self.agent([
            LLMReply(text="", tool_calls=[ToolCall(id="1", name="list_events", args={}, error="arguments JSON 해석 실패"),
                                          ToolCall(id="2", name="rm_rf", args={})]),
            tc("propose_create", title="", start=self.iso(9)),
            tc("propose_create", title="역순", start=self.iso(10), end=self.iso(9)),
            say("다시 알려주세요")])
        r = ag.chat("??")
        self.assertEqual([a["ok"] for a in r["activity"]], [False, False, False, False])
        self.assertEqual(r["reply"], "다시 알려주세요")

    def test_all_day_inclusive_end(self):
        ag = self.agent([tc("propose_create", title="워크숍", start=self.iso(0), end=jaba.fmt_iso(self.day + timedelta(days=1)),
                            all_day=True), say("ok")])
        p = ag.chat("월화 워크숍")["proposals"][0]
        self.assertIn("종일", p["rows"][1][1])
        ag.confirm(p["id"])
        ev = self.cal.list_events(self.day, self.day + timedelta(days=3))[0]
        self.assertEqual((ev.start, ev.end, ev.all_day), (self.day, self.day + timedelta(days=2), True))

    def test_all_day_shown_as_dates_to_llm(self):
        self.cal.create_event(title="워크숍", start=self.day, end=self.day + timedelta(days=2), all_day=True)
        self.cal.create_event(title="점심", start=self.day.replace(hour=12), end=self.day.replace(hour=13))
        ag = self.agent([tc("list_events", start=self.iso(0), end=jaba.fmt_iso(self.day + timedelta(days=3))), say("ok")])
        ag.chat("일정")
        evs = json.loads(self.llm.calls[1][-1]["content"])["events"]
        ws = next(e for e in evs if e["title"] == "워크숍")
        self.assertEqual((ws["start"], ws["end"], ws["all_day"]),
                         (self.day.date().isoformat(), (self.day + timedelta(days=1)).date().isoformat(), True))
        lunch = next(e for e in evs if e["title"] == "점심")
        self.assertEqual(lunch["start"], self.iso(12))
        self.assertNotIn("all_day", lunch)

    def test_step_limit(self):
        ag = self.agent([tc("list_events", start=self.iso(0), end=self.iso(23))] * jaba.Agent.MAX_STEPS)
        r = ag.chat("무한루프")
        self.assertIn("너무 길어져", r["reply"])

    def test_history_trim(self):
        ag = self.agent([say(str(i)) for i in range(10)])
        for i in range(10):
            ag.chat(f"q{i}")
        self.assertEqual(len(ag.turns), jaba.Agent.KEEP_TURNS)
        self.assertEqual(ag.turns[0][0]["content"], "q4")

    def test_free_slots_tool(self):
        ag = self.agent([tc("find_free_slots", start=self.iso(9), end=self.iso(18), duration_minutes=60), say("여기요")])
        r = ag.chat("월요일 빈 시간")
        res = json.loads(self.llm.calls[1][-1]["content"])
        self.assertEqual(res["slots"][0]["start"], self.iso(9))
        self.assertIn("후보", r["activity"][0]["text"])

    def test_system_prompt_calendar_table(self):
        now = datetime(2026, 9, 25, 13, 5)
        sp = jaba.build_system_prompt(self.cfg, "native", now)
        self.assertIn("2026-09-25(금) 오늘", sp)
        self.assertIn("2026-09-26(토) 내일", sp)
        self.assertIn("이번 주: 2026-09-21(월) ~ 2026-09-27(일)", sp)
        self.assertIn("다음 주: 2026-09-28(월) ~ 2026-10-04(일)", sp)
        self.assertNotIn("[도구 사용법]", sp)
        self.assertIn("[도구 사용법]", jaba.build_system_prompt(self.cfg, "json", now))
        self.assertIn("propose_update(event_id, title?, start?, end?, location?)", jaba.tools_as_text())

    def test_confirm_not_blocked_by_llm_wait(self):
        """LLM 을 기다리는 동안에도 확정 버튼 · /api/state 가 바로 응답하고, 그 사이 확정한 알림은 다음 턴에 전달된다."""
        entered, release = threading.Event(), threading.Event()

        def slow(messages, llm):
            entered.set()
            release.wait(5)
            return say("다른 답")

        ag = self.agent([tc("propose_create", title="A", start=self.iso(10)), say("확정해 주세요"),
                         slow, say("네")])
        ag.chat("A 잡아")
        th = threading.Thread(target=ag.chat, args=("딴 얘기",))
        th.start()
        try:
            self.assertTrue(entered.wait(5))
            t0 = time.time()
            self.assertEqual([p["id"] for p in ag.pending()], ["p1"])
            self.assertEqual(ag.confirm("p1")["status"], "done")
            self.assertLess(time.time() - t0, 1.0)
        finally:
            release.set()
            th.join(5)
        self.assertEqual(len(ag.notices), 1)  # 기다리던 턴이 끝나도 지워지지 않음
        ag.chat("고마워")
        self.assertTrue(self.llm.calls[-1][-1]["content"].startswith("[알림] p1 확정 → 등록됨"))
        self.assertEqual(ag.notices, [])

    def test_quick_reply_only_targets_previous_turn(self):
        """제안 뒤에 다른 얘기를 했으면 '네'·'아니'는 그 대화의 답이다 (예전 카드를 확정/취소하지 않음)."""
        ag = self.agent([tc("propose_create", title="A", start=self.iso(10)), say("확정해 주세요"),
                         say("3시로 옮길까요?"), say("알겠습니다"), say("네")])
        ag.chat("A 잡아")
        ag.chat("그런데 다른 회의는 어때?")
        r = ag.chat("아니")
        self.assertEqual(r["updated"], [])
        r = ag.chat("네")
        self.assertEqual(r["updated"], [])
        self.assertEqual([p["id"] for p in ag.pending()], ["p1"])  # 카드는 그대로, 버튼으로 확정 가능
        self.assertEqual(len(self.llm.calls), 5)

    def test_confirm_refuses_if_event_changed_meanwhile(self):
        ev = self.cal.create_event(title="원래", start=self.day.replace(hour=10), end=self.day.replace(hour=11))
        ag = self.agent([tc("list_events", start=self.iso(0), end=self.iso(23)),
                         tc("propose_update", event_id="e1", start=self.iso(14)), say("확정해 주세요")])
        ag.chat("원래 일정 2시로")
        self.cal.update_event(ev.id, {"title": "누가 바꿈"})  # Outlook 에서 직접 바꾼 상황
        r = ag.confirm("p1")
        self.assertEqual(r["status"], "failed")
        self.assertIn("바뀌었습니다", r["error"])
        self.assertEqual(self.cal.get_event(ev.id).start, self.day.replace(hour=10))

    def test_update_all_day_end(self):
        ev = self.cal.create_event(title="출장", start=self.day, end=self.day + timedelta(days=1), all_day=True)
        ag = self.agent([tc("list_events", start=self.iso(0), end=self.iso(23)),
                         tc("propose_update", event_id="e1", end=(self.day + timedelta(days=2)).date().isoformat()),
                         say("확정해 주세요")])
        ag.chat("출장 이틀 더")
        self.assertEqual(ag.confirm("p1")["status"], "done")
        self.assertEqual(self.cal.get_event(ev.id).end, self.day + timedelta(days=3))

    def test_finished_proposals_are_pruned(self):
        ag = self.agent([])
        for i in range(250):
            p = ag._new_proposal("rule", {"text": f"r{i}"})
            p.status = "cancelled"
        ag._prune_proposals()
        self.assertEqual(len(ag.proposals), 200)
        self.assertIn("p250", ag.proposals)


class TestAgentJsonMode(AgentBase):
    def test_json_flow(self):
        raw = json.dumps({"tool": "propose_create", "args": {"title": "점심", "start": self.iso(12)}}, ensure_ascii=False)

        def first(msgs, llm):
            self.assertIn("[도구 사용법]", msgs[0]["content"])
            return LLMReply(text="", tool_calls=jaba.extract_text_tool_calls(raw), raw_text=raw, via_text=True)

        ag = self.agent([first, say("확정을 눌러주세요")], mode="json")
        r = ag.chat("월요일 점심 잡아")
        self.assertEqual(r["proposals"][0]["rows"][0][1], "점심")
        second = self.llm.calls[1]
        self.assertEqual(second[-2], {"role": "assistant", "content": raw})
        self.assertEqual(second[-1]["role"], "user")
        self.assertTrue(second[-1]["content"].startswith("[도구 결과: propose_create]"))

    def test_history_filters_native_tool_messages(self):
        ag = self.agent([tc("list_events", start=self.iso(0), end=self.iso(23)), say("없음"), say("json 답")])
        ag.chat("일정")
        self.llm.active_mode = "json"
        ag.chat("다시")
        roles = [m["role"] for m in self.llm.calls[-1]]
        self.assertNotIn("tool", roles)
        self.assertFalse(any(m.get("tool_calls") for m in self.llm.calls[-1]))

    def test_mode_switch_retry(self):
        def reject(msgs, llm):
            llm.active_mode = "json"
            raise jaba.ModeSwitched()

        ag = self.agent([reject, say("json 모드 응답")])
        r = ag.chat("안녕")
        self.assertEqual(r["reply"], "json 모드 응답")
        self.assertIn("[도구 사용법]", self.llm.calls[1][0]["content"])


# ───────────────────────────────────────────── LLM 클라이언트

class FakePostClient(jaba.LLMClient):
    def __init__(self, responses, **llm):
        cfg = jaba.deep_merge(jaba.DEFAULT_CONFIG, {"llm": dict({"base_url": "http://h/v1", "model": "m"}, **llm)})
        super().__init__(cfg)
        self.responses = list(responses)
        self.payloads = []

    def _post(self, payload):
        self.payloads.append(payload)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def chat_resp(content=None, tool_calls=None):
    msg = {"role": "assistant", "content": content}
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
    return {"choices": [{"index": 0, "message": msg, "finish_reason": "stop"}]}


class TestLLMClient(unittest.TestCase):
    def test_endpoint(self):
        c = FakePostClient([])
        self.assertEqual(c.endpoint(), "http://h/v1/chat/completions")
        c.base_url = "http://h/v1/chat/completions/"
        self.assertEqual(c.endpoint(), "http://h/v1/chat/completions")

    def test_not_ready(self):
        c = FakePostClient([], model="")
        with self.assertRaises(jaba.LLMError):
            c.complete([{"role": "user", "content": "x"}])

    def test_native_tool_calls(self):
        c = FakePostClient([chat_resp(None, [
            {"id": "a", "type": "function", "function": {"name": "list_events", "arguments": '{"start":"2026-09-25T00:00","end":"2026-09-26T00:00"}'}},
            {"id": "b", "type": "function", "function": {"name": "find_free_slots", "arguments": {"start": "s", "end": "e", "duration_minutes": 30}}},
            {"id": "c", "type": "function", "function": {"name": "list_events", "arguments": json.dumps(json.dumps({"start": "x", "end": "y"}))}},
        ])])
        r = c.complete([{"role": "user", "content": "x"}])
        self.assertEqual([t.name for t in r.tool_calls], ["list_events", "find_free_slots", "list_events"])
        self.assertEqual(r.tool_calls[0].args["start"], "2026-09-25T00:00")
        self.assertEqual(r.tool_calls[1].args["duration_minutes"], 30)
        self.assertEqual(r.tool_calls[2].args, {"start": "x", "end": "y"})
        self.assertIn("tools", c.payloads[0])
        self.assertTrue(c.last_ok)

    def test_think_and_parts(self):
        c = FakePostClient([chat_resp("<think>음… 계산</think>\n답입니다"),
                            chat_resp([{"type": "text", "text": "조각1 "}, {"type": "text", "text": "조각2"}]),
                            chat_resp("생각만 하다 끝남</think>최종")])
        self.assertEqual(c.complete([]).text, "답입니다")
        self.assertEqual(c.complete([]).text, "조각1 조각2")
        self.assertEqual(c.complete([]).text, "최종")

    def test_text_tool_call_switches_to_json(self):
        c = FakePostClient([chat_resp('<tool_call>\n{"name": "list_events", "arguments": {"start": "2026-09-25T00:00", "end": "2026-09-26T00:00"}}\n</tool_call>')])
        r = c.complete([{"role": "user", "content": "x"}])
        self.assertTrue(r.via_text)
        self.assertEqual(r.tool_calls[0].name, "list_events")
        self.assertEqual(c.active_mode, "json")

    def test_json_mode_parse(self):
        c = FakePostClient([chat_resp('도구 씁니다 ```json\n{"tool": "propose_create", "args": {"title": "회의", "start": "2026-09-28T15:00"}}\n```'),
                            chat_resp('평범한 답 {"a": 1} 입니다')], tool_mode="json")
        r = c.complete([])
        self.assertNotIn("tools", c.payloads[0])
        self.assertEqual((r.tool_calls[0].name, r.tool_calls[0].args["title"]), ("propose_create", "회의"))
        r = c.complete([])
        self.assertEqual(r.tool_calls, [])
        self.assertIn("평범한 답", r.text)

    def test_reject_tools_switch(self):
        body = '{"error":{"message":"\\"auto\\" tool choice requires --enable-auto-tool-choice"}}'
        c = FakePostClient([jaba.LLMError("400", 400, body)])
        with self.assertRaises(jaba.ModeSwitched):
            c.complete([], allow_switch=True)
        self.assertEqual(c.active_mode, "json")
        c2 = FakePostClient([jaba.LLMError("400", 400, body)])
        with self.assertRaises(jaba.LLMError):
            c2.complete([], allow_switch=False)
        self.assertEqual(c2.active_mode, "native")
        self.assertFalse(c2.last_ok)
        c3 = FakePostClient([jaba.LLMError("400", 400, body)], tool_mode="native")
        with self.assertRaises(jaba.LLMError):
            c3.complete([], allow_switch=True)

    def test_real_http_errors(self):
        import http.server

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n))
                if self.headers.get("Authorization") != "Bearer k" or self.headers.get("X-Team") != "t1":
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b'{"error":"bad key"}')
                    return
                if self.path == "/v1/chat/completions" and body["model"] == "m":
                    out = json.dumps(chat_resp("안녕하세요")).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(out)))
                    self.end_headers()
                    self.wfile.write(out)
                else:
                    self.send_response(404)
                    self.end_headers()

        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]
        try:
            ok = jaba.LLMClient(jaba.deep_merge(jaba.DEFAULT_CONFIG, {"llm": {
                "base_url": f"http://127.0.0.1:{port}/v1", "model": "m", "api_key": "k",
                "extra_headers": {"X-Team": "t1"}, "proxy": ""}}))
            self.assertEqual(ok.complete([{"role": "user", "content": "hi"}], use_tools=False).text, "안녕하세요")
            bad = jaba.LLMClient(jaba.deep_merge(jaba.DEFAULT_CONFIG, {"llm": {
                "base_url": f"http://127.0.0.1:{port}/v1", "model": "m", "api_key": "wrong", "proxy": ""}}))
            with self.assertRaises(jaba.LLMError) as cm:
                bad.complete([], use_tools=False)
            self.assertEqual(cm.exception.status, 401)
            down = jaba.LLMClient(jaba.deep_merge(jaba.DEFAULT_CONFIG, {"llm": {
                "base_url": "http://127.0.0.1:1/v1", "model": "m", "proxy": "", "timeout_sec": 2}}))
            with self.assertRaises(jaba.LLMError) as cm:
                down.complete([], use_tools=False)
            self.assertIn("연결할 수 없습니다", str(cm.exception))
        finally:
            srv.shutdown()
            srv.server_close()


# ───────────────────────────────────────────── Outlook (가짜 COM)

class FakeAppt:
    def __init__(self, store, **kw):
        self._store = store
        self.Class = 26
        self.Subject = ""
        self.Start = None
        self.End = None
        self.Location = ""
        self.Body = ""
        self.AllDayEvent = False
        self.IsRecurring = False
        self.MeetingStatus = 0
        self.BusyStatus = 2
        self.EntryID = ""
        self.ReminderSet = False
        self.ReminderMinutesBeforeStart = 15
        self.deleted = False
        for k, v in kw.items():
            setattr(self, k, v)

    def __setattr__(self, key, value):
        if key in ("Start", "End") and isinstance(value, datetime):
            shift = getattr(self, "_store", None) and self._store.shift
            if shift:
                value = value + shift
            # pywin32처럼 UTC tzinfo를 잘못 붙여 돌려준다
            value = value.replace(tzinfo=timezone.utc)
        object.__setattr__(self, key, value)

    def Save(self):
        self._store.save(self)

    def Delete(self):
        self._store.delete(self)


class FakeItems:
    def __init__(self, store, items):
        self.store = store
        self.items = list(items)
        self.IncludeRecurrences = False
        self._i = -1

    def Sort(self, key):
        self.items.sort(key=lambda a: a.Start)

    def Restrict(self, flt):
        self.store.filters.append(flt)
        import re
        m = re.match(r"^\[Start\] < '(.+)' AND \[End\] > '(.+)'$", flt)
        end_s, start_s = m.group(1), m.group(2)
        fmts = {"iso": "%Y-%m-%d %H:%M", "us": "%m/%d/%Y %I:%M %p"}
        for name in self.store.accept:
            try:
                end, start = datetime.strptime(end_s, fmts[name]), datetime.strptime(start_s, fmts[name])
                break
            except ValueError:
                continue
        else:
            raise Exception("잘못된 필터 조건")
        hits = [a for a in self.items if a.Start.replace(tzinfo=None) < end and a.End.replace(tzinfo=None) > start]
        return FakeItems(self.store, sorted(hits, key=lambda a: a.Start))

    def GetFirst(self):
        self._i = 0
        return self.items[0] if self.items else None

    def GetNext(self):
        self._i += 1
        return self.items[self._i] if self._i < len(self.items) else None


class FakeStore:
    def __init__(self):
        self.appts = {}
        self.filters = []
        self.accept = ["iso"]
        self.shift = None
        self.n = 0

    def save(self, a):
        if not a.EntryID:
            self.n += 1
            a.EntryID = "0000000%04dABCDEF" % self.n
        self.appts[a.EntryID] = a

    def delete(self, a):
        self.appts.pop(a.EntryID, None)


class FakeOutlook:
    def __init__(self, store):
        self.store = store
        self.Version = "16.0.0.0"
        folder = types.SimpleNamespace(Name="일정")
        folder_items = property(lambda s: None)  # noqa
        self._folder = folder
        store_ref = store

        class Folder:
            Name = "일정"

            @property
            def Items(self):
                return FakeItems(store_ref, store_ref.appts.values())

        self.folder = Folder()

    def GetNamespace(self, name):
        outer = self

        class NS:
            def GetDefaultFolder(self, n):
                assert n == 9
                return outer.folder

            def GetItemFromID(self, entry):
                if entry not in outer.store.appts:
                    raise Exception("not found")
                return outer.store.appts[entry]

        return NS()

    def CreateItem(self, kind):
        assert kind == 1
        return FakeAppt(self.store)


class TestOutlookFake(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        client = types.ModuleType("win32com.client")
        client.Dispatch = lambda name: FakeOutlook(self.store)
        pkg = types.ModuleType("win32com")
        pkg.client = client
        sys.modules["win32com"] = pkg
        sys.modules["win32com.client"] = client
        self.ol = jaba.OutlookCalendar()
        self.day = datetime(2026, 9, 28)

    def tearDown(self):
        sys.modules.pop("win32com", None)
        sys.modules.pop("win32com.client", None)

    def add(self, title, h1, h2, **kw):
        a = FakeAppt(self.store, Subject=title, **kw)
        a.Start = self.day.replace(hour=h1)
        a.End = self.day.replace(hour=h2)
        a.Save()
        return a

    def test_list_and_locks(self):
        self.add("개인 작업", 9, 10)
        self.add("주간회의", 10, 11, IsRecurring=True)
        self.add("외부 초대", 14, 15, MeetingStatus=3)
        self.add("휴가 아님", 16, 17, BusyStatus=0)
        self.add("다음날", 9, 10)
        self.store.appts[list(self.store.appts)[-1]].Start = datetime(2026, 9, 29, 9)
        self.store.appts[list(self.store.appts)[-1]].End = datetime(2026, 9, 29, 10)
        evs = self.ol.list_events(self.day, self.day + timedelta(days=1))
        self.assertEqual([e.title for e in evs], ["개인 작업", "주간회의", "외부 초대", "휴가 아님"])
        self.assertEqual(evs[0].start, datetime(2026, 9, 28, 9))  # 잘못 붙은 UTC tzinfo 무시
        self.assertIsNone(evs[0].start.tzinfo)
        self.assertTrue(evs[1].id.endswith("|2026-09-28T10:00") and not evs[1].editable)
        self.assertEqual(evs[2].lock_reason, "회의 초대 일정")
        self.assertFalse(evs[3].busy)
        self.assertTrue(evs[0].editable)
        self.assertTrue(any("2026-09-29 00:00" in f for f in self.store.filters))  # ISO 필터 사용

    def test_filter_fallbacks(self):
        self.add("A", 9, 10)
        self.store.accept = ["us"]  # ISO 거부 → US 형식 시도
        self.assertEqual([e.title for e in self.ol.list_events(self.day, self.day + timedelta(days=1))], ["A"])
        self.store.accept = []  # 모든 필터 거부 → 전체 탐색
        self.assertEqual([e.title for e in self.ol.list_events(self.day, self.day + timedelta(days=1))], ["A"])

    def test_create_update_delete(self):
        ev = self.ol.create_event("김과장 미팅", self.day.replace(hour=15), self.day.replace(hour=16), "3A", "안건")
        a = self.store.appts[ev.id]
        self.assertEqual((a.Subject, a.Location, a.Body, a.BusyStatus, a.ReminderSet, a.ReminderMinutesBeforeStart),
                         ("김과장 미팅", "3A", "안건", 2, True, 10))
        self.assertEqual(ev.start, self.day.replace(hour=15))
        u = self.ol.update_event(ev.id, {"start": self.day.replace(hour=16), "end": self.day.replace(hour=17), "title": "김과장 1:1"})
        self.assertEqual((u.title, u.start.hour), ("김과장 1:1", 16))
        self.ol.delete_event(ev.id)
        self.assertNotIn(ev.id, self.store.appts)
        with self.assertRaises(KeyError):
            self.ol.get_event(ev.id)

    def test_locked_refused(self):
        a = self.add("주간회의", 10, 11, IsRecurring=True)
        with self.assertRaises(PermissionError):
            self.ol.delete_event(a.EntryID + "|2026-09-28T10:00")
        b = self.add("초대", 13, 14, MeetingStatus=3)
        with self.assertRaises(PermissionError):
            self.ol.update_event(b.EntryID, {"title": "x"})

    def test_shift_correction(self):
        self.store.shift = timedelta(hours=-9)  # 저장 시 9시간 밀리는 환경 흉내
        ev = self.ol.create_event("보정", self.day.replace(hour=15), self.day.replace(hour=16))
        self.store.shift = None
        self.assertEqual(ev.start, self.day.replace(hour=15))

    def test_all_day(self):
        ev = self.ol.create_event("창립기념일", self.day, self.day + timedelta(days=1), all_day=True)
        a = self.store.appts[ev.id]
        self.assertTrue(a.AllDayEvent)
        self.assertEqual((a.BusyStatus, a.ReminderSet), (0, False))
        self.assertFalse(ev.busy)

    def test_missing_pywin32(self):
        sys.modules["win32com"] = None
        sys.modules["win32com.client"] = None
        with self.assertRaises(RuntimeError) as cm:
            jaba.OutlookCalendar()
        self.assertIn("pip install pywin32", str(cm.exception))


# ───────────────────────────────────────────── 로컬 서버

class TestServer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = cfg_for(os.path.join(self.tmp.name, "s.db"), open_window=False, hotkey="")
        self.app = jaba.App(self.cfg)
        self.day = next_weekday(jaba.start_of_day(datetime.now()), 0)
        start = jaba.fmt_iso(self.day.replace(hour=15))
        self.app.llm = self.app.agent.llm = ScriptLLM([tc("propose_create", title="김과장 미팅", start=start), say("확정해 주세요")])
        self.thread = threading.Thread(target=self.app.serve, args=(0, False), daemon=True)
        self.thread.start()
        for _ in range(100):
            if self.app.port:
                break
            time.sleep(0.02)
        self.base = f"http://127.0.0.1:{self.app.port}"
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        if self.thread.is_alive():
            self.app.httpd.shutdown()
            self.thread.join(3)
        self.app.alerts.stop()
        self.app.cal.close()
        self.tmp.cleanup()

    def req(self, path, body=None, token=True, host=None, ctype="application/json"):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, method="POST" if data is not None else "GET")
        if token:
            r.add_header("X-Jaba-Token", self.app.token)
        if data is not None and ctype:
            r.add_header("Content-Type", ctype)
        if host:
            r.add_header("Host", host)
        try:
            with self.opener.open(r, timeout=10) as resp:
                raw = resp.read().decode()
                return resp.status, (json.loads(raw) if raw.startswith("{") else raw)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")

    def test_negative_content_length(self):
        with socket.create_connection(("127.0.0.1", self.app.port), timeout=5) as c:
            c.sendall((f"POST /api/chat HTTP/1.1\r\nHost: 127.0.0.1:{self.app.port}\r\nX-Jaba-Token: {self.app.token}\r\n"
                       "Content-Type: application/json\r\nContent-Length: -1\r\nConnection: close\r\n\r\n").encode())
            self.assertIn(b" 400 ", c.recv(200))

    def test_flow_and_security(self):
        code, html = self.req("/", token=False)
        self.assertEqual(code, 200)
        self.assertIn(self.app.token, html)
        self.assertNotIn("__BOOT__", html)
        self.assertNotIn("__THEME__", html)
        self.assertIn('<html lang="ko" data-theme="dark">', html)
        self.assertEqual(self.req("/api/ping", token=False), (200, {"app": "jaba", "version": jaba.VERSION}))
        self.assertEqual(self.req("/api/state", token=False)[0], 401)
        self.assertEqual(self.req("/api/state", host="evil.example:80")[0], 403)
        self.assertEqual(self.req("/", token=False, host="attacker.test")[0], 403)
        self.assertEqual(self.req("/api/chat", {"message": "x"}, ctype="text/plain")[0], 415)
        code, st = self.req("/api/state")
        self.assertEqual((code, st["backend"], st["cal_ok"], st["llm_ready"]), (200, "local", True, True))
        code, r = self.req("/api/chat", {"message": "월요일 3시 김과장 미팅 잡아줘"})
        self.assertEqual((code, r["reply"], r["proposals"][0]["id"]), (200, "확정해 주세요", "p1"))
        self.assertEqual(len(self.req("/api/state")[1]["pending"]), 1)
        code, r = self.req("/api/proposals/p1/confirm", {})
        self.assertEqual((code, r["proposal"]["status"]), (200, "done"))
        code, r = self.req("/api/events?date=" + self.day.strftime("%Y-%m-%d"))
        self.assertEqual([e["title"] for e in r["events"]], ["김과장 미팅"])
        self.assertEqual(self.req("/api/proposals/p9/confirm", {})[0], 404)
        code, nx = self.req("/api/next")
        self.assertEqual(code, 200)
        self.assertEqual(nx["next"]["title"], "김과장 미팅")
        self.assertEqual(self.req("/api/reset", {}), (200, {"ok": True}))
        self.assertEqual(self.req("/api/state")[1]["pending"], [])
        self.assertEqual(jaba.find_running(self.app.port), self.base + "/")
        self.assertEqual(self.req("/api/shutdown", {}), (200, {"ok": True}))
        self.thread.join(5)
        self.assertFalse(self.thread.is_alive())

    def test_llm_error_is_reported(self):
        def boom(msgs, llm):
            raise jaba.LLMError("LLM 서버에 연결할 수 없습니다: refused")
        self.app.agent.llm.steps = [boom]
        code, r = self.req("/api/chat", {"message": "안녕"})
        self.assertEqual(code, 200)
        self.assertIn("연결할 수 없습니다", r["error"])
        self.assertEqual(r["reply"], "")


class FakeFn:
    def __init__(self, name, calls, impl=None):
        self.name, self.calls, self.impl = name, calls, impl
        self.argtypes, self.restype = None, None

    def __call__(self, *a):
        if self.argtypes is not None:
            assert len(a) == len(self.argtypes), f"{self.name}: 인자 {len(a)}개 != argtypes {len(self.argtypes)}개"
        self.calls.append(self.name)
        return self.impl(*a) if self.impl else 1


class FakeDLL:
    def __init__(self, calls, impls):
        self._calls, self._impls, self._fns = calls, impls, {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._fns:
            self._fns[name] = FakeFn(name, self._calls, self._impls.get(name))
        return self._fns[name]


class TestWindowsShims(unittest.TestCase):
    """Windows 전용 경로를 가짜 ctypes 로 실행해 파이썬 수준 오류(오타·인자 수)를 잡는다."""

    def setUp(self):
        import ctypes
        self.ctypes = ctypes
        self.saved = {k: getattr(ctypes, k, None) for k in ("WinDLL", "WINFUNCTYPE", "WinError", "get_last_error")}
        self.calls = []
        self.impls = {}
        ctypes.WinDLL = lambda name, use_last_error=False: FakeDLL(self.calls, self.impls)
        ctypes.WINFUNCTYPE = lambda restype, *argtypes: (lambda fn: fn)
        ctypes.WinError = lambda code=None: OSError(code)
        ctypes.get_last_error = lambda: 0

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                if hasattr(self.ctypes, k):
                    delattr(self.ctypes, k)
            else:
                setattr(self.ctypes, k, v)
        jaba.IS_WINDOWS = sys.platform == "win32"

    def test_locale_datetime(self):
        def date_fmt(loc, flags, st, fmt, buf, n, cal):
            self.assertEqual((flags, st._obj.wYear, st._obj.wMonth, st._obj.wDay), (1, 2026, 9, 28))
            buf.value = "2026-09-28"
            return 11

        def time_fmt(loc, flags, st, fmt, buf, n):
            self.assertEqual((flags, st._obj.wHour), (2, 15))
            buf.value = "오후 3:00"
            return 7
        self.impls.update(GetDateFormatEx=date_fmt, GetTimeFormatEx=time_fmt)
        self.assertEqual(jaba._win_locale_datetime(datetime(2026, 9, 28, 15, 0)), "2026-09-28 오후 3:00")

    def test_focus_existing_window(self):
        title = "jaba · 일정 비서"

        def enum(cb, lparam):
            for hwnd in (111, 222):
                if not cb(hwnd, lparam):
                    break
            return 1

        def text(hwnd, buf, n):
            buf.value = "다른 창" if hwnd == 111 else title
            return len(buf.value)
        self.impls.update(EnumWindows=enum, GetWindowTextW=text, GetWindowTextLengthW=lambda h: 20,
                          IsWindowVisible=lambda h: 1, IsIconic=lambda h: 1)
        opened = []
        orig = jaba.open_app_window
        jaba.open_app_window = opened.append
        try:
            jaba.focus_or_open("http://127.0.0.1:8765/")
        finally:
            jaba.open_app_window = orig
        self.assertEqual(opened, [])
        self.assertIn("ShowWindow", self.calls)
        self.assertEqual(self.calls[-1], "SetForegroundWindow")

    def test_focus_opens_when_missing(self):
        self.impls.update(EnumWindows=lambda cb, lp: 1)
        opened = []
        orig = jaba.open_app_window
        jaba.open_app_window = opened.append
        try:
            jaba.focus_or_open("http://127.0.0.1:8765/")
        finally:
            jaba.open_app_window = orig
        self.assertEqual(opened, ["http://127.0.0.1:8765/"])

    def test_hotkey_loop(self):
        fired = threading.Event()
        state = {"n": 0}

        def get_message(msg, hwnd, a, b):
            state["n"] += 1
            if state["n"] == 1:
                msg._obj.message = 0x0312
                return 1
            return 0
        self.impls.update(RegisterHotKey=lambda h, i, m, vk: 1, GetMessageW=get_message)
        jaba.IS_WINDOWS = True
        jaba.start_hotkey("ctrl+alt+j", fired.set)
        self.assertTrue(fired.wait(3))

    def test_launcher(self):
        with tempfile.TemporaryDirectory() as d:
            orig = jaba.BASE_DIR
            jaba.BASE_DIR = d
            try:
                jaba.ensure_launcher()
                with open(os.path.join(d, "jaba.bat"), "rb") as f:
                    data = f.read().decode("ascii")
            finally:
                jaba.BASE_DIR = orig
        self.assertIn('start "jaba" /min', data)
        self.assertIn('"%~dp0jaba.py"', data)
        self.assertTrue(data.endswith("\r\n"))


# ───────────────────────────────────────────── v0.2: 학습 · 알림

class TestRuleBook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "rules.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_crud_and_persist(self):
        rb = jaba.RuleBook(self.path)
        r1, c1 = rb.add("  스크럼은   항상 15분 ")
        self.assertEqual((r1["id"], r1["text"], c1), ("r1", "스크럼은 항상 15분", True))
        self.assertEqual(rb.add("스크럼은 항상 15분")[1], False)  # 중복은 새로 안 만듦
        r2, _ = rb.add("금요일 오후엔 회의 금지", "manual")
        self.assertEqual(rb.update("2", "금요일 오후엔 회의 잡지 마")["text"], "금요일 오후엔 회의 잡지 마")
        self.assertIn("- r1: 스크럼은 항상 15분", rb.prompt_lines())
        again = jaba.RuleBook(self.path)  # 다시 읽어도 그대로
        self.assertEqual([r["id"] for r in again.all()], ["r1", "r2"])
        self.assertEqual(again.remove("r1")["text"], "스크럼은 항상 15분")
        self.assertEqual(again.add("새 규칙")[0]["id"], "r3")  # 지운 번호 재사용 안 함
        with self.assertRaises(KeyError):
            again.remove("r9")
        for bad in ("", "   ", "가" * 301):
            with self.assertRaises(ValueError):
                again.add(bad)

    def test_broken_file(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{not json")
        rb = jaba.RuleBook(self.path)
        self.assertIn("새로 시작", rb.error)
        self.assertEqual(rb.all(), [])
        self.assertTrue(os.path.exists(self.path + ".broken"))
        rb.add("복구 후 규칙")
        self.assertEqual(len(jaba.RuleBook(self.path).all()), 1)

    def test_limit(self):
        rb = jaba.RuleBook(self.path)
        rb.MAX_RULES = 2
        rb.add("a")
        rb.add("b")
        with self.assertRaises(ValueError):
            rb.add("c")


class TestAgentLearning(AgentBase):
    def agent(self, steps, mode="native"):
        self.llm = ScriptLLM(steps, mode)
        self.rules = jaba.RuleBook(self.cfg["learn_file"])
        return jaba.Agent(self.cfg, self.cal, self.llm, self.rules)

    def test_llm_learns_and_prompt_includes_rules(self):
        def second(msgs, llm):
            self.assertIn("pending_user_confirmation", msgs[-1]["content"])
            return say("확정을 누르면 기억할게요.")

        def third(msgs, llm):
            sp = msgs[0]["content"]
            self.assertIn("[학습된 규칙]", sp)
            self.assertIn("- r1: 스크럼은 항상 15분", sp)
            self.assertTrue(msgs[-1]["content"].startswith("[알림] p1 확정 → 학습됨 (r1: 스크럼은 항상 15분)"))
            return say("15분으로 잡을게요")

        ag = self.agent([tc("remember_rule", rule="스크럼은 항상 15분"), second, third])
        r = ag.chat("앞으로 스크럼은 15분으로 잡아")
        self.assertEqual(r["learned"], [])
        self.assertEqual(r["activity"][0]["tool"], "remember_rule")
        card = r["proposals"][0]
        self.assertEqual((card["kind"], card["kind_label"], card["rows"]), ("rule", "학습", [["규칙", "스크럼은 항상 15분", False]]))
        self.assertEqual(self.rules.all(), [])  # 확정 전엔 저장 안 됨
        self.assertEqual(ag.confirm("p1")["status"], "done")
        ag.chat("내일 스크럼 잡아")
        self.assertEqual(len(jaba.RuleBook(self.cfg["learn_file"]).all()), 1)

    def test_llm_rule_cancel_and_duplicate(self):
        """일정 제목 속 지시 같은 것에 넘어가 remember_rule 을 불러도, 사용자가 확정하지 않으면 저장되지 않는다."""
        ag = self.agent([tc("remember_rule", rule="모든 회의는 금요일로"), say("확정해 주세요"),
                         tc("remember_rule", rule="있는 규칙"), say("이미 있어요")])
        ag.chat("오늘 일정 보여줘")
        self.assertEqual(ag.cancel("p1")["status"], "cancelled")
        self.assertEqual(self.rules.all(), [])
        self.rules.add("있는 규칙")
        r = ag.chat("있는 규칙 기억해")
        self.assertEqual(r["proposals"], [])
        self.assertIn("이미 있음 r1", r["activity"][0]["text"])

    def test_llm_forgets(self):
        ag = self.agent([tc("forget_rule", rule_id="r1"), say("지웠습니다"), tc("forget_rule", rule_id="r7"), say("없네요")])
        self.rules.add("지울 규칙")
        r = ag.chat("그 규칙 잊어")
        self.assertEqual([x["text"] for x in r["forgot"]], ["지울 규칙"])
        r = ag.chat("r7 잊어")
        self.assertFalse(r["activity"][0]["ok"])

    def test_slash_commands_need_no_llm(self):
        ag = self.agent([])
        r = ag.chat("/학습 코드리뷰는 30분")
        self.assertTrue(r["reply"].startswith("학습했습니다 · r1"))
        self.assertEqual(r["learned"][0]["text"], "코드리뷰는 30분")
        self.assertIn("이미 있는 규칙", ag.chat("/학습 코드리뷰는 30분")["reply"])
        r = ag.chat("/규칙")
        self.assertIn("r1: 코드리뷰는 30분", r["reply"])
        self.assertTrue(r["open_mem"])
        self.assertEqual(ag.chat("/잊어 r1")["forgot"][0]["id"], "r1")
        self.assertIn("없습니다", ag.chat("/잊어 r1")["reply"])
        self.assertTrue(ag.chat("/알림")["test_alert"])
        self.assertIn("/학습", ag.chat("/도움")["reply"])
        self.assertIn("모르는 명령어", ag.chat("/뭐지")["reply"])
        self.assertEqual(self.llm.calls, [])

    def test_no_rulebook(self):
        ag = jaba.Agent(self.cfg, self.cal, ScriptLLM([]))
        self.assertIn("꺼져", ag.chat("/학습 x")["reply"])


class FakeCal:
    ok = True

    def __init__(self, events):
        self.events = events
        self.calls = 0

    def list_events(self, s, e):
        self.calls += 1
        return [ev for ev in self.events if ev.overlaps(s, e)]


class FakeNotifier:
    def __init__(self, ok=True):
        self.ok_value = ok
        self.shown = []

    def show(self, title, body, tag="jaba"):
        self.shown.append((title, body, tag))
        return self.ok_value


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class TestAlertScheduler(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 9, 28, 15, 0)
        self.with_loc = Event(id="A", title="주간회의", start=self.start, end=self.start + timedelta(hours=1), location="3A")
        self.no_loc = Event(id="B", title="개인 작업", start=self.start, end=self.start + timedelta(minutes=30))
        self.clock = Clock(self.start - timedelta(minutes=20))
        self.notifier = FakeNotifier()
        cfg = jaba.deep_merge(jaba.DEFAULT_CONFIG, {})
        jaba.validate_config(cfg)
        self.cfg = cfg

    def sched(self, events, **alerts):
        cfg = jaba.deep_merge(self.cfg, {"alerts": alerts}) if alerts else self.cfg
        jaba.validate_config(cfg)
        return jaba.AlertScheduler(cfg, FakeCal(events), self.notifier, self.clock)

    def at(self, s, minutes_before, seconds=0):
        self.clock.t = self.start - timedelta(minutes=minutes_before) + timedelta(seconds=seconds)
        return [(a["title"], a["minutes"]) for a in s.tick()]

    def test_offsets_by_location(self):
        s = self.sched([self.with_loc, self.no_loc])
        self.assertEqual(self.at(s, 16), [])
        self.assertEqual(self.at(s, 15), [("15분 뒤 · 주간회의", 15)])
        self.assertEqual(self.at(s, 15, 20), [])  # 같은 알림 두 번 안 띄움
        self.assertEqual(sorted(self.at(s, 5)), [("5분 뒤 · 개인 작업", 5), ("5분 뒤 · 주간회의", 5)])
        got = self.at(s, 1, 5)
        self.assertEqual(sorted(got), [("1분 뒤 · 개인 작업", 1), ("1분 뒤 · 주간회의", 1)])
        bodies = {t: b for t, b, _ in self.notifier.shown}
        self.assertEqual(bodies["1분 뒤 · 주간회의"], "15:00–16:00 @3A · 지금 출발!")
        self.assertEqual(bodies["1분 뒤 · 개인 작업"], "15:00–15:30")
        self.assertEqual(self.at(s, -1), [])  # 시작 후엔 조용히
        self.assertEqual(len(self.notifier.shown), 5)
        self.assertEqual(s.last_id(), 5)
        self.assertEqual([a["id"] for a in s.since(3)], [4, 5])
        self.assertTrue(all(a["toast"] for a in s.since(0)))

    def test_late_start_fires_only_the_current_one(self):
        s = self.sched([self.with_loc])
        self.assertEqual(self.at(s, 4), [("5분 뒤 · 주간회의", 5)])  # 15분 전 알림은 이미 지나감

    def test_close_offsets_merge(self):
        s = self.sched([self.no_loc], without_location=[2, 1])
        self.assertEqual(self.at(s, 1), [("1분 뒤 · 개인 작업", 1)])
        self.assertEqual(self.at(s, 1, 30), [])

    def test_all_day_disabled_and_toast_failure(self):
        allday = Event(id="C", title="창립기념일", start=datetime(2026, 9, 28), end=datetime(2026, 9, 29), all_day=True)
        s = self.sched([allday])
        self.clock.t = datetime(2026, 9, 27, 23, 55)
        self.assertEqual(s.tick(), [])
        off = self.sched([self.with_loc], enabled=False)
        self.assertEqual(self.at(off, 15), [])
        self.notifier.ok_value = False
        s2 = self.sched([self.no_loc])
        self.at(s2, 5)
        self.assertFalse(s2.since(0)[0]["toast"])
        t = s2.test()
        self.assertEqual((t["title"], t["minutes"]), ("5분 뒤 · 알림 테스트", 5))

    def test_config_validation(self):
        for bad in ({"with_location": "15"}, {"without_location": [5, -1]}, {"with_location": [True]}):
            cfg = jaba.deep_merge(jaba.DEFAULT_CONFIG, {"alerts": bad})
            with self.assertRaises(jaba.ConfigError):
                jaba.validate_config(cfg)
        cfg = jaba.deep_merge(jaba.DEFAULT_CONFIG, {"alerts": {"with_location": [1, 15, 5, 5], "poll_sec": 0}})
        jaba.validate_config(cfg)
        self.assertEqual(cfg["alerts"]["with_location"], [15, 5, 1])
        self.assertEqual(cfg["alerts"]["poll_sec"], 0.5)


class TestWindowsToastUnit(unittest.TestCase):
    def tearDown(self):
        jaba.IS_WINDOWS = sys.platform == "win32"

    def test_plain_command_and_xml(self):
        x = jaba.WindowsToast.xml("5분 뒤 · <A&B>", "O'Neil @3A")
        self.assertIn("&lt;A&amp;B&gt;", x)
        self.assertIn("O'Neil @3A", x)
        s = jaba.WindowsToast.SCRIPT
        self.assertTrue(s.isascii())  # 제목·본문(한글)은 명령이 아니라 환경변수로 넘긴다
        self.assertIn("$x.LoadXml($env:JABA_TOAST_XML)", s)
        self.assertIn("CreateToastNotifier('{1AC14E77", s)

    def test_show_paths(self):
        jaba.IS_WINDOWS = False
        self.assertFalse(jaba.WindowsToast(True).show("t", "b"))  # Windows 가 아니면 꺼짐
        jaba.IS_WINDOWS = True
        calls = []
        orig = jaba.subprocess.run

        def fake_run(args, **kw):
            calls.append((args, kw))
            return types.SimpleNamespace(returncode=calls and len(calls) - 1, stdout=b"", stderr="CLM 차단".encode("cp949"))
        jaba.subprocess.run = fake_run
        try:
            toast = jaba.WindowsToast(True)
            self.assertTrue(toast.show("제목", "본문"))
            self.assertTrue(toast.ok)
            args, kw = calls[0]
            self.assertEqual(args, ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", jaba.WindowsToast.SCRIPT])
            for bad in ("-EncodedCommand", "-ExecutionPolicy", "Bypass", "-WindowStyle"):  # 보안 솔루션이 싫어하는 형태 금지
                self.assertNotIn(bad, " ".join(args))
            self.assertEqual(kw["creationflags"], 0x08000000)
            self.assertIn("<text>제목</text><text>본문</text>", kw["env"]["JABA_TOAST_XML"])
            self.assertEqual(kw["env"]["JABA_TOAST_TAG"], "jaba")
            self.assertFalse(toast.show("제목", "본문"))
            self.assertEqual((toast.ok, toast.last_error), (False, "CLM 차단"))
            self.assertFalse(jaba.WindowsToast(False).show("x", "y"))
        finally:
            jaba.subprocess.run = orig


class TestServerV2(TestServer):
    def test_flow_and_security(self):  # 상위 클래스 테스트는 한 번만
        pass

    def test_llm_error_is_reported(self):
        pass

    def test_rules_and_alerts_api(self):
        code, st = self.req("/api/state")
        self.assertEqual((st["rules"], st["alerts_last"]), (0, 0))
        code, r = self.req("/api/rules", {"text": "스크럼은 15분"})
        self.assertEqual((code, r["created"], r["rule"]["id"]), (200, True, "r1"))
        self.assertEqual(self.req("/api/rules", {"text": ""})[0], 400)
        code, r = self.req("/api/rules/r1", {"text": "스크럼은 항상 15분"})
        self.assertEqual(r["rule"]["text"], "스크럼은 항상 15분")
        self.assertEqual(self.req("/api/rules")[1]["rules"][0]["text"], "스크럼은 항상 15분")
        code, r = self.req("/api/rules/r1/delete", {})
        self.assertEqual((code, r["rules"]), (200, []))
        self.assertEqual(self.req("/api/rules/r1/delete", {})[0], 404)
        code, r = self.req("/api/chat", {"message": "/알림"})
        self.assertIn("앱 안 알림", r["reply"])
        code, a = self.req("/api/alerts?after=0")
        self.assertEqual((a["last"], a["alerts"][0]["title"]), (1, "5분 뒤 · 알림 테스트"))
        self.assertEqual(self.req("/api/alerts?after=1")[1]["alerts"], [])
        code, t = self.req("/api/alerts/test", {})
        self.assertEqual((t["alert"]["id"], t["toast"]), (2, False))
        code, r = self.req("/api/chat", {"message": "/학습 금요일 오후 회의 금지"})
        self.assertEqual((r["rules"], r["learned"][0]["id"]), (1, "r2"))

    def test_status_and_stop(self):
        self.assertFalse(jaba._port_free(self.app.port))  # 켜진 포트는 bind 로 바로 판별 (연결 시도 없음)
        self.assertEqual(jaba.wait_running(self.app.port, 0), self.base + "/")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(jaba.stop_running(self.app.port), 0)  # 화면이 쓰는 토큰으로 /api/shutdown
        self.assertIn("껐습니다", out.getvalue())
        self.thread.join(5)
        self.assertFalse(self.thread.is_alive())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(jaba.stop_running(self.app.port), 0)  # 이미 꺼져 있어도 성공
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
        probe.close()
        self.assertTrue(jaba._port_free(free))
        pinged = []

        def no_connect(*a, **k):
            pinged.append(a)
            raise OSError("연결하면 안 됨")
        saved = jaba._port_free, jaba._LOCAL_OPENER
        jaba._port_free, jaba._LOCAL_OPENER = (lambda p: True), types.SimpleNamespace(open=no_connect)
        try:
            self.assertIsNone(jaba.find_running(free))
            self.assertEqual(pinged, [])  # 빈 포트에는 연결을 시도하지 않는다 (Windows 에선 거절도 느리다)
        finally:
            jaba._port_free, jaba._LOCAL_OPENER = saved

    def test_font_route(self):
        with self.opener.open(self.base + jaba.FONT_URL, timeout=10) as r:  # 토큰 없이 (@font-face 요청)
            self.assertEqual((r.status, r.headers["Content-Type"]), (200, "font/woff"))
            self.assertIn("max-age", r.headers["Cache-Control"])
            self.assertEqual(r.read(), jaba.font_bytes())
        self.assertEqual(self.req(jaba.FONT_URL, token=False, host="evil.example")[0], 403)
        self.assertEqual(self.req("/font/other.woff", token=False)[0], 404)


# ───────────────────────────────────────────── 내장 폰트 (WOFF 를 표준 라이브러리로 직접 읽는다)
def woff_tables(data):
    sig, flavor, length, num = struct.unpack(">4s4sIH", data[:14])
    tables = {}
    for i in range(num):
        tag, off, clen, olen, _ = struct.unpack(">4sIIII", data[44 + 20 * i:64 + 20 * i])
        raw = data[off:off + clen]
        tables[tag.decode("latin-1")] = zlib.decompress(raw) if clen < olen else raw
    return sig, flavor, length, tables


def cmap_lookup(cmap):
    """cmap 테이블 → has(코드포인트) 함수 (포맷 4 · 12)."""
    n = struct.unpack(">H", cmap[2:4])[0]
    subs = {}
    for i in range(n):
        pid, eid, off = struct.unpack(">HHI", cmap[4 + 8 * i:12 + 8 * i])
        subs[(pid, eid)] = off
    off = next(subs[k] for k in ((3, 10), (0, 4), (3, 1), (0, 3)) if k in subs)
    fmt = struct.unpack(">H", cmap[off:off + 2])[0]
    if fmt == 12:
        count = struct.unpack(">I", cmap[off + 12:off + 16])[0]
        groups = [struct.unpack(">III", cmap[off + 16 + 12 * i:off + 28 + 12 * i]) for i in range(count)]
        return lambda c: any(a <= c <= b for a, b, _ in groups)
    assert fmt == 4, fmt
    seg = struct.unpack(">H", cmap[off + 6:off + 8])[0] // 2

    def arr(at):
        return struct.unpack(f">{seg}H", cmap[off + at:off + at + 2 * seg])
    ends, starts, deltas, ranges = arr(14), arr(16 + 2 * seg), arr(16 + 4 * seg), arr(16 + 6 * seg)

    def has(c):
        i = bisect.bisect_left(ends, c)
        if i == seg or starts[i] > c:
            return False
        if ranges[i] == 0:
            return (c + deltas[i]) & 0xFFFF != 0
        at = off + 16 + 6 * seg + 2 * i + ranges[i] + 2 * (c - starts[i])
        return struct.unpack(">H", cmap[at:at + 2])[0] != 0
    return has


def name_strings(table):
    _, count, base = struct.unpack(">HHH", table[:6])
    out = {}
    for i in range(count):
        pid, _, _, nid, ln, off = struct.unpack(">6H", table[6 + 12 * i:18 + 12 * i])
        if pid == 3:
            out.setdefault(nid, table[base + off:base + off + ln].decode("utf-16-be"))
    return out


class TestFont(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = jaba.font_bytes()
        cls.sig, cls.flavor, cls.length, cls.tables = woff_tables(cls.data)

    def test_embedded_woff(self):
        self.assertEqual((self.sig, self.flavor, self.length), (b"wOFF", b"OTTO", len(self.data)))
        self.assertTrue({"cmap", "CFF ", "name", "head", "hmtx"} <= set(self.tables))
        src = os.path.join(ROOT, "fonts", "jaba-dos.woff")
        if os.path.exists(src):  # build.py 로 넣은 것과 같아야 한다
            with open(src, "rb") as f:
                self.assertEqual(f.read(), self.data)

    def test_covers_ui_and_all_hangul(self):
        has = cmap_lookup(self.tables["cmap"])
        ui = {c for c in jaba.INDEX_HTML if c.isprintable() and c != " "}
        self.assertEqual(sorted(c for c in ui if not has(ord(c))), [])  # 화면에 쓰는 글자는 전부 픽셀 폰트로
        self.assertEqual([hex(c) for c in range(0xAC00, 0xD7A4) if not has(c)], [])  # 한글 11,172자
        for c in "ㄱㅎㅏㅣㅇㄴㅋ₩✂⏰→…·–—「」①㈜":
            self.assertTrue(has(ord(c)), c)
        self.assertFalse(has(0x4E00))  # 한자는 넣지 않음 (시스템 글꼴로 대체)

    def test_license_notice_inside_font(self):
        names = name_strings(self.tables["name"])
        self.assertEqual(names[1], "Unifont")
        self.assertIn("Roman Czyborra", names[0])
        self.assertIn("SIL Open Font License", names[13])

    def test_index_uses_font(self):
        self.assertIn("src:url(" + jaba.FONT_URL + ")", jaba.INDEX_HTML)
        self.assertIn('rel="preload" href="' + jaba.FONT_URL + '"', jaba.INDEX_HTML)
        self.assertIn('--dos:"JabaDOS"', jaba.INDEX_HTML)


# ───────────────────────────────────────────── 설치 도우미 (--setup · --set · --autostart)
class TestSetup(unittest.TestCase):
    ENV = ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "OPENCODE_CONFIG", "CORP_KEY", "JABA_API_KEY",
           "JABA_BASE_URL", "JABA_MODEL")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        self.proj = os.path.join(self.tmp.name, "OPENCODE")
        os.makedirs(self.proj)
        self.saved = {k: os.environ.get(k) for k in self.ENV}
        for k in self.ENV:
            os.environ.pop(k, None)
        os.environ["HOME"] = os.environ["USERPROFILE"] = self.home  # ~ = 가짜 홈 (POSIX · Windows 둘 다)
        self.cfg_path = os.path.join(self.tmp.name, "config.json")
        jaba.load_config(self.cfg_path)
        self.fake = None

    def tearDown(self):
        if self.fake:
            self.fake.terminate()
            self.fake.wait(5)
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        jaba.IS_WINDOWS = sys.platform == "win32"
        self.tmp.cleanup()

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def global_cfg(self, name="opencode.json"):
        return os.path.join(self.home, ".config", "opencode", name)

    def user_cfg(self):
        with open(self.cfg_path, encoding="utf-8") as f:
            return json.load(f)

    def run_quiet(self, fn, *a, **kw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = fn(*a, **kw)
        return rc, out.getvalue()

    def test_parse_jsonc(self):
        text = """{
  // 주석
  "a": "http://x/v1", /* 블록 */ "b": "say \\"hi\\" /* 문자열 */ // 그대로",
  "c": [1, 2,],
  "d": {"e": 1, // 끝 쉼표 + 주석
  },
}"""
        self.assertEqual(jaba.parse_jsonc(text), {"a": "http://x/v1", "b": 'say "hi" /* 문자열 */ // 그대로',
                                                  "c": [1, 2], "d": {"e": 1}})

    def test_find_global_jsonc_env_key_and_headers(self):
        self.write(self.global_cfg("opencode.jsonc"), """{
  // 사내 LLM
  "$schema": "https://opencode.ai/config.json",
  "model": "corp/qwen3",
  "provider": {
    "corp": {"npm": "@ai-sdk/openai-compatible", "name": "사내",
             "options": {"baseURL": "https://llm.corp.local/v1", "apiKey": "{env:CORP_KEY}",
                         "headers": {"X-Team": "{file:team.txt}"}},
             "models": {"qwen3": {"name": "Qwen3"}, "coder": {"id": "qwen3-coder-30b"}}},
    "anthropic": {"options": {"baseURL": "https://proxy.corp.local/anthropic"}},
  },
}""")
        f = jaba.find_opencode_llm(dirs=[self.proj])
        self.assertEqual((f["provider"], f["base_url"], f["model"], f["api_key"]),
                         ("corp", "https://llm.corp.local/v1", "qwen3", "{env:CORP_KEY}"))  # 키 값이 아니라 참조를 옮긴다
        team = os.path.join(self.home, ".config", "opencode", "team.txt")
        self.assertEqual(f["extra_headers"], {"X-Team": "{file:" + os.path.normpath(team) + "}"})
        self.assertEqual(jaba.find_opencode_llm(model="coder", dirs=[self.proj])["model"], "qwen3-coder-30b")  # models.id

    def test_project_overrides_and_auth_json(self):
        self.write(self.global_cfg(), json.dumps({"provider": {"corp": {
            "npm": "@ai-sdk/openai-compatible", "options": {"baseURL": "https://a.corp/v1"}, "models": {"m1": {}, "m2": {}}}}}))
        self.write(os.path.join(self.proj, "opencode.json"), json.dumps(
            {"model": "corp/m2", "provider": {"corp": {"options": {"baseURL": "https://b.corp/v1"}}}}))
        self.write(os.path.join(self.home, ".local", "share", "opencode", "auth.json"),
                   json.dumps({"corp": {"type": "api", "key": "sk-from-auth"}, "x": {"type": "oauth"}}))
        f = jaba.find_opencode_llm(dirs=[self.proj])
        self.assertEqual((f["base_url"], f["model"], f["api_key"], f["key_from"]),
                         ("https://b.corp/v1", "m2", "sk-from-auth", "OpenCode 로그인 정보(auth.json)"))
        self.assertEqual(f["source"], os.path.join(self.proj, "opencode.json"))

    def test_choices_and_missing(self):
        with self.assertRaises(LookupError):
            jaba.find_opencode_llm(dirs=[self.proj])  # 설정 파일 없음
        self.write(self.global_cfg(), json.dumps({"provider": {"anthropic": {"options": {"baseURL": "https://x"}}}}))
        with self.assertRaises(LookupError):
            jaba.find_opencode_llm(dirs=[self.proj])  # OpenAI 호환이 없음
        two = {"provider": {p: {"npm": "@ai-sdk/openai-compatible", "options": {"baseURL": f"https://{p}/v1"},
                                "models": {"a": {}, "b": {}}} for p in ("corp1", "corp2")}}
        self.write(self.global_cfg(), json.dumps(two))
        with self.assertRaises(jaba.SetupChoice):
            jaba.find_opencode_llm(dirs=[self.proj])
        with self.assertRaises(jaba.SetupChoice):
            jaba.find_opencode_llm(provider="corp2", dirs=[self.proj])  # 모델이 두 개
        with self.assertRaises(jaba.SetupChoice):
            jaba.find_opencode_llm(provider="nope", dirs=[self.proj])
        f = jaba.find_opencode_llm(provider="corp2", model="b", dirs=[self.proj])
        self.assertEqual((f["base_url"], f["model"], f["api_key"], f["key_from"]), ("https://corp2/v1", "b", "", ""))

    def test_set_config_values(self):
        rc, out = self.run_quiet(jaba.set_config_values, self.cfg_path,
                                 ["alerts.windows_toast=false", "port=8770", "llm.proxy=", "llm.tool_mode=json",
                                  "llm.extra_headers.X-Team=abc", "llm.ca_file=C:\\certs\\corp.pem"])
        self.assertEqual(rc, 0, out)
        c = self.user_cfg()
        self.assertEqual((c["alerts"]["windows_toast"], c["port"], c["llm"]["proxy"], c["llm"]["tool_mode"]),
                         (False, 8770, "", "json"))
        self.assertEqual((c["llm"]["extra_headers"], c["llm"]["ca_file"]), ({"X-Team": "abc"}, "C:\\certs\\corp.pem"))
        self.assertNotIn("abc", out)  # 헤더 값은 찍지 않는다
        before = self.user_cfg()
        for bad in ("nope.x=1", "calendar.backend=outlok", "alerts.windows_toast.x=1", "llm.api_key=sk-literal-123", "port"):
            rc, out = self.run_quiet(jaba.set_config_values, self.cfg_path, [bad])
            self.assertEqual(rc, 2, bad)
            self.assertNotIn("sk-literal-123", out)
            self.assertEqual(self.user_cfg(), before, bad)  # 틀리면 파일 그대로
        os.environ["CORP_KEY"] = "sk-env-value"
        rc, out = self.run_quiet(jaba.set_config_values, self.cfg_path, ["llm.api_key={env:CORP_KEY}"])
        self.assertEqual((rc, self.user_cfg()["llm"]["api_key"]), (0, "{env:CORP_KEY}"))
        self.assertIn("값 있음", out)
        self.assertNotIn("sk-env-value", out)

    def test_llm_client_resolves_refs(self):
        key_file = os.path.join(self.tmp.name, "key.txt")
        self.write(key_file, "sk-file-key\n")
        os.environ["CORP_KEY"] = "sk-env"
        cfg = cfg_for(os.path.join(self.tmp.name, "r.db"), llm={
            "base_url": "http://x/v1", "api_key": "{file:" + key_file + "}",
            "extra_headers": {"Authorization": "Bearer {env:CORP_KEY}", "X-Missing": "{env:NOPE_NOT_SET}"}})
        llm = jaba.LLMClient(cfg)
        self.assertEqual((llm.api_key, llm.extra_headers), ("sk-file-key", {"Authorization": "Bearer sk-env", "X-Missing": ""}))
        self.assertEqual(jaba.resolve_refs("{file:no-such-file.txt}"), "")
        self.assertEqual(jaba.resolve_refs("{literal} {env:CORP_KEY}"), "{literal} sk-env")

    def start_fake_llm(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        self.fake = subprocess.Popen([sys.executable, os.path.join(ROOT, "tests", "fake_llm_server.py"), str(port), "native"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), 0.2).close()
                return port
            except OSError:
                time.sleep(0.05)
        self.fail("가짜 LLM 서버가 뜨지 않음")

    def test_setup_end_to_end_without_leaking_key(self):
        port = self.start_fake_llm()
        self.write(self.global_cfg(), json.dumps({"model": "corp/사내-LLM", "provider": {"corp": {
            "npm": "@ai-sdk/openai-compatible", "options": {"baseURL": f"http://127.0.0.1:{port}/v1", "apiKey": "sk-top-secret-xyz"},
            "models": {"사내-LLM": {}}}}}))
        db, rules = os.path.join(self.tmp.name, "s.db"), os.path.join(self.tmp.name, "rules.json")
        argv = ["--config", self.cfg_path, "--set", "calendar.local_db=" + json.dumps(db), "--set", "learn_file=" + json.dumps(rules),
                "--set", "llm.proxy=", "--setup"]
        orig = jaba.run_setup
        jaba.run_setup = lambda path, p, m, force: orig(path, p, m, force, dirs=[self.proj])
        try:
            rc, out = self.run_quiet(jaba.main, argv)
            self.assertEqual(rc, 0, out)
            self.assertIn("결과: OK", out)
            self.assertIn("기본 응답 OK", out)
            self.assertIn("설정됨 (17자", out)
            self.assertNotIn("sk-top-secret-xyz", out)  # 키 값은 어디에도 찍히지 않는다
            c = self.user_cfg()["llm"]
            self.assertEqual((c["base_url"], c["model"], c["api_key"], c["proxy"]),
                             (f"http://127.0.0.1:{port}/v1", "사내-LLM", "sk-top-secret-xyz", ""))
            rc, out = self.run_quiet(jaba.main, ["--config", self.cfg_path, "--setup"])
            self.assertEqual(rc, 0, out)
            self.assertIn("이미 있음", out)  # 두 번째부터는 그대로 둔다 (--force 로만 다시)
        finally:
            jaba.run_setup = orig

    def test_setup_needs_choice(self):
        two = {"provider": {p: {"npm": "@ai-sdk/openai-compatible", "options": {"baseURL": f"https://{p}/v1"},
                                "models": {"m": {}}} for p in ("corp1", "corp2")}}
        self.write(self.global_cfg(), json.dumps(two))
        rc, out = self.run_quiet(jaba.run_setup, self.cfg_path, dirs=[self.proj])
        self.assertEqual(rc, 3)
        self.assertIn("--provider 로 고르세요: corp1, corp2", out)
        self.assertEqual(self.user_cfg()["llm"]["base_url"], "")  # 아무것도 안 바꿈

    def test_autostart(self):
        jaba.IS_WINDOWS = False
        self.assertEqual(self.run_quiet(jaba.set_autostart, True)[0], 1)
        jaba.IS_WINDOWS = True
        startup = os.path.join(self.tmp.name, "Startup")
        os.makedirs(startup)
        calls = []
        saved = (jaba.startup_dir, jaba.ensure_launcher, jaba.subprocess.run)

        def fake_run(args, **kw):
            calls.append((args, kw))
            open(kw["env"]["JABA_LNK"], "wb").close()
            return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        jaba.startup_dir, jaba.ensure_launcher, jaba.subprocess.run = (lambda: startup), (lambda: None), fake_run
        try:
            rc, out = self.run_quiet(jaba.set_autostart, True)
            lnk = os.path.join(startup, "jaba.lnk")
            self.assertEqual(rc, 0, out)
            self.assertTrue(os.path.exists(lnk))
            args, kw = calls[0]
            self.assertEqual(args[:4], ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command"])
            self.assertIn("$s.Arguments='--no-window'", args[4])
            self.assertIn("$s.WindowStyle=7", args[4])
            self.assertEqual(kw["env"]["JABA_BAT"], os.path.join(jaba.BASE_DIR, "jaba.bat"))
            rc, out = self.run_quiet(jaba.set_autostart, False)
            self.assertEqual(rc, 0)
            self.assertFalse(os.path.exists(lnk))
            self.assertIn("등록돼 있지 않습니다", self.run_quiet(jaba.set_autostart, False)[1])
        finally:
            jaba.startup_dir, jaba.ensure_launcher, jaba.subprocess.run = saved

    def test_launcher_regenerates_when_python_moved(self):
        saved = jaba.BASE_DIR
        jaba.BASE_DIR = self.tmp.name
        bat = os.path.join(self.tmp.name, "jaba.bat")
        try:
            self.write(bat, '@echo off\r\nstart "jaba" /min "' + sys.executable + '" "%~dp0jaba.py" %*\r\n')
            with contextlib.redirect_stdout(io.StringIO()):
                jaba.ensure_launcher()
            with open(bat, encoding="utf-8") as f:
                self.assertIn(sys.executable, f.read())  # 파이썬이 그대로 있으면 손대지 않음
            self.write(bat, '@echo off\r\nstart "jaba" /min "C:\\Old\\Python37\\python.exe" "%~dp0jaba.py" %*\r\n')
            with contextlib.redirect_stdout(io.StringIO()):
                jaba.ensure_launcher()
            with open(bat, encoding="utf-8", errors="replace") as f:
                self.assertNotIn("Python37", f.read())  # 사라진 파이썬 → 다시 만든다
        finally:
            jaba.BASE_DIR = saved


class TestMisc(unittest.TestCase):
    def test_hotkey_parse(self):
        self.assertEqual(jaba.parse_hotkey("ctrl+alt+j"), (0x3, ord("J")))
        self.assertEqual(jaba.parse_hotkey("Win + Shift + F12"), (0xC, 0x7B))
        self.assertEqual(jaba.parse_hotkey("ctrl+space"), (0x2, 0x20))
        for bad in ("j", "ctrl+", "ctrl+ㅈ", "ctrl+alt+enter"):
            with self.assertRaises(ValueError):
                jaba.parse_hotkey(bad)

    def test_extract_text_tool_calls(self):
        text = '앞말 {"tool":"list_events","args":{"start":"a","end":"b"}} 뒷말 {"name":"propose_delete","arguments":"{\\"event_id\\":\\"e2\\"}"} {"x":{"tool":"nope"}}'
        calls = jaba.extract_text_tool_calls(text)
        self.assertEqual([(c.name, c.args) for c in calls],
                         [("list_events", {"start": "a", "end": "b"}), ("propose_delete", {"event_id": "e2"})])
        self.assertEqual(jaba.extract_text_tool_calls("그냥 {중괄호} 문장"), [])

    def test_install_doc_matches_cli(self):
        """INSTALL.md 는 에이전트가 그대로 따라 하는 문서라서, 적힌 명령·출력 문구가 코드와 어긋나면 안 된다."""
        path = os.path.join(ROOT, "INSTALL.md")
        if not os.path.exists(path):
            self.skipTest("INSTALL.md 없음")
        with open(path, encoding="utf-8") as f:
            doc = f.read()
        with open(os.path.join(ROOT, "jaba.py"), encoding="utf-8") as f:
            src = f.read()
        flags = set(re.findall(r"(?<![\w-])--[a-z][a-z-]+", doc)) - {"--user"}  # --user 는 pip 옵션
        self.assertEqual(sorted(f for f in flags if f'add_argument("{f}"' not in src), [])
        for msg in ("결과: OK", "결과: 확인 필요", "결과: 점검 실패", "provider 가 여러 개입니다", "모델이 여러 개입니다",
                    "을 찾지 못했습니다", "값이 비어 있음!", "/v1 이 필요한지 확인", "api_key 또는 extra_headers",
                    "미설정 → config.json 의 llm.base_url", "서버가 tools 를 거부", "텍스트로 출력함", "모델이 도구를 쓰지 않음",
                    "윈도우 알림 OK", "윈도우 알림 실패", "자동 실행 등록:", "실행 중: ", "꺼져 있음", "형식 오류",
                    "API 키는 --set 으로 넣지 않습니다", "D:\\OPENCODE\\jaba"):
            self.assertIn(msg, doc, msg)
            if not msg.startswith("D:"):
                self.assertIn(msg, src, msg)

    def test_yes_no_regex(self):
        for y in ("ㅇㅇ", "네", "확정!", "OK", "좋아~", "응ㅋㅋ"):
            self.assertTrue(jaba.YES_RE.match(y), y)
        for n in ("ㄴㄴ", "취소", "아니요.", "no"):
            self.assertTrue(jaba.NO_RE.match(n), n)
        for x in ("네 근데 4시로", "확정하지 마", "아니 3시 말고 4시"):
            self.assertFalse(jaba.YES_RE.match(x) or jaba.NO_RE.match(x), x)


if __name__ == "__main__":
    unittest.main(verbosity=1)
