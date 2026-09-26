"""TOKEN QUEST v3 테스트: 리뷰 버그 수정 + 새 기능 (세대/성격/훈육/퀘스트 로그/응답 대기/레이드/퀴즈)"""
import datetime
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))  # 저장소 루트
TMP = tempfile.mkdtemp()
os.environ["LOCALAPPDATA"] = TMP
import t1_pet as P  # noqa: E402
import t1_pet_data as D  # noqa: E402
import t1_pet_run as R  # noqa: E402
import t1_monitor as M  # noqa: E402


def setUpModule():
    # 여러 테스트 파일을 한 번에 돌려도 저장 폴더가 섞이지 않게: 이 파일의 테스트는 이 파일의 임시 폴더만 쓴다
    os.environ["LOCALAPPDATA"] = TMP


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def ts(y, mo, d, h=10, mi=0):
    return datetime.datetime(y, mo, d, h, mi).timestamp()


def mk(scope="t", t=None, persist=False, seed=1):
    clk = Clock(t or ts(2026, 9, 21, 10))
    return P.PetGame(scope, "토큰이", clock=clk, seed=seed, persist=persist), clk


def hatch(g, clk):
    clk.t += 200
    g.signal("busy", sid="a", title="t", agent="build")
    g.signal("idle", sid="a", title="t")
    g.tick()
    assert not g.is_egg()


def run_for(g, clk, secs, step=5.0, present=True):
    end = clk.t + secs
    while clk.t < end:
        clk.t += step
        if present:
            g.input_seen()
        g.tick()


class Josa(unittest.TestCase):
    def test_cases(self):
        f = P.fix_josa
        self.assertEqual(f("매직넘버 42이(가) 나타났다"), "매직넘버 42가 나타났다")
        self.assertEqual(f("IBM 모델 M을(를) 얻었다"), "IBM 모델 M을 얻었다")
        self.assertEqual(f("Claude이(가) 왔다"), "Claude가 왔다")
        self.assertEqual(f("Python을(를) 배운다"), "Python을 배운다")
        self.assertEqual(f("핫픽스 패치으로(로) 회복"), "핫픽스 패치로 회복")
        self.assertEqual(f("아메리카노으로(로) 회복"), "아메리카노로 회복")
        self.assertEqual(f("Slack을(를) 켰다"), "Slack을 켰다")
        self.assertEqual(f("「코코」이(가) 인사했다"), "「코코」가 인사했다")
        self.assertEqual(f("1으로(로) 나눈다"), "1로 나눈다")
        self.assertEqual(f("3으로(로) 나눈다"), "3으로 나눈다")
        self.assertEqual(f("토큰이이(가) 코코아(야)"), "토큰이가 코코야")
        self.assertEqual(f("물건을(를) 샀다"), "물건을 샀다")
        self.assertEqual(f("API을(를) 호출"), "API를 호출")
        self.assertEqual(f("🙂이(가)"), "🙂이(가)")     # 모르면 그대로


class SaveRobustness(unittest.TestCase):
    def test_corrupt_backup(self):
        scope = "corrupt1"
        g, clk = mk(scope, persist=True)
        hatch(g, clk)
        g.s["gold"] = 99999
        g.save(force=True)
        g.close()
        with open(P.pet_path(scope), "r+", encoding="utf-8") as fh:
            data = fh.read()
            fh.seek(0)
            fh.write(data[: len(data) // 2])
            fh.truncate()
        g2 = P.PetGame(scope, clock=Clock(clk.t + 60), seed=2)
        self.assertTrue(g2.is_egg())
        backups = [f for f in os.listdir(P.data_dir()) if f.startswith(f"pet-{scope}.corrupt-")]
        self.assertEqual(len(backups), 1)
        self.assertTrue(any("백업" in w for w in g2.welcome))
        g2.close()

    def test_newer_version_readonly(self):
        scope = "newer1"
        os.makedirs(P.data_dir(), exist_ok=True)
        st = P.new_state(scope, "미래", time.time())
        st["v"] = D.SAVE_VERSION + 5
        st["gold"] = 4242
        P.write_json(P.pet_path(scope), st)
        g = P.PetGame(scope, clock=Clock(time.time()), seed=1)
        self.assertTrue(g.readonly)
        self.assertEqual(g.readonly_reason, "version")
        self.assertFalse(g.take_over(force=True))
        g.close()
        self.assertEqual(P.read_json(P.pet_path(scope))["gold"], 4242)

    def test_unknown_items_sanitized_and_v2_migration(self):
        scope = "v2old"
        now = ts(2026, 9, 21, 10)
        st = P.new_state(scope, "옛날이", now - 3 * 86400)
        st["v"] = 2
        del st["family"], st["raid"], st["quest_log"], st["expd_snap"], st["anniv_w"]
        st["pet"].pop("discipline")
        st["pet"].pop("personality")
        st["pet"]["form"] = "tenx"
        st["hatched"] = now - 3 * 86400
        st["last_anniv"] = 0
        st["inv"]["items"]["old_potion"] = 2
        st["inv"]["gear"].append({"id": "kb_old", "plus": 3})
        st["equip"]["weapon"] = {"id": "kb_gone", "plus": 1}
        st["gold"] = 100
        st["last_seen"] = now - 60
        P.write_json(P.pet_path(scope), st)
        g = P.PetGame(scope, clock=Clock(now), seed=1)
        self.assertEqual(g.s["v"], D.SAVE_VERSION)
        self.assertIn(g.p["personality"], D.PERSONALITIES)
        self.assertEqual(g.p["discipline"], 50.0)
        self.assertIn("tenx", g.s["family"]["forms_seen"])
        self.assertNotIn("old_potion", g.s["inv"]["items"])
        self.assertIsNone(g.s["equip"]["weapon"])
        self.assertGreater(g.s["gold"], 100)   # 환불
        g.items_of(("food", "drink"))
        g.battle_items()
        g.sell_list()
        for _ in range(30):
            g.tick()
        g.close()

    def test_expedition_snapshot_recovered(self):
        scope = "snap1"
        g, clk = mk(scope, persist=True)
        hatch(g, clk)
        g.p["energy"] = g.p["full"] = 90
        self.assertTrue(g.start_expedition(0))
        g.expd["carry"]["gold"] = 321
        g.expd["carry"]["mats"]["shard_scan"] = 4
        g.save(force=True)
        # 프로세스가 강제로 죽었다고 가정 (close 안 함) → 잠금이 오래되길 기다림
        clk2 = Clock(clk.t + 60)
        gold_before = P.read_json(P.pet_path(scope))["gold"]
        g2 = P.PetGame(scope, clock=clk2, seed=2)
        self.assertFalse(g2.readonly)
        self.assertEqual(g2.s["gold"], gold_before + 321)
        self.assertEqual(g2.s["inv"]["mats"].get("shard_scan"), 4)
        self.assertIsNone(g2.s["expd_snap"])
        g2.close()


class CareFixes(unittest.TestCase):
    def test_absent_no_sleep_flip(self):
        g, clk = mk(t=ts(2026, 9, 21, 10))
        hatch(g, clk)
        g.p["energy"] = 99.9
        notes_before = len(g.log)
        run_for(g, clk, 10 * 3600, step=1.0, present=False)
        flips = sum(1 for _, t in list(g.log) if "일어났다" in t)
        self.assertLessEqual(flips, 1)
        self.assertLess(len(g.log) - notes_before, 80)

    def test_burnout_low_level_is_curable(self):
        g, clk = mk()
        hatch(g, clk)
        g.p["sick"] = "burnout"
        g.s["gold"] = 500
        self.assertTrue(g.cure_available("burnout"))
        self.assertTrue(g.buy("vacation"))
        self.assertTrue(g.use_item("vacation"))
        self.assertIsNone(g.p["sick"])
        # 돈도 약도 없으면 호출/벌점 없음
        g.p["sick"] = "burnout"
        g.s["gold"] = 0
        g.s["inv"]["items"].pop("vacation", None)
        self.assertFalse(g.cure_available("burnout"))
        care0 = g.p["care"]
        g.p["full"] = 90
        g.p["sleeping"] = False
        g.p["health"] = 10
        g.p["energy"] = 50
        g.s["call"] = None
        run_for(g, clk, 10 * 3600, step=5.0, present=False)   # 가만히 두면 요양하러 잠든다
        self.assertGreaterEqual(g.p["care"], care0 - 1)
        self.assertIsNone(g.p["sick"])      # 푹 자고 회복

    def test_offline_call_cleared(self):
        scope = "offcall"
        g, clk = mk(scope, persist=True)
        hatch(g, clk)
        g.s["call"] = {"kind": "hungry", "since": clk.t}
        g.close()
        g2 = P.PetGame(scope, clock=Clock(clk.t + 3 * 3600), seed=3)
        care = g2.p["care"]
        g2.tick()
        self.assertIsNone(g2.s["call"])
        self.assertEqual(g2.p["care"], care)
        g2.close()

    def test_int_cap_keeps_event_int(self):
        g, clk = mk()
        hatch(g, clk)
        g.p["int_bonus"] = 8
        g.signal("tokens", tin=200000, tout=0)
        self.assertEqual(g.p["int_bonus"], 8)

    def test_minigame_idle_timeout(self):
        g, clk = mk()
        hatch(g, clk)
        self.assertTrue(g.start_minigame("type"))
        run_for(g, clk, 90, step=1.0, present=False)
        self.assertIsNone(g.mg)

    def test_overfed_keeps_exploring(self):
        g, clk = mk()
        hatch(g, clk)
        g.p["sick"] = "overfed"
        g.s["timers"]["overfed_until"] = clk.t + 3600
        g.p["energy"] = g.p["full"] = 90
        self.assertTrue(g.start_expedition(0))
        run_for(g, clk, 8, step=1.0)
        self.assertIsNotNone(g.expd)

    def test_close_mid_battle_penalty(self):
        g, clk = mk()
        hatch(g, clk)
        g.p["energy"] = g.p["full"] = 90
        g.start_expedition(0)
        g.expd["carry"]["gold"] = 1000
        g.start_battle("golem", "boss", 5)
        gold0 = g.s["gold"]
        g.close()
        self.assertEqual(g.s["gold"] - gold0, 700)

    def test_anniversary_once(self):
        g, clk = mk()
        hatch(g, clk)
        g.s["hatched"] = clk.t - 15 * 86400
        g.s["anniv_w"] = 0
        cakes = g.s["inv"]["items"].get("cake", 0)
        clk.t += 86400
        g.tick()
        self.assertEqual(g.s["inv"]["items"].get("cake", 0), cakes + 1)
        self.assertEqual(g.s["anniv_w"], 2)
        clk.t += 86400
        g.tick()
        self.assertEqual(g.s["inv"]["items"].get("cake", 0), cakes + 1)

    def test_clock_backwards_no_regrant(self):
        g, clk = mk()
        hatch(g, clk)
        date = g.s["daily"]["date"]
        streak = g.s["daily"]["streak"]
        gold = g.s["gold"]
        clk.t -= 3 * 86400
        g.tick()
        self.assertEqual(g.s["daily"]["date"], date)
        self.assertEqual(g.s["daily"]["streak"], streak)
        self.assertLessEqual(g.s["gold"], gold + 5)


class Discipline(unittest.TestCase):
    def setUp(self):
        self.g, self.clk = mk(seed=5)
        hatch(self.g, self.clk)

    def test_scold_tantrum(self):
        g = self.g
        g.s["call"] = {"kind": "tantrum", "since": g.now()}
        d0 = g.p["discipline"]
        self.assertTrue(g.scold())
        self.assertIsNone(g.s["call"])
        self.assertEqual(g.p["discipline"], d0 + P.T["disc_scold"])

    def test_spoil_tantrum(self):
        g = self.g
        g.s["call"] = {"kind": "tantrum", "since": g.now()}
        d0 = g.p["discipline"]
        self.clk.t += 10
        g.pat()
        self.assertIsNone(g.s["call"])
        self.assertEqual(g.p["discipline"], d0 - P.T["disc_spoil"])

    def test_wrong_scold(self):
        g = self.g
        m0 = g.p["mood"]
        g.scold()
        self.assertEqual(g.p["mood"], max(0, m0 - 8))

    def test_tantrum_appears_and_expires_softly(self):
        g, clk = self.g, self.clk
        g.s["timers"]["next_call"] = 0
        seen = False
        for _ in range(400):
            g.p["full"], g.p["mood"], g.p["energy"], g.p["bugs"] = 90, 90, 90, 0
            g.s["timers"]["next_call"] = 0
            g.s["timers"]["call_cool"] = 0
            g.s["call"] = None
            clk.t += 1
            g.input_seen()
            g.tick()
            if g.s["call"] and g.s["call"]["kind"] == "tantrum":
                seen = True
                break
        self.assertTrue(seen)
        care = g.p["care"]
        d0 = g.p["discipline"]
        clk.t += P.T["call_expire"] + 5
        g.input_seen()
        g.tick()
        self.assertIsNone(g.s["call"])
        self.assertGreaterEqual(g.p["care"], care - 0.01)
        self.assertEqual(g.p["discipline"], d0 - P.T["disc_ignore"])

    def test_teen_form_uses_discipline(self):
        g = self.g
        g.p["care"] = 55
        g.p["discipline"] = 80
        self.assertEqual(g._teen_form(), "junior")
        g.p["care"] = 70
        g.p["discipline"] = 10
        self.assertEqual(g._teen_form(), "kiddie")


class OpencodeWiring(unittest.TestCase):
    def test_todos_quest_log(self):
        g, clk = mk()
        hatch(g, clk)
        todos = [{"content": "스키마 파악", "status": "in_progress"}, {"content": "테스트 작성", "status": "pending"},
                 {"content": "리팩터링", "status": "pending"}]
        g.signal("todos", sid="r1", title="결제 리팩터링", todos=todos, root=True)
        self.assertEqual(g.quest_progress(), (0, 3, "스키마 파악"))
        gold0 = g.s["gold"]
        todos[0]["status"] = "completed"
        todos[1]["status"] = "in_progress"
        g.signal("todos", sid="r1", title="결제 리팩터링", todos=todos, root=True)
        self.assertEqual(g.stat("todos_done"), 1)
        self.assertGreater(g.s["gold"], gold0)
        # 같은 목록이 다시 와도 중복 보상 없음
        g.signal("todos", sid="r1", title="결제 리팩터링", todos=todos, root=True)
        self.assertEqual(g.stat("todos_done"), 1)
        # 서브에이전트 목록은 진행 중인 메인 목록을 덮지 않음
        g.signal("todos", sid="sub1", title="탐색", todos=[{"content": "x", "status": "pending"}], root=False)
        self.assertEqual(g.s["quest_log"]["sid"], "r1")
        for t in todos:
            t["status"] = "completed"
        g.signal("todos", sid="r1", title="결제 리팩터링", todos=todos, root=True)
        self.assertTrue(g.s["quest_log"]["cleared"])
        self.assertEqual(g.stat("todo_lists"), 1)
        self.assertEqual(g.stat("todos_done"), 3)

    def test_todo_daily_cap(self):
        g, clk = mk()
        hatch(g, clk)
        g.s["daily"]["todo_n"] = P.T["todo_daily_cap"]
        g.signal("todos", sid="r", title="", todos=[{"content": "a", "status": "pending"}], root=True)
        g.signal("todos", sid="r", title="", todos=[{"content": "a", "status": "completed"}], root=True)
        self.assertEqual(g.stat("todos_done"), 0)

    def test_wait_and_fast_reply(self):
        g, clk = mk()
        hatch(g, clk)
        g.signal("wait", id="per_1", sid="r1", wkind="perm", label="bash rm -rf dist")
        self.assertTrue(g.ring)
        self.assertIn("per_1", g.waits)
        self.assertEqual(g.live_dict()["wait"], "bash rm -rf dist")
        clk.t += 5
        g.signal("wait_done", id="per_1", reply="once")
        self.assertNotIn("per_1", g.waits)
        self.assertIn("fastperm", g.s["ach"])
        # 응답이 안 와도 루트가 idle 이 되면 정리
        g.signal("wait", id="q1", sid="r2", wkind="ask", label="어느 쪽?")
        g.signal("idle", sid="r2", title="t")
        self.assertNotIn("q1", g.waits)

    def test_compacted_abort_command(self):
        g, clk = mk()
        hatch(g, clk)
        g.p["full"] = 50
        g.signal("compacted", sid="r")
        self.assertEqual(g.p["full"], 54)
        errs = g.stat("errors")
        g.signal("abort", sid="r")
        self.assertEqual(g.stat("errors"), errs)
        self.assertIsNone(g.s.get("boss_flag"))
        g.signal("command", name="init")
        self.assertEqual(g.stat("commands"), 1)


class Generations(unittest.TestCase):
    def test_retire_flow(self):
        g, clk = mk(seed=7)
        hatch(g, clk)
        ok, why = g.can_retire()
        self.assertFalse(ok)
        g.p["form"] = "hunter"
        g.p["lvl"] = 26
        g.s["hatched"] = clk.t - 4 * 86400
        g.s["equip"]["weapon"] = {"id": "kb_topre", "plus": 5}
        g.s["gold"] = 5000
        g.s["inv"]["placed"] = []
        self.assertTrue(g.can_retire()[0])
        self.assertTrue(g.retire())
        self.assertTrue(g.is_egg())
        self.assertEqual(g.s["family"]["gen"], 2)
        self.assertEqual(g.p["name"], "토큰이 2세")
        self.assertEqual(g.s["gold"], 5000 + next(a[3] for a in D.ACHIEVEMENTS if a[0] == "retire"))
        self.assertTrue(any(x["id"] == "kb_topre" and x["plus"] == 5 for x in g.s["inv"]["gear"]))
        hall = g.s["family"]["hall"]
        self.assertEqual(hall[-1]["form"], "hunter")
        self.assertAlmostEqual(g.family_bonus("exp"), 0.05)
        self.assertIn("retire", g.s["ach"])
        # 새 알이 금방 깬다
        clk.t += 200
        g.tick()
        self.assertFalse(g.is_egg())
        self.assertIn(g.p["personality"], D.PERSONALITIES)
        self.assertEqual(P.heir_name("토큰이 2세", 3), "토큰이 3세")

    def test_maintainer_secret(self):
        g, clk = mk(seed=8)
        hatch(g, clk)
        g.s["family"]["forms_seen"] = ["egg", "bit", "byte", "junior", "tenx", "hunter", "architect", "monk"]
        g.p["form"] = "monk"
        g.p["lvl"] = 35
        g.p["care"] = 90
        g.s["prog"]["cleared"] = ["z1", "z2", "z3", "z4", "z5", "z6"]
        g.s["hatched"] = clk.t - 6 * 86400
        g._check_evolve()
        self.assertEqual(g.p["form"], "maintainer")
        self.assertIn("maintainer", g.s["ach"])
        self.assertIn("lgtm", g.available_skills())


class RaidTests(unittest.TestCase):
    def test_raid_flow_and_board(self):
        g, clk = mk("raidA", persist=True, seed=9, t=ts(2026, 9, 22, 10))
        hatch(g, clk)
        g.p["lvl"] = 12
        g.p["energy"] = g.p["full"] = 95
        self.assertTrue(g.start_raid())
        self.assertTrue(g.battle["raid"])
        for _ in range(400):
            clk.t += 0.5
            g.input_seen()
            g.tick()
            if not g.battle:
                break
        self.assertIsNone(g.battle)
        self.assertGreater(g.s["raid"]["dmg"], 0)
        self.assertTrue(os.path.exists(P.raid_path("raidA")))
        board = P.raid_board(P.week_key(clk.t), clk.t, fresh=True)
        self.assertEqual(board[0]["scope"], "raidA")
        # 두 번째 펫 참가 → 공동 체력 증가
        info1 = g.raid_info(fresh=True)
        P.write_json(P.raid_path("raidB"), dict(week=P.week_key(clk.t), scope="raidB", name="코코", lvl=20, dmg=500, cleared=False))
        info2 = g.raid_info(fresh=True)
        self.assertGreater(info2["hp"], info1["hp"])
        # 하루 3번 제한
        g.s["raid"]["tries"]["n"] = D.RAID["per_day"]
        ok, why = g.can_raid()
        self.assertFalse(ok)
        # 격파 → 보상 한 번만
        P.write_json(P.raid_path("raidB"), dict(week=P.week_key(clk.t), scope="raidB", name="코코", lvl=20, dmg=10 ** 7, cleared=True))
        cores = g.s["inv"]["mats"].get("boss_core", 0)
        g._raid_claim_check()
        self.assertTrue(g.s["raid"]["claimed"])
        self.assertEqual(g.s["inv"]["mats"].get("boss_core", 0), cores + 2)
        g._raid_claim_check()
        self.assertEqual(g.s["inv"]["mats"].get("boss_core", 0), cores + 2)
        self.assertIn("raid_clear", g.s["ach"])
        g.close()

    def test_raid_weekly_reset(self):
        g, clk = mk("raidC", seed=10, t=ts(2026, 9, 22, 10))
        hatch(g, clk)
        g.s["raid"].update(week=P.week_key(clk.t), dmg=999, claimed=True)
        clk.t += 7 * 86400
        r = g._raid_state()
        self.assertEqual(r["dmg"], 0)
        self.assertFalse(r["claimed"])


class Quiz(unittest.TestCase):
    def test_perfect_quiz(self):
        g, clk = mk(seed=11)
        hatch(g, clk)
        ib = g.p["int_bonus"]
        self.assertTrue(g.start_minigame("quiz"))
        for _ in range(5):
            q = D.QUIZ[g.mg["qs"][g.mg["idx"]]]
            g.minigame_key("o" if q[1] else "x")
            g.minigame_key("ENTER")
        self.assertEqual(g.mg["phase"], "result")
        self.assertIn("quiz_perfect", g.s["ach"])
        self.assertEqual(g.p["int_bonus"], ib + 1)

    def test_quiz_timeout(self):
        g, clk = mk(seed=12)
        hatch(g, clk)
        g.start_minigame("quiz")
        run_for(g, clk, 5 * (D.QUIZ_TIME + 4) + 5, step=0.5)
        self.assertTrue(g.mg is None or g.mg["phase"] == "result")


class Bus(unittest.TestCase):
    def test_no_replay_after_truncate(self):
        scope = "busx"
        r = P.BusReader(scope)
        got = 0
        for i in range(900):
            P.bus_write(scope, {"type": "compose", "chars": 1, "text": "x" * 400, "i": i})
            if i % 7 == 0:
                got += len(r.poll())
        got += len(r.poll())
        self.assertLessEqual(got, 900)
        self.assertGreater(got, 800)


class FakeApi:
    def get(self, path, timeout=5):
        return []


class FakeInst:
    def __init__(self):
        import threading
        self.lock = threading.Lock()
        self.sessions, self.status, self.stats = {}, {}, {}
        self.listeners = []
        self.ready = True
        self.offline_since = None
        self.created_ms = {}
        self.api = FakeApi()

    def session_tokens(self):
        return {sid: (st.get("tin", 0), st.get("tout", 0) + st.get("reason", 0), self.created_ms.get(sid, 0))
                for sid, st in self.stats.items()}

    def totals(self):
        return (sum(s.get("tin", 0) for s in self.stats.values()), sum(s.get("tout", 0) for s in self.stats.values()))

    def emit(self, typ, **props):
        for fn in self.listeners:
            fn({"type": typ, "properties": props})


class Rec:
    def __init__(self):
        self.sig = []

    def signal(self, kind, **d):
        self.sig.append((kind, d))


class Bridge(unittest.TestCase):
    def mkb(self):
        inst = FakeInst()
        td = M.TokenDelta(start_ms=time.time() * 1000)
        b = R.SignalBridge(inst, td, M.wait_info, M.WAIT_ASK_EVENTS, M.WAIT_DONE_EVENTS)
        return inst, b, Rec()

    def test_child_with_late_parent_is_sub(self):
        inst, b, g = self.mkb()
        now = time.time() * 1000
        inst.sessions["root"] = {"id": "root", "title": "r", "time": {"created": now, "updated": now}}
        inst.status = {"root": {"type": "busy"}, "child": {"type": "busy"}}
        b.poll(g)                          # child: 아직 정체불명 → 보류
        self.assertEqual([k for k, _ in g.sig], ["busy"])
        g.sig.clear()
        inst.emit("session.created", info={"id": "child", "parentID": "root", "title": "c"})
        b.poll(g)
        self.assertEqual(g.sig[-1][0], "sub_start")
        inst.status = {"root": {"type": "busy"}}
        b.poll(g)
        self.assertEqual(g.sig[-1][0], "sub_end")
        inst.status = {}
        b.poll(g)
        self.assertEqual(g.sig[-1][0], "idle")

    def test_old_session_no_token_dump(self):
        inst, b, g = self.mkb()
        old = time.time() * 1000 - 86400 * 1000
        inst.created_ms["old"] = old
        inst.stats["old"] = {"tin": 400000, "tout": 20000}
        b.poll(g)
        self.assertFalse([s for s in g.sig if s[0] == "tokens"])
        inst.stats["old"] = {"tin": 401000, "tout": 20000}
        b.poll(g)
        self.assertEqual([d for k, d in g.sig if k == "tokens"], [{"tin": 1000, "tout": 0}])
        # 새 세션은 0부터
        inst.created_ms["new"] = time.time() * 1000
        inst.stats["new"] = {"tin": 3000, "tout": 100}
        b.poll(g)
        self.assertEqual([d for k, d in g.sig if k == "tokens"][-1], {"tin": 3000, "tout": 100})

    def test_offline_ends_busy(self):
        inst, b, g = self.mkb()
        now = time.time() * 1000
        inst.sessions["r"] = {"id": "r", "title": "r", "time": {"created": now, "updated": now}}
        inst.status = {"r": {"type": "busy"}}
        b.poll(g)
        inst.offline_since = time.time() - 30
        b.poll(g)
        self.assertEqual(g.sig[-1][0], "gone")      # 서버가 사라지면 보상 없이 정리

    def test_events(self):
        inst, b, g = self.mkb()
        inst.emit("session.error", sessionID="r", error={"name": "MessageAbortedError", "data": {"message": "aborted"}})
        inst.emit("session.error", sessionID="r", error={"name": "APIError", "data": {"message": "429 Too Many Requests"}})
        inst.emit("todo.updated", sessionID="r", todos=[{"content": "a", "status": "pending"}])
        inst.emit("permission.asked", id="per_9", sessionID="r", permission="bash", patterns=["rm -rf dist"])
        inst.emit("permission.replied", sessionID="r", requestID="per_9", reply="once")
        inst.emit("permission.updated", id="per_1", sessionID="r", type="edit", title="Edit src/a.py")
        inst.emit("question.asked", id="q_1", sessionID="r", questions=[{"question": "어느 DB?", "header": "DB"}])
        inst.emit("session.compacted", sessionID="r")
        inst.emit("command.executed", name="init", sessionID="r", arguments="", messageID="m")
        inst.emit("message.part.updated", part={"id": "p1", "type": "tool", "tool": "read", "sessionID": "r",
                                                "state": {"status": "completed", "time": {"start": 1, "end": 2, "compacted": 3}}})
        inst.emit("message.part.updated", part={"id": "p2", "type": "tool", "tool": "read", "sessionID": "r",
                                                "state": {"status": "completed", "time": {"start": 1, "end": 2}}})
        inst.emit("message.part.updated", part={"id": "p3", "type": "tool", "tool": "edit", "sessionID": "r",
                                                "state": {"status": "running"}})
        inst.emit("message.part.updated", part={"id": "p3", "type": "tool", "tool": "edit", "sessionID": "r",
                                                "state": {"status": "completed", "time": {"start": 1, "end": time.time() * 1000}}})
        b.poll(g)
        kinds = [k for k, _ in g.sig]
        self.assertEqual(kinds.count("abort"), 1)
        self.assertEqual(kinds.count("error"), 1)
        self.assertIn("todos", kinds)
        waits = [d for k, d in g.sig if k == "wait"]
        self.assertEqual({w["id"] for w in waits}, {"per_9", "per_1", "q_1"})
        self.assertEqual([d["id"] for k, d in g.sig if k == "wait_done"], ["per_9"])
        self.assertIn("compacted", kinds)
        self.assertIn("command", kinds)
        tools = [d for k, d in g.sig if k == "tool"]
        self.assertEqual([t["tool"] for t in tools], ["edit"])   # 압축/오래된 도구는 제외


class UiSmoke(unittest.TestCase):
    def test_render_all_views(self):
        import t1_pet_ui as UI
        from t1_term import vlen
        g, clk = mk(seed=13, t=ts(2026, 10, 6, 10))     # 레이드 테스트와 다른 주
        hatch(g, clk)
        ui = UI.PetUI(g)
        g.welcome = None
        g.signal("todos", sid="r", title="t", todos=[{"content": "하나", "status": "completed"},
                                                     {"content": "둘", "status": "in_progress"}], root=True)
        g.signal("wait", id="w", sid="r", wkind="perm", label="bash ls")
        g.s["call"] = {"kind": "tantrum", "since": g.now()}
        for W, H in ((40, 14), (56, 19), (80, 24), (120, 34)):
            for tab in range(6):
                ui.tab = tab
                for sub in range(len(UI.SUBTABS.get(UI.TABS[tab][0], [0]))):
                    if UI.TABS[tab][0] in UI.SUBTABS:
                        ui.sub[UI.TABS[tab][0]] = sub
                    lines = ui.render(W, H)
                    self.assertLessEqual(len(lines), H)
                    for ln in lines:
                        self.assertLessEqual(vlen(ln), W, (W, H, tab, sub, ln))
        # 레이드 화면 + 퀴즈 + 은퇴식
        g.welcome = None
        g.s["call"] = None
        g.p["energy"] = g.p["full"] = 95
        self.assertTrue(g.start_raid())
        ui.tab = 1
        for W, H in ((40, 14), (80, 24)):
            for ln in ui.render(W, H):
                self.assertLessEqual(vlen(ln), W)
        g.battle = None
        g.start_minigame("quiz")
        for W, H in ((40, 14), (80, 24)):
            for ln in ui.render(W, H):
                self.assertLessEqual(vlen(ln), W)
        g.mg = None
        g.p["form"], g.p["lvl"] = "tenx", 30
        g.s["hatched"] = g.now() - 5 * 86400
        g.retire()
        for W, H in ((40, 14), (80, 24)):
            for ln in ui.render(W, H):
                self.assertLessEqual(vlen(ln), W)

    def test_paste_burst_ignored(self):
        import t1_pet_ui as UI
        g, clk = mk(seed=14)
        hatch(g, clk)
        ui = UI.PetUI(g)
        g.welcome = None
        ui.tab = 3
        ui.sub["shop"] = 1
        n = sum(g.s["inv"]["items"].values())
        ui.keys(list("hello\rworld\r\r"))
        self.assertEqual(sum(g.s["inv"]["items"].values()), n)

    def test_superscript_digit_no_crash(self):
        import t1_pet_ui as UI
        g, clk = mk(seed=15)
        hatch(g, clk)
        ui = UI.PetUI(g)
        g.welcome = None
        ui.key("f")
        ui.key("²")
        ui.key("①")
        ui.key("ESC")


if __name__ == "__main__":
    unittest.main(verbosity=1)
