"""v5 기다리는 주 · 엔딩 뒤: 사이드 에피소드 · NPC 동료 · 챕터 선택과 엔딩 · 주간 부채 상환 · 골드 쓸 곳"""
import datetime
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_story as TS  # noqa: E402
from test_story import P, D, UI, vlen, mk, hatch, fill_missions, tick_for, ready, fight, settle  # noqa: E402


def setUpModule():
    TS.setUpModule()


def plain(lines):
    return re.sub(r"\x1b\[[0-9;]*m", "", "\n".join(lines))


def cleared_upto(g, clk, n):
    """챕터 n 개를 깬 상태 (다음 챕터 진행 중)"""
    st = g.story()
    st["cleared"] = [c["id"] for c in D.CHAPTERS[:n]]
    st["fast"] = st["rel"] = len(D.CHAPTERS)
    if n < len(D.CHAPTERS):
        g._story_begin(n, clk.t, quiet=True)
    return st


def finish_side(g, clk):
    """지금 사이드 에피소드를 도입 → 목표 → 마무리까지"""
    si = g.side_info()
    assert si, g.story()
    g.side_seen()
    goal = si["ep"]["goal"]
    g.s["stats"][goal["s"]] = g.stat(goal["s"]) + goal["n"]
    tick_for(g, clk, 2)
    assert g.side_info()["phase"] == "done"
    g.side_seen()


class Data(unittest.TestCase):
    def test_side_episodes(self):
        ids, needs = set(), []
        for e in D.SIDE_EPISODES:
            self.assertNotIn(e["id"], ids)
            ids.add(e["id"])
            needs.append(e["need"])
            self.assertIn(e["npc"], D.NPCS)
            self.assertIn(e["goal"]["s"], D.STORY_STAT_TEXT)
            for iid in e["reward"].get("decos", []):
                self.assertEqual(D.ITEMS[iid]["kind"], "deco")
                self.assertIn(iid, D.DECO_ART)
            h = e["help"]
            self.assertIn(h["kind"], ("attack", "heal", "guard"))
            self.assertEqual(len(h["art"]), 2)
            for ln in h["art"]:
                self.assertLessEqual(vlen(ln), 6)
            for spk, _ in e["intro"] + e["outro"]:
                base, _, face = spk.partition(":")
                self.assertTrue(base in D.NPCS or base in ("pet", "narr"))
                self.assertTrue(not face or face in D.FACES)
        self.assertEqual(needs, sorted(needs))

    def test_choices_and_endings(self):
        for cid, ch in D.CHOICES.items():
            self.assertIn(cid, {c["id"] for c in D.CHAPTERS})
            self.assertEqual([o[0] for o in ch["opts"]], ["now", "share"])
            for _, label, reply in ch["opts"]:
                self.assertIn(reply[0], D.NPCS)
        self.assertEqual(set(D.ENDINGS), {"now", "share", "balance"})

    def test_premium_decos_are_expensive_sinks(self):
        for iid in ("gold_duck", "neon_green", "server_farm"):
            it = D.ITEMS[iid]
            self.assertTrue(it["shop"])
            self.assertGreaterEqual(it["price"], 50000)
            self.assertIn(iid, D.DECO_ART)


class SideEpisodes(unittest.TestCase):
    def test_arrives_after_chapter_and_runs_to_reward(self):
        g, clk = mk("side1")
        hatch(g, clk)
        tick_for(g, clk, 2)
        self.assertIsNone(g.side_info())                          # 1장을 깨기 전엔 없음
        cleared_upto(g, clk, 1)
        tick_for(g, clk, 2)
        si = g.side_info()
        self.assertEqual((si["ep"]["id"], si["phase"]), ("e_duck", "new"))
        self.assertIn("러버덕", "\n".join(t for _, t, _ in g.side_scene()) + si["npc"])
        g.side_seen()
        self.assertEqual(g.side_info()["phase"], "play")
        for _ in range(10):
            clk.t += 7
            g.pat()
        tick_for(g, clk, 2)
        self.assertEqual(g.side_info()["phase"], "done")
        gold = g.s["gold"]
        self.assertTrue(g.side_scene())
        g.side_seen()
        self.assertIn("duck_nest", g.s["inv"]["decos"])
        self.assertGreater(g.s["gold"], gold)
        self.assertEqual(g.story()["side_done"], ["e_duck"])
        g.story().update(side_t=0, side_at=-9)
        tick_for(g, clk, 2)
        self.assertIsNone(g.side_info())                          # CI 봇 편은 2장을 깨야
        cleared_upto(g, clk, 3)
        g.story().update(side_t=clk.t, side_at=1)
        tick_for(g, clk, 2)
        self.assertIsNone(g.side_info())                          # 방금 하나 끝냈으면 며칠 뒤에
        g.story()["phase"] = "wait"
        tick_for(g, clk, 2)
        self.assertIsNone(g.side_info())                          # 기다리는 주에도 최소 간격은 둔다
        g.story()["phase"] = "wait"
        g.story()["side_t"] = clk.t - D.SIDE_GAP_WAIT - 1
        tick_for(g, clk, 2)
        self.assertEqual(g.side_info()["ep"]["id"], "e_ci")       # 기다리는 주엔 짧은 간격으로

    def test_one_side_episode_per_two_chapters(self):
        g, clk = mk("side_one")
        hatch(g, clk)
        cleared_upto(g, clk, 3)
        tick_for(g, clk, 2)
        finish_side(g, clk)
        self.assertEqual(g.story()["side_at"], 3)
        for n in (3, 4):
            cleared_upto(g, clk, n)
            g.story().update(side_t=0, phase="wait")
            tick_for(g, clk, 2)
            self.assertIsNone(g.side_info(), n)                   # 챕터를 두 개 더 깨기 전엔 두 편째가 오지 않는다
        cleared_upto(g, clk, 5)
        g.story().update(side_t=0, phase="wait")
        tick_for(g, clk, 2)
        self.assertEqual(g.side_info()["ep"]["id"], "e_ci")

    def test_all_six_unlock_title_and_helpers_join_boss(self):
        g, clk = mk("side2")
        hatch(g, clk)
        cleared_upto(g, clk, 7)
        for _ in range(len(D.SIDE_EPISODES)):
            g.story().update(side_t=0, side_at=-9)        # 간격 건너뛰기
            tick_for(g, clk, 2)
            finish_side(g, clk)
        self.assertIn("side_all", g.s["ach"])
        hs = g.story_helpers()
        self.assertEqual([h["npc"] for h in hs], ["wolf", "pm", "owl"])     # 최근 셋
        fill_missions(g)
        tick_for(g, clk, 2)
        ready(g, D.CHAPTERS[7]["boss"]["lvl"] + 5)
        base_atk = P.monster_stats("sb08", D.CHAPTERS[7]["boss"]["lvl"], "story")["atk"] * D.GIMMICKS["sb08"]["tune"][1]
        self.assertTrue(g.start_story_boss())
        b = g.battle
        self.assertEqual(len(b["helpers"]), 3)
        self.assertAlmostEqual(b["mon"]["atk"], base_atk * (1 - 0.1), places=3)          # PM 고양이 guard
        ui = UI.PetUI(g)
        ui.boot_until = 0
        ui.tab = 6
        settle(g)
        screen = plain(ui.render(80, 24))
        self.assertIn("{o,o}", screen)                                                   # 부엉이가 무대에
        fight(g, clk, 3000)
        self.assertIn("의 지원!", "\n".join(t for _, t in g.log))

    def test_story_tab_side_line_and_key(self):
        g, clk = mk("side3")
        hatch(g, clk)
        cleared_upto(g, clk, 1)
        tick_for(g, clk, 2)
        ui = UI.PetUI(g)
        ui.boot_until = 0
        ui.tab = 6
        settle(g)
        g.story_mark_seen(1, "intro")
        screen = plain(ui.render(80, 24))
        self.assertIn("◇ SIDE", screen)
        self.assertIn("꽥의 의미", screen)
        self.assertTrue(ui._story_news())
        ui.key("e")
        self.assertEqual(ui.scene["part"], "side")
        self.assertIn("SIDE", plain(ui.render(80, 24)))
        ui.key("ESC")
        self.assertEqual(g.side_info()["phase"], "play")


class Choices(unittest.TestCase):
    def test_choice_in_epilogue_and_ending_follows_path(self):
        g, clk = mk("choice")
        hatch(g, clk)
        st = cleared_upto(g, clk, 2)
        lines = g.story_scene(1, "outro")
        self.assertEqual(lines[-1][0], "choice")
        ui = UI.PetUI(g)
        ui.boot_until = 0
        ui.tab = 6
        settle(g)
        ui._scene_start(1, "outro")
        ui.scene["idx"] = len(ui.scene["lines"]) - 1
        self.assertIn("위임장", plain(ui.render(80, 24)))
        self.assertEqual(ui._hint_pairs()[0][0], "1")
        ui.key("ENTER")
        ui.key("ENTER")
        self.assertEqual(ui.scene["lines"][ui.scene["idx"]][0], "choice")   # 고르기 전엔 안 넘어감
        ui.key("2")
        self.assertEqual(st["choices"], {"c02": "share"})
        self.assertEqual(ui.scene["lines"][ui.scene["idx"]][0], "pet")
        self.assertNotEqual(g.story_scene(1, "outro")[-1][0], "choice")    # 한 번만
        self.assertEqual(g.story_path(), "share")
        st["choices"].update(c04="now", c06="now")
        self.assertEqual(g.story_path(), "now")
        st["cleared"] = [c["id"] for c in D.CHAPTERS]
        final = [t for _, t, _ in g.story_scene(11, "outro")]
        self.assertIn(D.ENDINGS["now"][0][1].replace("{name}", g.p["name"]).split("은(는)")[1][:10], "\n".join(final))
        self.assertIn("TOKEN QUEST 시즌 1", final[-2])


class Debt(unittest.TestCase):
    def season_end(self, scope):
        g, clk = mk(scope)
        hatch(g, clk)
        st = cleared_upto(g, clk, len(D.CHAPTERS))
        st["ch"], st["phase"] = len(D.CHAPTERS) - 1, "end"
        return g, clk, st

    def test_pay_then_fight_then_weekly_interest(self):
        g, clk, st = self.season_end("debt1")
        info = g.debt_info()
        self.assertEqual(info["principal"], D.DEBT["base"])
        g.s["gold"] = info["cost"] * 20
        for _ in range(20):
            g.debt_pay()
        self.assertAlmostEqual(g.debt_info()["paid"], D.DEBT["max_pay"])      # 60% 까지만
        self.assertEqual(g.s["gold"], info["cost"] * 20 - info["cost"] * 12)
        self.assertEqual(g.stat("debt_paid"), info["cost"] * 12)
        ready(g, 100)
        g.p["form"] = "singularity"
        g.s["equip"]["weapon"] = {"id": "kb_green", "plus": 5}
        g.s["equip"]["armor"] = {"id": "robe_senior", "plus": 5}
        S = g.stats()
        g.p["hp"], g.p["mp"] = S["maxhp"], S["maxmp"]
        self.assertTrue(g.start_debt_boss())
        b = g.battle
        full = P.monster_stats("sb12", g.p["lvl"] + D.DEBT["lvl_add"], "story")["maxhp"] * D.GIMMICKS["sb12"]["tune"][0]
        self.assertAlmostEqual(b["mon"]["maxhp"] / full, 1 - D.DEBT["max_pay"], places=2)
        self.assertTrue(b["debt"])
        while g.battle:
            clk.t += 0.6
            g.tick()
            t2 = g.battle.get("tele") if g.battle else None
            if t2:
                g.gim_answer(t2["ans"])
        db = st["debt"]
        self.assertTrue(db["cleared"])
        self.assertEqual(db["weeks"], 1)
        self.assertEqual(st["phase"], "end")
        self.assertFalse(g.can_debt_boss()[0])
        self.assertTrue(g.last_summary[0]["debt"])
        clk.t += 7 * 86400                                                    # 다음 주: 이자
        tick_for(g, clk, 2)
        info = g.debt_info()
        self.assertFalse(info["cleared"])
        self.assertEqual(info["paid"], 0)
        self.assertEqual(info["principal"], int(D.DEBT["base"] * (1 + D.DEBT["growth"])))

    def test_story_tab_after_season(self):
        g, clk, st = self.season_end("debt2")
        ui = UI.PetUI(g)
        ui.boot_until = 0
        ui.tab = 6
        settle(g)
        for i in range(len(D.CHAPTERS)):
            g.story_mark_seen(i, "intro")
            g.story_mark_seen(i, "outro")
        st["pending"] = None
        screen = plain(ui.render(80, 24))
        self.assertIn("원금", screen)
        keys = [p[0] for p in ui._hint_pairs()]
        self.assertIn("P", keys)
        self.assertIn("B", keys)
        g.s["gold"] = 10 ** 7
        ui.key("p")
        self.assertGreater(g.debt_info()["paid"], 0)
        ready(g, 100)
        ui.key("b")
        self.assertEqual(ui.scene["part"], "debt")
        while ui.scene:
            ui.key("ESC")
        self.assertTrue(g.battle and g.battle.get("debt"))
        for W, H in ((40, 14), (60, 20), (80, 24), (120, 34)):
            for ln in ui.render(W, H):
                self.assertLessEqual(vlen(ln), W)


if __name__ == "__main__":
    unittest.main()


class OldSaves(unittest.TestCase):
    """v5 이전(지금 배포된) 저장을 그대로 불러와도 진행이 이어지고, 새 기능은 기본값으로 붙는다"""

    def test_pre_v5_story_loads_and_catches_up(self):
        scope = "old_v4"
        g, clk = mk(scope, persist=True)
        hatch(g, clk)
        st = cleared_upto(g, clk, 5)
        g.story_mark_seen(5, "intro")
        g.s["stats"]["quests"] = 777
        g.save(force=True)
        g.close()
        s = TS.load(scope)
        for k in ("heir", "sev", "side", "side_done", "choices", "debt"):
            s["story"].pop(k, None)                    # 예전 엔진은 이 값들을 모른다
        TS.dump(scope, s)
        g2 = P.PetGame(scope, clock=clk, seed=5, persist=True)
        st2 = g2.story()
        self.assertEqual((st2["ch"], len(st2["cleared"])), (5, 5))
        self.assertEqual((st2["side_done"], st2["choices"], st2["sev"], st2["heir"]), ([], {}, [], False))
        self.assertIsNone(st2["side"])
        tick_for(g2, clk, 3)
        self.assertEqual(g2.side_info()["ep"]["id"], "e_duck")         # 이미 깬 챕터만큼 조연이 차례로
        self.assertTrue(g2.story_scene(5, "intro"))
        self.assertEqual(g2.story_scene(1, "outro")[-1][0], "choice")  # 지난 챕터 선택은 다시 볼 때 고를 수 있다
        g2.close()

    def test_broken_new_fields_are_reset(self):
        scope = "old_bad"
        g, clk = mk(scope, persist=True)
        hatch(g, clk)
        g.save(force=True)
        g.close()
        s = TS.load(scope)
        s["story"].update(side="x", side_done="y", choices=[1], debt=5, sev={"a": 1}, heir="yes")
        TS.dump(scope, s)
        g2 = P.PetGame(scope, clock=clk, seed=5, persist=True)
        st = g2.story()
        self.assertIsNone(st["side"])
        self.assertIsNone(st["debt"])
        self.assertEqual((st["side_done"], st["choices"], st["sev"], st["heir"]), ([], {}, [], False))
        tick_for(g2, clk, 2)
        g2.close()
