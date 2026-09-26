"""시즌 2 엔진 (S2-0): 시즌 구조 · 시즌 1 → 2 전환 · 준비 중 대기 · 시즌별 조각 · 부채는 계속 · 사내 R&D"""
import copy
import datetime
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_story as TS  # noqa: E402
from test_story import P, D, UI, vlen, mk, hatch, fill_missions, tick_for, ready, settle  # noqa: E402


def setUpModule():
    TS.setUpModule()


def plain(lines):
    return re.sub(r"\x1b\[[0-9;]*m", "", "\n".join(lines))


def fake_chapter(k):
    """시즌 2 자리에 끼워 넣는 시험용 챕터 (지역은 시즌 1 몬스터를 빌려 쓴다)"""
    c = copy.deepcopy(D.CHAPTERS[0])
    c.update(id=f"t2c{k:02d}", title=f"시험 {k}장", en=f"TEST {k}", zone=f"t2z{k:02d}", hash=f"{k:07d}",
             missions=[dict(k="stat", n=1, z=None, s="pats", opt=False), dict(k="stat", n=1, z=None, s="meals", opt=True)])
    c["boss"] = dict(c["boss"], lvl=20)
    return c


def fake_zone(k):
    z = copy.deepcopy(D.ZONES[0])
    z.update(id=f"t2z{k:02d}", name=f"시험 지역 {k}", short=f"시험{k}", lvl=1, base=1)
    return z


class FakeSeason2:
    """D.CHAPTERS · D.ZONES 에 시즌 2 챕터를 n 개 끼워 넣었다가 되돌린다"""

    def __init__(self, n):
        self.n = n

    def __enter__(self):
        self.ch, self.zn = list(D.CHAPTERS), list(D.ZONES)
        D.CHAPTERS.extend(fake_chapter(k) for k in range(1, self.n + 1))
        D.ZONES.extend(fake_zone(k) for k in range(1, self.n + 1))
        return self

    def add(self, k):
        D.CHAPTERS.append(fake_chapter(k))
        D.ZONES.append(fake_zone(k))

    def __exit__(self, *a):
        D.CHAPTERS[:] = self.ch
        D.ZONES[:] = self.zn


def finish_season1(g, clk):
    st = g.story()
    s1 = D.STORY_SEASONS[0]
    st["cleared"] = [c["id"] for c in D.CHAPTERS[:s1["n"]]]
    st["ch"], st["phase"], st["pending"] = s1["n"] - 1, "end", s1["n"] - 1
    return st


def clear_current(g, clk):
    fill_missions(g)
    tick_for(g, clk, 2)
    st = g.story()
    assert st["phase"] == "boss", st["phase"]
    g._story_clear(st["ch"], clk.t)
    g.story_mark_seen(st["ch"], "outro")
    tick_for(g, clk, 2)


class Helpers(unittest.TestCase):
    def test_labels_and_seasons(self):
        self.assertEqual(P.ch_tag(0), "CH01")
        self.assertEqual(P.ch_tag(11), "CH12")
        self.assertEqual(P.ch_tag(12), "S2 CH01")
        self.assertEqual(P.ch_no(15), 4)
        self.assertTrue(P.season_final(11))
        self.assertTrue(P.season_final(23))
        self.assertFalse(P.season_final(12))
        self.assertEqual(P.season_of(5)["season"], 1)
        self.assertEqual(P.season_of(12)["season"], 2)
        s1 = D.STORY_SEASONS[0]
        self.assertEqual((s1["title"], s1["fast"], s1["every"]), (D.STORY["title"], D.STORY["fast"], D.STORY["every"]))


class WithoutSeason2Content(unittest.TestCase):
    def test_season1_end_waits_with_teaser_and_debt(self):
        g, clk = mk("s2none")
        hatch(g, clk)
        st = finish_season1(g, clk)
        g.story_mark_seen(11, "outro")
        tick_for(g, clk, 3)
        self.assertEqual((st["ch"], st["phase"]), (11, "end"))       # 시즌 2 는 아직 이 버전에 없다
        self.assertIsNotNone(g.debt_info())
        ui = UI.PetUI(g)
        ui.boot_until = 0
        ui.tab = 6
        settle(g)
        for i in range(12):
            g.story_mark_seen(i, "intro")
        screen = plain(ui.render(80, 24))
        self.assertIn("시즌 1 완결", screen)
        self.assertIn("Esc를 찾아서", screen)
        self.assertIn("준비 중", screen)


class Transition(unittest.TestCase):
    def test_season1_to_season2_and_content_gate(self):
        with FakeSeason2(2) as fk:
            g, clk = mk("s2go")
            hatch(g, clk)
            st = finish_season1(g, clk)
            tick_for(g, clk, 2)
            self.assertEqual(st["phase"], "end")                      # 완결 에필로그를 보기 전엔 그대로
            g.story_mark_seen(11, "outro")
            tick_for(g, clk, 2)
            s2 = D.STORY_SEASONS[1]
            self.assertEqual((st["ch"], st["phase"]), (12, "play"))
            self.assertEqual(st["start"], P.day_key(clk.t))
            self.assertEqual(st["fast"], s2["fast"])
            self.assertGreaterEqual(g.story_released_n(), 12 + s2["fast"])
            self.assertTrue(g.zones_info()[12]["released"])
            self.assertIn("시즌 2", "\n".join(t for _, t in st["log"][-3:]))
            clear_current(g, clk)
            self.assertEqual((st["ch"], st["phase"]), (13, "play"))   # 시즌 2 는 2장까지 바로
            clear_current(g, clk)
            self.assertEqual((st["ch"], st["phase"]), (13, "wait"))   # 3장은 아직 준비 중
            self.assertEqual(P.season_cleared(st, s2), 2)
            self.assertEqual(P.season_cleared(st, D.STORY_SEASONS[0]), 12)
            # 업데이트로 3장이 들어오고 공개일이 지났다면 받자마자 시작
            fk.add(3)
            self.assertEqual(g.story_release_date(14), datetime.date.fromisoformat(st["start"]) + datetime.timedelta(days=7))
            tick_for(g, clk, 2)
            self.assertEqual(st["phase"], "wait")
            clk.t += 8 * 86400
            tick_for(g, clk, 2)
            self.assertEqual((st["ch"], st["phase"]), (14, "play"))

    def test_story_tab_in_season2(self):
        with FakeSeason2(2):
            g, clk = mk("s2ui")
            hatch(g, clk)
            finish_season1(g, clk)
            g.story_mark_seen(11, "outro")
            tick_for(g, clk, 2)
            g.story_mark_seen(12, "intro")
            ui = UI.PetUI(g)
            ui.boot_until = 0
            ui.tab = 6
            settle(g)
            screen = plain(ui.render(80, 24))
            self.assertIn("S2", screen)
            self.assertIn("Esc를 찾아서", screen)
            self.assertIn("01/12", screen)
            self.assertEqual(P.season_cleared(g.story(), D.STORY_SEASONS[1]), 0)     # 시즌 2 조각 0개부터
            ui.key("LEFT")                                              # 시즌 1 마지막 장도 다시 볼 수 있다
            screen = plain(ui.render(80, 24))
            self.assertIn("초록불을 찾아서", screen)
            self.assertIn("12/12", screen)
            for W, H in ((40, 14), (60, 20), (120, 34)):
                for ln in ui.render(W, H):
                    self.assertLessEqual(vlen(ln), W)
            # 방 선반은 지금 시즌 조각
            ui.tab = 0
            settle(g)
            self.assertNotIn("[▮▮▮▮▮▮▮▮▮▮▮▮]", plain(ui.render(80, 24)))

    def test_debt_keeps_running_in_season2(self):
        with FakeSeason2(2):
            g, clk = mk("s2debt")
            hatch(g, clk)
            finish_season1(g, clk)
            g.story_mark_seen(11, "outro")
            tick_for(g, clk, 2)
            self.assertEqual(g.story()["ch"], 12)
            self.assertIsNotNone(g.debt_info())
            ui = UI.PetUI(g)
            ui.boot_until = 0
            ui.tab = 6
            settle(g)
            g.story_mark_seen(12, "intro")
            self.assertIn("B", [p[0] for p in ui._hint_pairs()])
            ready(g, 100)
            ui.key("b")                                                 # 챕터 보스 신호가 없으면 B = 부채 상환전
            self.assertEqual(ui.scene["part"], "debt")
            ui.scene = None
            fill_missions(g)
            tick_for(g, clk, 2)
            self.assertEqual(g.story()["phase"], "boss")
            ui.key("b")                                                 # 신호가 잡히면 B = 챕터 보스
            self.assertEqual(ui.scene["part"], "boss")

    def test_sanitize_keeps_season2_progress(self):
        with FakeSeason2(2):
            scope = "s2save"
            g, clk = mk(scope, persist=True)
            hatch(g, clk)
            finish_season1(g, clk)
            g.story_mark_seen(11, "outro")
            tick_for(g, clk, 2)
            st = g.story()
            st["rel"] = 3                                              # 깨진 값
            g.save(force=True)
            g.close()
            g2 = P.PetGame(scope, clock=clk, seed=3, persist=True)
            st2 = g2.story()
            self.assertEqual(st2["ch"], 12)
            self.assertEqual(st2["fast"], D.STORY_SEASONS[1]["fast"])
            self.assertGreaterEqual(st2["rel"], 12 + st2["fast"])
            g2.close()


class RnD(unittest.TestCase):
    def test_buy_levels_costs_and_max(self):
        g, clk = mk("rnd1")
        hatch(g, clk)
        r = D.RND["window"]
        self.assertEqual(g.rnd_cost("window"), r["base"])
        g.s["gold"] = 10 ** 9
        spent = 0
        for lv in range(r["max"]):
            spent += g.rnd_cost("window")
            self.assertTrue(g.rnd_buy("window"))
        self.assertEqual(g.rnd_level("window"), r["max"])
        self.assertIsNone(g.rnd_cost("window"))
        self.assertFalse(g.rnd_buy("window"))
        self.assertEqual(g.s["gold"], 10 ** 9 - spent)
        self.assertEqual(g.stat("rnd_spent"), spent)
        self.assertEqual(int(r["base"] * D.RND_GROWTH), int(r["base"] * D.RND_GROWTH ** 1))
        g.s["gold"] = 0
        self.assertFalse(g.rnd_buy("exp"))
        for k in D.RND:
            g.s["rnd"][k] = D.RND[k]["max"]
        g.s["gold"] = 10 ** 9
        g.s["rnd"]["exp"] -= 1
        g.rnd_buy("exp")
        self.assertIn("rnd_all", g.s["ach"])

    def test_effects(self):
        g, clk = mk("rnd2")
        hatch(g, clk)
        base_exp, base_mod = g.exp_mult(), g._mods("full_decay")
        g.s["rnd"] = {"exp": 10, "care": 5, "window": 4, "auto": 5}
        self.assertAlmostEqual(g.exp_mult() / base_exp, 1.10, places=3)
        self.assertAlmostEqual(g._mods("full_decay") / base_mod, 0.90, places=3)
        st = g.story()
        st["cleared"] = [c["id"] for c in D.CHAPTERS[:3]]
        st["fast"] = st["rel"] = len(D.CHAPTERS)
        g._story_begin(3, clk.t, quiet=True)
        fill_missions(g)
        tick_for(g, clk, 2)
        ready(g, 60)
        g.last_input = clk.t - 3600
        self.assertTrue(g.start_story_boss())
        tl = None
        for _ in range(400):
            clk.t += 0.5
            g.tick()
            tl = g.battle.get("tele")
            if tl:
                break
        self.assertAlmostEqual(tl["until"] - tl["t0"], D.GIM_WINDOW["away"] + 2.0)
        self.assertAlmostEqual(tl["auto_p"], D.GIMMICKS["sb04"]["auto"] + 0.10)

    def test_sanitize_and_forge_ui(self):
        scope = "rnd3"
        g, clk = mk(scope, persist=True)
        hatch(g, clk)
        g.s["rnd"] = {"exp": 99, "nope": 3, "care": "x", "drop": True}
        g.save(force=True)
        g.close()
        g2 = P.PetGame(scope, clock=clk, seed=3, persist=True)
        self.assertEqual(g2.s["rnd"], {"exp": D.RND["exp"]["max"]})
        ui = UI.PetUI(g2)
        ui.boot_until = 0
        ui.tab = 4
        ui.sub["forge"] = 2
        settle(g2)
        g2.s["gold"] = 10 ** 7
        screen = plain(ui.render(80, 24))
        self.assertIn("R&D", screen)
        self.assertIn(D.RND["care"]["name"], screen)
        ui.key("DOWN")
        ui.key("ENTER")                                                 # 두 번째 줄 = 사내 복지
        self.assertEqual(g2.rnd_level("care"), 1)
        for W, H in ((40, 14), (60, 20), (120, 34)):
            for ln in ui.render(W, H):
                self.assertLessEqual(vlen(ln), W)
        g2.close()


if __name__ == "__main__":
    unittest.main()
