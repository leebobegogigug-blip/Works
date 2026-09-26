"""v4 메인 스토리 테스트: 주간 챕터 공개 · 미션 · 챕터 보스 · 지역 공개 · 저장/이전 · 토큰 경험치 체감 · 화면"""
import datetime
import json
import os
import re
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))  # 저장소 루트
TMP = tempfile.mkdtemp()
os.environ["LOCALAPPDATA"] = TMP
import t1_pet as P  # noqa: E402
import t1_pet_data as D  # noqa: E402
import t1_pet_ui as UI  # noqa: E402
from t1_term import vlen  # noqa: E402


def setUpModule():
    os.environ["LOCALAPPDATA"] = TMP


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def ts(y, mo, d, h=10, mi=0):
    return datetime.datetime(y, mo, d, h, mi).timestamp()


def mk(scope="st", t=None, persist=False, seed=1):
    clk = Clock(t or ts(2026, 9, 21, 10))
    return P.PetGame(scope, "토큰이", clock=clk, seed=seed, persist=persist), clk


def hatch(g, clk):
    clk.t += 200
    g.signal("busy", sid="a", title="t", agent="build")
    g.signal("idle", sid="a", title="t")
    g.tick()
    assert not g.is_egg()
    settle(g)


def settle(g):
    """연출·팝업 걷어 내기 (부화 연출 4초 동안은 키가 먹지 않는다)"""
    g.fx.clear()
    g.welcome = None
    g.last_summary = None
    g.banner = None
    g.banners.clear()


def tick_for(g, clk, secs, step=1.0):
    end = clk.t + secs
    while clk.t < end:
        clk.t += step
        g.input_seen()
        g.tick()


def fill_missions(g):
    """현재 챕터의 필수 미션을 전부 채운다 (보너스 제외)"""
    st = g.story()
    c = D.CHAPTERS[st["ch"]]
    for m in c["missions"]:
        if m.get("opt"):
            continue
        if m["k"] in ("floor", "clear"):
            g.s["prog"]["floor"][m["z"]] = 10
            if m["k"] == "clear" and m["z"] not in g.s["prog"]["cleared"]:
                g.s["prog"]["cleared"].append(m["z"])
        elif m["k"] == "kills":
            k = f"kz_{m['z']}"
            g.s["stats"][k] = g.s["stats"].get(k, 0) + m["n"]
        elif m["k"] == "stat":
            g.s["stats"][m["s"]] = g.s["stats"].get(m["s"], 0) + m["n"]
        elif m["k"] == "care":
            g.p["care"] = 99.0
        elif m["k"] == "enh":
            g.s["equip"]["weapon"]["plus"] = max(g.s["equip"]["weapon"]["plus"], m["n"])


def load(scope):
    with open(P.pet_path(scope), encoding="utf-8") as f:
        return json.load(f)


def dump(scope, s):
    with open(P.pet_path(scope), "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False)


def ready(g, lvl=None):
    """보스전 준비: 원정 끝, 체력·포만 가득, 레벨 넉넉히"""
    g.expd = None
    g.battle = None
    g.mg = None
    g.p.update(sleeping=False, sick=None, energy=100.0, full=90.0)
    st = g.story()
    g.p["lvl"] = lvl if lvl is not None else D.CHAPTERS[st["ch"]]["boss"]["lvl"] + 25
    S = g.stats()
    g.p["hp"], g.p["mp"] = S["maxhp"], S["maxmp"]


def fight(g, clk, secs=900):
    end = clk.t + secs
    while g.battle and clk.t < end:
        clk.t += 1.2
        g.tick()


class StoryStart(unittest.TestCase):
    def test_egg_has_no_story_and_first_zones_released(self):
        g, clk = mk()
        self.assertIsNone(g.story())
        self.assertEqual(g.story_released_n(), D.STORY["fast"])

    def test_hatch_starts_chapter_one(self):
        g, clk = mk()
        hatch(g, clk)
        st = g.story()
        self.assertEqual((st["ch"], st["phase"], st["fast"]), (0, "play", D.STORY["fast"]))
        self.assertEqual(st["start"], P.day_key(clk.t))
        zi = g.zones_info()
        self.assertTrue(all(z["released"] for z in zi[:D.STORY["fast"]]))
        self.assertFalse(any(z["released"] for z in zi[D.STORY["fast"]:]))

    def test_release_schedule_and_sticky(self):
        g, clk = mk()
        hatch(g, clk)
        f, every = D.STORY["fast"], D.STORY["every"]
        self.assertEqual(g.story_released_n(clk.t + (every - 1) * 86400), f)
        self.assertEqual(g.story_released_n(clk.t + every * 86400), f + 1)
        n_all = len(D.CHAPTERS)
        self.assertEqual(g.story_released_n(clk.t + every * (n_all - f) * 86400), n_all)
        self.assertEqual(g.story_released_n(clk.t + 999 * 86400), n_all)
        # 시계가 뒤로 가도 한 번 열린 건 닫히지 않는다
        self.assertEqual(g.story_released_n(clk.t), n_all)
        d = g.story_release_date(f)
        self.assertEqual(d, datetime.date.fromtimestamp(clk.t) + datetime.timedelta(days=every))
        self.assertIsNone(g.story_release_date(0))

    def test_unreleased_zone_is_locked(self):
        g, clk = mk()
        hatch(g, clk)
        g.p["lvl"] = 99
        for z in D.ZONES:
            if z["id"] not in g.s["prog"]["cleared"]:
                g.s["prog"]["cleared"].append(z["id"])
        zi = g.zones_info()
        f = D.STORY["fast"]
        self.assertTrue(zi[f - 1]["unlocked"])
        self.assertFalse(zi[f]["unlocked"])
        self.assertFalse(zi[f]["released"])
        g.p.update(energy=100.0, full=90.0)
        self.assertFalse(g.start_expedition(f))
        self.assertIsNone(g.expd)
        self.assertLessEqual(g.best_zone(), f - 1)


class Missions(unittest.TestCase):
    def test_progress_counts_from_chapter_start(self):
        g, clk = mk()
        g.s["stats"]["quests"] = 500             # 부화 전 기록은 세지 않는다
        hatch(g, clk)
        ms = g.story_missions()
        q = next(m for m in ms if "응답" in m["text"])
        self.assertEqual(q["prog"], 0)
        for _ in range(3):
            g.signal("busy", sid="b", title="x")
            clk.t += 5
            g.signal("idle", sid="b", title="x")
        q = next(m for m in g.story_missions() if "응답" in m["text"])
        self.assertEqual(q["prog"], 3)

    def test_sticky_and_boss_phase(self):
        g, clk = mk()
        hatch(g, clk)
        fill_missions(g)
        tick_for(g, clk, 3)
        st = g.story()
        self.assertEqual(st["phase"], "boss")
        req = [i for i, m in enumerate(D.CHAPTERS[0]["missions"]) if not m.get("opt")]
        self.assertTrue(set(req) <= set(st["mdone"]))
        # 진행이 되돌아가도(예: 은퇴로 층 기록 초기화) 완료한 미션은 그대로
        g.s["prog"]["floor"] = {}
        tick_for(g, clk, 3)
        self.assertEqual(st["phase"], "boss")
        self.assertTrue(all(m["done"] for m in g.story_missions() if not m["opt"]))

    def test_bonus_mission_rewards_once(self):
        g, clk = mk()
        hatch(g, clk)
        c = D.CHAPTERS[0]
        opt = next(m for m in c["missions"] if m.get("opt"))
        g.s["stats"][opt["s"]] = g.s["stats"].get(opt["s"], 0) + opt["n"]
        gold0 = g.s["gold"]
        tick_for(g, clk, 3)
        st = g.story()
        self.assertTrue(st["bonus"])
        self.assertGreater(g.s["gold"], gold0)
        gold1 = g.s["gold"]
        g.s["stats"][opt["s"]] += opt["n"] * 3
        tick_for(g, clk, 3)
        self.assertEqual(g.s["gold"] - gold1, 0)
        self.assertEqual(st["bonus_n"], 1)

    def test_mission_texts(self):
        g, clk = mk()
        hatch(g, clk)
        for i in range(len(D.CHAPTERS)):
            for m in g.story_missions(i):
                self.assertTrue(m["text"] and "{" not in m["text"], m)


class BossFight(unittest.TestCase):
    def test_cannot_fight_before_missions(self):
        g, clk = mk()
        hatch(g, clk)
        ok, why = g.can_story_boss()
        self.assertFalse(ok)
        self.assertIn("미션", why)
        self.assertFalse(g.start_story_boss())

    def test_win_clears_and_next_chapter_begins(self):
        g, clk = mk()
        hatch(g, clk)
        fill_missions(g)
        tick_for(g, clk, 2)
        ready(g)
        gold0 = g.s["gold"]
        self.assertTrue(g.start_story_boss())
        self.assertEqual(g.battle["story"], 0)
        fight(g, clk)
        st = g.story()
        self.assertIsNone(g.battle)
        self.assertIn("c01", st["cleared"])
        self.assertEqual(st["pending"], 0)
        self.assertEqual(st["ch"], 1)               # 앞 4장은 바로 이어진다
        self.assertEqual(st["phase"], "play")
        self.assertGreater(g.s["gold"], gold0)
        self.assertTrue(g.last_summary and g.last_summary[0].get("story") and g.last_summary[0]["win"])
        g.story_mark_seen(0, "outro")
        self.assertIsNone(st["pending"])

    def test_weekly_wait_then_release(self):
        g, clk = mk()
        hatch(g, clk)
        f = D.STORY["fast"]
        for i in range(f):
            fill_missions(g)
            tick_for(g, clk, 2)
            ready(g)
            self.assertTrue(g.start_story_boss(), g.can_story_boss())
            fight(g, clk)
        st = g.story()
        self.assertEqual((st["ch"], st["phase"]), (f - 1, "wait"))
        self.assertEqual(len(st["cleared"]), f)
        tick_for(g, clk, 60)
        self.assertEqual(st["phase"], "wait")
        # 다음 챕터 공개일(자정)이 지나면 시작
        d = g.story_release_date(f)
        clk.t = datetime.datetime(d.year, d.month, d.day, 0, 0, 30).timestamp()
        tick_for(g, clk, 3)
        self.assertEqual((st["ch"], st["phase"]), (f, "play"))
        self.assertTrue(g.zones_info()[f]["released"])

    def test_lose_has_no_faint_penalty(self):
        g, clk = mk()
        hatch(g, clk)
        fill_missions(g)
        tick_for(g, clk, 2)
        ready(g, lvl=1)
        g.s["gold"] = 1000
        faints = g.stat("faints")
        self.assertTrue(g.start_story_boss())
        fight(g, clk)
        st = g.story()
        self.assertEqual(st["phase"], "boss")
        self.assertEqual(st["fails"], 1)
        self.assertEqual(g.stat("faints"), faints)
        self.assertEqual(g.s["gold"], 1000)
        self.assertGreater(g.p["hp"], 0)
        self.assertFalse(g.can_story_boss()[0])        # HP 50% 넘을 때까지 쉬어야
        self.assertFalse(g.last_summary[0]["win"])

    def test_retreat_and_close(self):
        g, clk = mk()
        hatch(g, clk)
        fill_missions(g)
        tick_for(g, clk, 2)
        ready(g)
        self.assertTrue(g.start_story_boss())
        self.assertTrue(g.story_retreat())
        fight(g, clk)
        self.assertEqual(g.story()["phase"], "boss")
        self.assertEqual(g.story()["fails"], 0)
        ready(g)
        self.assertTrue(g.start_story_boss())
        g.close()                                  # 창을 닫으면 페널티 없이 물러난다
        self.assertIsNone(g.battle)
        self.assertEqual(g.story()["phase"], "boss")

    def test_story_battle_blocks_expedition_and_raid(self):
        g, clk = mk()
        hatch(g, clk)
        fill_missions(g)
        tick_for(g, clk, 2)
        ready(g)
        self.assertTrue(g.start_story_boss())
        ok, why = g.can_depart()
        self.assertFalse(ok)
        self.assertIn("보스전", why)
        self.assertFalse(g.can_raid()[0])

    def test_final_boss_phase2_and_season_end(self):
        g, clk = mk()
        hatch(g, clk)
        st = g.story()
        n = len(D.CHAPTERS)
        # 마지막 챕터 직전까지 건너뛰기
        st["cleared"] = [c["id"] for c in D.CHAPTERS[:n - 1]]
        st["fast"] = n
        st["rel"] = n
        g._story_begin(n - 1, clk.t, quiet=True)
        fill_missions(g)
        tick_for(g, clk, 2)
        self.assertEqual(st["phase"], "boss")
        ready(g)
        self.assertTrue(g.start_story_boss())
        b = g.battle
        self.assertEqual(b["phase2"], D.CHAPTERS[-1]["boss"]["phase2"])
        # 첫 번째 쓰러짐 → 리파이낸싱(부활)
        b["mon"]["hp"] = 0
        g._check_end(b)
        self.assertTrue(b["p2_done"])
        self.assertIsNone(b["over"])
        self.assertEqual(b["mon"]["hp"], int(b["mon"]["maxhp"] * b["phase2"]))
        fight(g, clk, 3000)
        self.assertEqual(st["phase"], "end")
        self.assertEqual(len(st["cleared"]), n)
        self.assertIn("season1", g.s["ach"])
        self.assertIn("greenlight", g.s["inv"]["decos"])
        self.assertFalse(g.can_story_boss()[0])
        tick_for(g, clk, 5)
        self.assertEqual(st["phase"], "end")


class SaveAndMigrate(unittest.TestCase):
    def test_roundtrip(self):
        scope = "story_rt"
        g, clk = mk(scope, persist=True)
        hatch(g, clk)
        fill_missions(g)
        tick_for(g, clk, 2)
        g.save(force=True)
        g.close()
        g2 = P.PetGame(scope, clock=clk, seed=2, persist=True)
        st = g2.story()
        self.assertEqual(st["phase"], "boss")
        self.assertEqual(load(scope)["v"], D.SAVE_VERSION)
        g2.close()

    def test_v3_save_migrates_with_catchup(self):
        scope = "story_mig"
        g, clk = mk(scope, persist=True)
        hatch(g, clk)
        g.s["prog"]["cleared"] = [z["id"] for z in D.ZONES[:6]]
        g.s["stats"]["quests"] = 321
        g.save(force=True)
        g.close()
        s = load(scope)
        s["v"] = 3
        s.pop("story", None)
        dump(scope, s)
        g2 = P.PetGame(scope, clock=clk, seed=3, persist=True)
        st = g2.story()
        self.assertIsNotNone(st)
        self.assertEqual(st["fast"], 7)            # 깬 6곳 + 새 지역 하나는 바로
        self.assertEqual(st["base"].get("quests"), 321)
        self.assertTrue(g2.zones_info()[6]["released"])
        self.assertFalse(g2.zones_info()[7]["released"])
        self.assertTrue(any("스토리" in ln for ln in (g2.welcome or [])))
        g2.close()

    def test_broken_story_is_sanitized(self):
        scope = "story_bad"
        g, clk = mk(scope, persist=True)
        hatch(g, clk)
        g.save(force=True)
        g.close()
        s = load(scope)
        s["story"].update(ch=99, phase="???", mdone="x", cleared=["c01", "zzz"], start="not-a-date", rel="7", pending="x")
        dump(scope, s)
        g2 = P.PetGame(scope, clock=clk, seed=3, persist=True)
        st = g2.story()
        self.assertEqual(st["ch"], len(D.CHAPTERS) - 1)
        self.assertEqual(st["phase"], "play")
        self.assertEqual(st["mdone"], [])
        self.assertEqual(st["cleared"], ["c01"])
        self.assertIsNone(st["pending"])
        g2.tick()
        g2.close()

    def test_story_survives_retire(self):
        g, clk = mk()
        hatch(g, clk)
        fill_missions(g)
        tick_for(g, clk, 2)
        ready(g)
        g.start_story_boss()
        fight(g, clk)
        st_before = dict(g.story())
        g.p["form"] = "tenx"
        g.p["lvl"] = 30
        g.s["hatched"] = clk.t - 4 * 86400
        self.assertTrue(g.retire())
        self.assertEqual(g.story()["cleared"], st_before["cleared"])
        self.assertEqual(g.story()["ch"], st_before["ch"])


class TokenCap(unittest.TestCase):
    def test_weights(self):
        self.assertEqual(P.token_weight(0, 1_000_000), 1_000_000)
        self.assertEqual(P.token_weight(1_500_000, 1_000_000), 500_000 + 500_000 * 0.25)
        self.assertEqual(P.token_weight(9_000_000, 3_000_000), 1_000_000 * 0.25 + 2_000_000 * 0.05)
        self.assertEqual(P.token_weight(50_000_000, 1_000), 1_000 * 0.05)
        self.assertEqual(P.token_rate(0), 1.0)
        self.assertEqual(P.token_rate(3_000_000), 0.25)
        self.assertEqual(P.token_rate(30_000_000), 0.05)

    def test_heavy_day_exp_is_capped(self):
        g, clk = mk()
        hatch(g, clk)
        g.p["lvl"], g.p["exp"] = 90, 0.0          # 레벨업이 안 끼게 높은 레벨에서 잰다
        g.s["daily"]["quests"] = []                # 일일 퀘스트 보상 경험치는 빼고 잰다
        for _ in range(50):                       # 2천만 토큰
            g.signal("tokens", tin=360_000, tout=40_000)
        exp = g.p["exp"] + 0.0
        expect = (2_000_000 * 1.0 + 8_000_000 * 0.25 + 10_000_000 * 0.05) / 1000
        self.assertAlmostEqual(exp, expect * g.exp_mult(), delta=5)
        self.assertLess(exp, 20_000 / 3)


def _plain(lines):
    return "\n".join(re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", ln) for ln in lines)


class StoryUI(unittest.TestCase):
    SIZES = ((40, 14), (48, 16), (60, 20), (80, 24), (120, 34))

    def setUp(self):
        self.g, self.clk = mk("ui_story")
        self.ui = UI.PetUI(self.g)
        self.ui.boot_until = 0

    def key(self, k):
        self.ui.key(k)
        self.ui.wipe_t = 0.0

    def render_all(self):
        for W, H in self.SIZES:
            lines = self.ui.render(W, H)
            self.assertLessEqual(len(lines), H)
            for ln in lines:
                self.assertLessEqual(vlen(ln), W, (W, H, ln))
        return self.ui.render(80, 24)

    def test_tab_7_and_egg(self):
        self.key("7")
        self.assertEqual(UI.TABS[self.ui.tab][0], "story")
        out = _plain(self.render_all())
        self.assertIn("초록불을 찾아서", out)

    def test_intro_autoplay_typewriter_and_seen(self):
        g = self.g
        hatch(g, self.clk)
        g.welcome = None
        self.key("7")
        self.render_all()
        sc = self.ui.scene
        self.assertIsNotNone(sc)
        self.assertEqual(sc["part"], "intro")
        self.key("ENTER")                     # 글자가 다 안 나왔으면 한 번에
        self.assertEqual(sc["idx"], 0)
        self.key("ENTER")
        self.assertEqual(sc["idx"], 1)
        self.render_all()
        self.key("ESC")                       # 건너뛰기 = 본 걸로
        self.assertIsNone(self.ui.scene)
        self.assertTrue(g.story_seen(0, "intro"))
        out = _plain(self.render_all())
        self.assertIn("MISSIONS", out)
        self.assertIn("NEXT", out)

    def test_boss_scene_then_battle_then_epilogue(self):
        g, clk = self.g, self.clk
        hatch(g, clk)
        g.welcome = None
        g.story_mark_seen(0, "intro")
        fill_missions(g)
        tick_for(g, clk, 2)
        ready(g)
        g.welcome = None
        self.key("7")
        self.render_all()
        self.key("b")
        self.assertEqual(self.ui.scene["part"], "boss")
        self.key("ESC")
        self.assertIsNotNone(g.battle)
        out = _plain(self.render_all())
        self.assertIn("CH01 BOSS", out)
        self.key("2")                          # 모험 탭에서도 같은 전투 화면
        self.assertIn("CH01 BOSS", _plain(self.render_all()))
        self.key("7")
        fight(g, clk)
        self.assertEqual(g.story()["pending"], 0)
        out = _plain(self.render_all())           # 결과 카드
        self.assertIn("CHAPTER CLEAR", out)
        self.key("ENTER")                      # 카드 닫기 → 에필로그 자동
        self.render_all()
        self.assertEqual(self.ui.scene["part"], "outro")
        self.key("ESC")
        self.assertIsNone(g.story()["pending"])
        self.render_all()
        self.assertEqual(self.ui.scene["part"], "intro")   # 다음 장 프롤로그가 이어진다
        self.assertEqual(self.ui.scene["ch"], 1)

    def test_browse_and_news_led(self):
        g, clk = self.g, self.clk
        hatch(g, clk)
        g.welcome = None
        self.assertTrue(self.ui._story_news())
        self.key("7")
        self.render_all()
        self.key("ESC")
        self.assertFalse(self.ui._story_news())
        self.key("RIGHT")
        self.assertEqual(self.ui._story_idx(), 1)   # 다음 장 예고까지 볼 수 있다
        self.key("RIGHT")
        self.assertEqual(self.ui._story_idx(), 1)
        out = _plain(self.render_all())
        self.assertIn("LOCK", out)
        self.key("ENTER")                      # 아직 안 열린 장은 대화 없음
        self.assertIsNone(self.ui.scene)
        self.key("LEFT")
        self.assertIsNone(self.ui.story_view)

    def test_wait_and_end_pages_render(self):
        g, clk = self.g, self.clk
        hatch(g, clk)
        g.welcome = None
        st = g.story()
        for c in D.CHAPTERS:
            for part in ("intro", "outro", "boss"):
                g.story_mark_seen(D.CHAPTERS.index(c), part)
        st["cleared"] = [c["id"] for c in D.CHAPTERS[:4]]
        st["ch"], st["phase"] = 3, "wait"
        self.key("7")
        out = _plain(self.render_all())
        self.assertIn("D-", out)
        st["cleared"] = [c["id"] for c in D.CHAPTERS]
        st["ch"], st["phase"] = len(D.CHAPTERS) - 1, "end"
        out = _plain(self.render_all())
        self.assertIn("완결", out)

    def test_every_scene_renders(self):
        g, clk = self.g, self.clk
        hatch(g, clk)
        g.welcome = None
        for i in range(len(D.CHAPTERS)):
            for part in ("intro", "boss", "outro", "replay"):
                self.ui._scene_start(i, part)
                while self.ui.scene:
                    self.ui.scene["t0"] -= 60
                    self.render_all()
                    self.key("ENTER")

    def test_home_hint_and_ranch_card(self):
        g, clk = self.g, self.clk
        hatch(g, clk)
        g.welcome = None
        out = _plain(self.ui.render(80, 24))
        self.assertIn("STORY", out)
        g.speech = ("", 0.0)                       # 카드 맨 아래 줄: 말풍선 > 퀘스트 > 스토리
        live = g.live_dict()
        self.assertEqual(live["story"]["ch"], 1)
        live["ts"] = time.time()                  # 목장은 '방금 쓴' live 파일만 믿는다
        P.write_json(P.live_path(g.scope), live)
        lines = UI.render_ranch([g.scope], 80, 24)
        self.assertIn("CH01", _plain(lines))


class DataIntegrity(unittest.TestCase):
    def test_chapters_reference_real_things(self):
        self.assertEqual(len(D.CHAPTERS), len(D.ZONES))
        for i, c in enumerate(D.CHAPTERS):
            self.assertEqual(c["zone"], D.ZONES[i]["id"])
            self.assertIn(c["boss"]["mid"], D.MONSTERS)
            for spk, _ in c["intro"] + c["outro"] + c["boss"]["intro"] + c["boss"].get("phase2_lines", []):
                self.assertTrue(spk in D.NPCS or spk in ("pet", "boss", "narr"), spk)
            r = c["reward"]
            for iid in list(r.get("items", {})) + list(r.get("mats", {})) + r.get("gear", []) + r.get("decos", []):
                self.assertIn(iid, D.ITEMS)
            self.assertEqual(sum(1 for m in c["missions"] if m.get("opt")), 1)
            self.assertEqual(len(c["hash"]), 7)
        lv = [c["boss"]["lvl"] for c in D.CHAPTERS]
        self.assertEqual(lv, sorted(lv))
        bases = [z["base"] for z in D.ZONES]
        self.assertEqual(bases, sorted(bases))

    def test_monster_art_fits(self):
        for mid, m in D.MONSTERS.items():
            self.assertEqual(len(m["art"]), 4, mid)
            for ln in m["art"]:
                self.assertLessEqual(vlen(ln), 12, (mid, ln))
                self.assertNotIn('\\"', ln, mid)


if __name__ == "__main__":
    unittest.main(verbosity=1)
