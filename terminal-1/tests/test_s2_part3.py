"""시즌 2 3부 (S2-3): 9~12장 · 피날레 리믹스 · 선대 카메오 · 시즌별 선택과 엔딩 · 완결 뒤 · R&D 두 줄"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_story as TS  # noqa: E402
from test_story import P, D, UI, vlen, mk, hatch, tick_for, ready, settle  # noqa: E402
from test_gimmick import at_chapter, until_tele  # noqa: E402
from test_side import finish_side  # noqa: E402

S1 = D.STORY_SEASONS[0]["n"]
CH = {c["id"]: i for i, c in enumerate(D.CHAPTERS)}
FIN = CH[D.FINALE["ch"]]
S1_SIDES = [e["id"] for e in D.SIDE_EPISODES if P.season_of(e["need"])["season"] == 1]


def setUpModule():
    TS.setUpModule()


def plain(lines):
    return re.sub(r"\x1b\[[0-9;]*m", "", "\n".join(lines))


def boss(g, i, off=30):
    ready(g, D.CHAPTERS[i]["boss"]["lvl"] + off)
    g.p["form"] = "singularity"
    S = g.stats()
    g.p["hp"], g.p["mp"] = S["maxhp"], S["maxmp"]
    return g.start_story_boss()


def keep_alive(g):
    g.battle["mon"]["hp"] = g.battle["mon"]["maxhp"]
    g.p["hp"] = g.stats()["maxhp"]


def retire_record(name):
    return dict(gen=1, name=name, form="tenx", lvl=40, title=None, personality="brave", days=10, care=80, discipline=50,
                kills=0, bosses=0, tokens=0, quests=0, todos=0, retired=0, zones=6, epitaph="-")


class Data(unittest.TestCase):
    def test_season2_is_complete(self):
        se = D.STORY_SEASONS[1]
        self.assertEqual(len(D.CHAPTERS), se["first"] + se["n"])
        self.assertTrue(P.season_final(FIN))
        self.assertEqual(D.CHAPTERS[FIN]["boss"].get("phase2"), 0.5)
        self.assertEqual(D.ENDINGS_BY_CH[D.FINALE["ch"]], D.ENDINGS2)
        self.assertEqual(set(D.ENDINGS2), {"now", "share", "balance"})
        s2_choices = [c for c in D.CHOICES if P.season_of(CH[c])["season"] == 2]
        self.assertEqual(len(s2_choices), 6)
        remix = D.GIMMICKS[D.CHAPTERS[FIN]["boss"]["mid"]]["remix"]
        others = [D.CHAPTERS[i]["boss"]["mid"] for i in range(S1, FIN)]
        self.assertEqual(sorted(remix), sorted(others))                      # 시즌 2 보스 기믹을 전부 섞는다
        for mid in ("sb21", "sb22", "sb23"):
            gd = D.GIMMICKS[mid]
            keys = [k for k, _ in gd["opts"]]
            pool = D.GIM_POOLS[gd["pool"]]
            self.assertGreaterEqual(len(pool), 8, mid)
            for k in keys:
                self.assertGreaterEqual(sum(1 for _, a, _ in pool if a == k), 3, (mid, k))      # 정답이 고루
            for q, a, why in pool:
                self.assertLessEqual(vlen(gd["warn"].format(q=q, agenda="", n=0, clue="")), 120, q)

    def test_rnd_new_lines(self):
        self.assertIn("party", D.RND)
        self.assertIn("boss", D.RND)


class Finale(unittest.TestCase):
    def test_remix_draws_from_past_bosses(self):
        g, clk = mk("fin1", seed=7)
        hatch(g, clk)
        at_chapter(g, clk, FIN)
        self.assertTrue(boss(g, FIN))
        remix = D.GIMMICKS["sb24"]["remix"]
        subs = []
        for _ in range(8):
            tl = until_tele(g, clk)
            self.assertIn(tl["sub"], remix)
            sgd = D.GIMMICKS[tl["sub"]]
            self.assertEqual(tl["opts"], list(sgd["opts"]))
            self.assertIn(tl["ans"], [k for k, _ in sgd["opts"]])
            subs.append(tl["sub"])
            before = g.gim_info()["meter"]["value"]
            g.gim_answer(tl["ans"])
            self.assertEqual(g.gim_info()["meter"]["value"], min(5, before + 1))     # Esc 조립
            keep_alive(g)
        self.assertGreaterEqual(len(set(subs)), 3)
        self.assertTrue(g.battle["gim"]["full"])                              # 다섯 번 맞히면 Esc 키 완성

    def test_wrong_answer_uses_the_copied_boss_words(self):
        g, clk = mk("fin2", seed=8)
        hatch(g, clk)
        at_chapter(g, clk, FIN)
        self.assertTrue(boss(g, FIN))
        tl = until_tele(g, clk)
        wrong = next(k for k, _ in tl["opts"] if k != tl["ans"])
        g.gim_answer(wrong)
        ng = D.GIMMICKS[tl["sub"]]["ng"]
        msg = ng.get(wrong) if isinstance(ng, dict) else ng
        self.assertTrue(any(msg in t for _, t in list(g.log)[-6:]), msg)

    def test_ancestors_join_the_finale(self):
        g, clk = mk("fin3")
        hatch(g, clk)
        g.s["family"]["hall"] = [retire_record("초대"), retire_record("두번째")]
        at_chapter(g, clk, FIN)
        text = "\n".join(t for _, t, _ in g.story_scene(FIN, "boss"))
        self.assertIn("두번째", text)                                        # 가장 최근 선대 이름
        self.assertTrue(boss(g, FIN))
        names = [h["name"] for h in g.battle["helpers"]]
        self.assertEqual(names[:2], ["두번째(선대)", "초대(선대)"])
        ui = UI.PetUI(g)
        ui.boot_until = 0
        ui.tab = 6
        settle(g)
        for W, H in ((60, 20), (80, 24)):
            for ln in ui.render(W, H):
                self.assertLessEqual(vlen(ln), W)

    def test_no_hall_no_ancestors(self):
        g, clk = mk("fin4")
        hatch(g, clk)
        at_chapter(g, clk, FIN)
        self.assertNotIn("명예의 전당", "\n".join(t for _, t, _ in g.story_scene(FIN, "boss")))
        self.assertTrue(boss(g, FIN))
        self.assertFalse(any(h.get("ancestor") for h in g.battle["helpers"]))
        g2, clk2 = mk("fin4b")
        hatch(g2, clk2)
        g2.s["family"]["hall"] = [retire_record("선배")]
        at_chapter(g2, clk2, CH["c23"])                                      # 피날레가 아니면 선대는 안 온다
        self.assertTrue(boss(g2, CH["c23"]))
        self.assertFalse(any(h.get("ancestor") for h in g2.battle["helpers"]))

    def test_share_path_brings_one_more_friend(self):
        for path, want in (("share", 4), ("now", 3)):
            g, clk = mk(f"fin5{path}")
            hatch(g, clk)
            st = g.story()
            at_chapter(g, clk, FIN)
            st["choices"] = {c: path for c in ("c02", "c04", "c06")}
            st["side_done"] = S1_SIDES + ["e_duck2", "e_turtle"]
            self.assertEqual(g.party_max(), want)
            self.assertEqual(len(g.story_helpers()), want)
            at_chapter(g, clk, CH["c23"])
            self.assertEqual(g.party_max(), 3)                               # 피날레에서만


class Ending(unittest.TestCase):
    def test_season2_ending_uses_season2_choices(self):
        g, clk = mk("end1")
        hatch(g, clk)
        st = g.story()
        st["cleared"] = [c["id"] for c in D.CHAPTERS[:FIN]]
        st["fast"] = st["rel"] = len(D.CHAPTERS)
        g._story_begin(FIN, clk.t, quiet=True)
        st["choices"] = {"c02": "now", "c04": "now", "c06": "now", "c08": "now",           # 시즌 1 은 '지금'
                         "c14": "share", "c16": "share", "c18": "share"}                   # 시즌 2 는 '함께'
        self.assertEqual((g.story_path(1), g.story_path(2), g.story_path()), ("now", "share", "now"))
        g._story_clear(FIN, clk.t)
        self.assertEqual(st["phase"], "end")
        self.assertIn("season2", g.s["ach"])
        self.assertIn("ask_neon", g.s["inv"]["decos"])
        outro = "\n".join(t for _, t, _ in g.story_scene(FIN, "outro"))
        self.assertIn(D.ENDINGS2["share"][1][1][:10], outro)
        self.assertIn("시즌 2", outro.splitlines()[-2])
        s1 = "\n".join(t for _, t, _ in g.story_scene(S1 - 1, "outro"))
        self.assertIn("미루지 않는", s1)                                      # 시즌 1 엔딩은 시즌 1 선택대로

    def test_after_season2_end(self):
        g, clk = mk("end2")
        hatch(g, clk)
        st = g.story()
        st["cleared"] = [c["id"] for c in D.CHAPTERS]
        st["ch"], st["phase"], st["pending"] = FIN, "end", None
        for i in range(len(D.CHAPTERS)):
            g.story_mark_seen(i, "intro")
            g.story_mark_seen(i, "outro")
        tick_for(g, clk, 2)
        self.assertEqual(st["phase"], "end")                                 # 다음 시즌은 아직 없다
        self.assertTrue(g.season_done(2))
        self.assertIsNotNone(g.debt_info())                                  # 부채 상환은 계속
        ui = UI.PetUI(g)
        ui.boot_until = 0
        ui.tab = 6
        settle(g)
        self.assertIn("시즌 2 완결", plain(ui.render(80, 24)))
        ui.tab = 0
        g.signal("wait", id="w1", sid="s", wkind="perm", label="bash: npm test")
        self.assertIn("오토: 해도 될까요?", plain(ui.render(80, 24)))           # 홈의 결재 팻말 옆

    def test_letter_after_the_finale_and_side_all2(self):
        g, clk = mk("end3")
        hatch(g, clk)
        st = g.story()
        s2 = [e["id"] for e in D.SIDE_EPISODES if P.season_of(e["need"])["season"] == 2]
        st.update(side_done=S1_SIDES + [x for x in s2 if x != "e_letter"], cleared=[c["id"] for c in D.CHAPTERS],
                  ch=FIN, phase="end", pending=None, side_t=0, side_at=-9)
        tick_for(g, clk, 2)
        self.assertEqual(g.side_info()["ep"]["id"], "e_letter")
        finish_side(g, clk)
        self.assertIn("side_all2", g.s["ach"])
        self.assertIn("letter_2019", g.s["inv"]["decos"])


class RnD(unittest.TestCase):
    def test_boss_analysis_and_party_training(self):
        g, clk = mk("rnd3")
        hatch(g, clk)
        at_chapter(g, clk, CH["c21"])
        g.s["gold"] = 10_000_000
        self.assertTrue(boss(g, CH["c21"]))
        hp0 = g.battle["mon"]["maxhp"]
        g.battle = None
        for _ in range(3):
            self.assertTrue(g.rnd_buy("boss"))
            self.assertTrue(g.rnd_buy("party"))
        at_chapter(g, clk, CH["c21"])
        self.assertTrue(boss(g, CH["c21"]))
        self.assertAlmostEqual(g.battle["mon"]["maxhp"] / hp0, 0.97, places=2)
        self.assertAlmostEqual(g.party_bonus(), D.PARTY_BONUS + 0.03)


if __name__ == "__main__":
    unittest.main()
