"""v5 챕터 보스 기믹: 예고 → 대응 창 → 결과 · 보호막 · 회고(패배 보정) · 계기 · 완벽 대응 · 화면"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_story as TS  # noqa: E402  (같은 임시 저장 폴더 · 시계 · 도우미를 쓴다)
from test_story import P, D, UI, vlen, mk, hatch, fill_missions, tick_for, ready, fight  # noqa: E402

EFFECT_KEYS = {"stun", "dmg", "pct", "def_down", "heal", "mp", "hit", "sleep", "pstun", "confuse", "poison", "wipe",
               "boss_heal", "boss_atk", "mp_drain"}


def setUpModule():
    TS.setUpModule()


def at_chapter(g, clk, i):
    """챕터 i(0부터)의 보스 신호가 잡힌 상태로 건너뛴다"""
    st = g.story()
    st["cleared"] = [c["id"] for c in D.CHAPTERS[:i]]
    st["fast"] = st["rel"] = len(D.CHAPTERS)
    g._story_begin(i, clk.t, quiet=True)
    fill_missions(g)
    tick_for(g, clk, 2)
    assert st["phase"] == "boss"


def until_tele(g, clk, limit=400):
    for _ in range(limit):
        if g.battle and g.battle.get("tele"):
            return g.battle["tele"]
        if not g.battle:
            return None
        clk.t += 0.5
        g.tick()
    return None


class Data(unittest.TestCase):
    def test_every_chapter_boss_has_a_gimmick(self):
        for c in D.CHAPTERS:
            gd = D.GIMMICKS.get(c["boss"]["mid"])
            self.assertIsNotNone(gd, c["id"])
            keys = [k for k, _ in gd["opts"]]
            self.assertGreaterEqual(len(keys), 2, c["id"])
            self.assertEqual(len(keys), len(set(keys)))
            for k in keys:
                self.assertIn(k, ("a", "d", "1", "2", "3"))
            if not (gd.get("quiz") or gd.get("clue")):
                self.assertIn(gd["ans"], keys, c["id"])
            for part in ("good", "bad"):
                self.assertLessEqual(set(gd.get(part) or {}), EFFECT_KEYS, (c["id"], part))
            if isinstance(gd["ng"], dict):
                self.assertLessEqual(set(gd["ng"]), set(keys) - {gd["ans"]}, c["id"])
            gd["warn"].format(agenda="x", n=1, q="x", clue="x")        # 자리 이름 오타 없음
            mt = gd.get("meter")
            if mt:
                self.assertIn("label", mt)
                if mt.get("goal") is not None:
                    self.assertIn("full_text", mt)
                    self.assertLessEqual(set(mt.get("full") or {}), EFFECT_KEYS)
            h, a = gd.get("tune", (1.0, 1.0))
            self.assertTrue(0.3 <= h <= 2.0 and 0.3 <= a <= 2.0)
            self.assertTrue(0.0 < gd["auto"] < 1.0)

    def test_clues_answerable(self):
        keys = {k for k, _ in D.GIMMICKS["sb09"]["opts"]}
        self.assertTrue(all(a in keys for _, a in D.ZERO_DAY_CLUES))
        self.assertEqual({a for _, a in D.ZERO_DAY_CLUES}, keys)      # 셋 다 정답이 되는 단서가 있다


class Telegraph(unittest.TestCase):
    def fight_at(self, i, lvl_off=10, seed=1):
        g, clk = mk(seed=seed)
        hatch(g, clk)
        at_chapter(g, clk, i)
        ready(g, D.CHAPTERS[i]["boss"]["lvl"] + lvl_off)
        self.assertTrue(g.start_story_boss())
        return g, clk

    def test_first_telegraph_at_round_two_pauses_rounds(self):
        g, clk = self.fight_at(3)
        tl = until_tele(g, clk)
        self.assertIsNotNone(tl)
        b = g.battle
        self.assertEqual(b["round"], 2)
        self.assertEqual(b["gim"]["n"], 1)
        r = b["round"]
        clk.t += 1.0
        g.tick()                                    # 대응 창이 열려 있는 동안 라운드는 멈춘다
        self.assertEqual(b["round"], r)
        self.assertFalse(g.battle_action("attack"))
        self.assertFalse(g.gim_answer("9"))         # 없는 선택지
        self.assertTrue(g.gim_answer(tl["ans"]))
        self.assertIsNone(b["tele"])
        self.assertEqual((b["gim"]["ok"], b["gim"]["hist"]), (1, [True]))
        self.assertGreaterEqual(b["mon"]["st"].get("stun", 0), 2)   # 크론잡: 방해 금지 모드 → 2턴 멈춤

    def test_wrong_answer_hurts(self):
        g, clk = self.fight_at(3)
        tl = until_tele(g, clk)
        hp = g.p["hp"]
        wrong = next(k for k, _ in tl["opts"] if k != tl["ans"])
        self.assertTrue(g.gim_answer(wrong))
        self.assertLess(g.p["hp"], hp)                                # 알림 폭탄 (즉시 피해)
        self.assertTrue(g.battle["pst"].get("sleep"))                 # + 비몽사몽
        self.assertEqual(g.battle["gim"]["hist"], [False])

    def test_window_timeout_auto_resolves(self):
        for p_auto, want in ((1.0, True), (0.0, False)):
            g, clk = self.fight_at(1)
            tl = until_tele(g, clk)
            tl["auto_p"] = p_auto
            clk.t = tl["until"] + 0.1
            g.tick()
            self.assertIsNone(g.battle["tele"])
            self.assertEqual(g.battle["gim"]["hist"], [want])

    def test_watching_player_gets_longer_window(self):
        g, clk = self.fight_at(1)
        g.last_input = clk.t - 3600               # 자리 비움
        tl = until_tele(g, clk)
        self.assertAlmostEqual(tl["until"] - tl["t0"], D.GIM_WINDOW["away"])
        g, clk = self.fight_at(1)
        tl = None
        for _ in range(400):
            g.input_seen()
            clk.t += 0.5
            g.tick()
            if g.battle.get("tele"):
                tl = g.battle["tele"]
                break
        self.assertAlmostEqual(tl["until"] - tl["t0"], D.GIM_WINDOW["watch"])

    def test_quiz_and_clue_answers_follow_the_question(self):
        g, clk = self.fight_at(7)                   # 스핑크스: O/X 퀴즈
        tl = until_tele(g, clk)
        q = next(x for x in D.QUIZ if x[0] in tl["text"])
        self.assertEqual(tl["ans"], "1" if q[1] else "2")
        self.assertTrue(tl["why"])
        g, clk = self.fight_at(8)                   # 가고일: 단서
        tl = until_tele(g, clk)
        clue = next(x for x in D.ZERO_DAY_CLUES if x[0] in tl["text"])
        self.assertEqual(tl["ans"], clue[1])

    def test_shield_caps_damage_per_round_but_not_counters(self):
        g, clk = self.fight_at(6, lvl_off=60)       # 한참 센 펫
        b = g.battle
        m = b["mon"]
        hp0 = m["hp"]
        g.battle_round(("skill", "rust"))
        self.assertGreaterEqual(m["hp"], hp0 - int(m["maxhp"] * D.STORY["shield"]))
        self.assertGreater(m["hp"], 0)
        tl = until_tele(g, clk)
        before = m["hp"]
        g.gim_answer(tl["ans"])                     # 칼퇴 → 반격은 보호막을 뚫는다 (def_down + 회복이라 피해 없음)
        g2, clk2 = self.fight_at(1, lvl_off=60)     # 너구리: 끊기 = 강공격
        tl2 = until_tele(g2, clk2)
        m2 = g2.battle["mon"]
        before2 = m2["hp"]
        g2.gim_answer(tl2["ans"])
        self.assertGreater(before2 - m2["hp"], int(m2["maxhp"] * D.STORY["shield"]))
        self.assertLessEqual(m["hp"], before)

    def test_story_enrage_is_capped(self):
        g, clk = self.fight_at(4, lvl_off=60)       # 회의 주재자 = 데드라인 가속
        b = g.battle
        for _ in range(30):
            b.pop("tele", None)
            b["tele"] = None
            g._enemy_act(g.stats(), b)
        self.assertEqual(b["enrage"], 8)


class RetroAndMeters(unittest.TestCase):
    def test_retro_weakens_boss_and_raises_auto(self):
        g, clk = mk()
        hatch(g, clk)
        at_chapter(g, clk, 5)
        ready(g, D.CHAPTERS[5]["boss"]["lvl"])
        self.assertTrue(g.start_story_boss())
        hp_full, atk_full = g.battle["mon"]["maxhp"], g.battle["mon"]["atk"]
        g.story_retreat()
        fight(g, clk)
        g.story()["fails"] = 3
        ready(g, D.CHAPTERS[5]["boss"]["lvl"])
        self.assertTrue(g.start_story_boss())
        m = g.battle["mon"]
        self.assertAlmostEqual(m["maxhp"] / hp_full, 1 - 3 * D.GIM_RETRO["hp"], places=2)
        self.assertAlmostEqual(m["atk"] / atk_full, 1 - 3 * D.GIM_RETRO["atk"], places=3)
        tl = until_tele(g, clk)
        self.assertAlmostEqual(tl["auto_p"], D.GIMMICKS["sb06"]["auto"] + 3 * D.GIM_RETRO["auto"])

    def test_losing_counts_as_retro(self):
        g, clk = mk()
        hatch(g, clk)
        fill_missions(g)
        tick_for(g, clk, 2)
        ready(g, lvl=1)
        self.assertTrue(g.start_story_boss())
        fight(g, clk, 3000)
        self.assertEqual(g.story()["fails"], 1)
        self.assertIn("회고 1번", g.last_summary[0]["reason"])

    def test_migration_meter_completes_once(self):
        g, clk = mk()
        hatch(g, clk)
        at_chapter(g, clk, 2)
        ready(g, D.CHAPTERS[2]["boss"]["lvl"] + 40)
        self.assertTrue(g.start_story_boss())
        b = g.battle
        self.assertEqual(b["gim"]["meter"], 67)
        m = b["mon"]
        hits = 0
        for _ in range(3):
            tl = until_tele(g, clk)
            m["hp"] = m["maxhp"]
            g.gim_answer(tl["ans"])
            hits += 1
        self.assertEqual(b["gim"]["meter"], 100)
        self.assertTrue(b["gim"]["full"])
        self.assertLessEqual(m["hp"], m["maxhp"] - int(m["maxhp"] * 0.22))    # 완료 = 최대 HP 22% 피해
        tl = until_tele(g, clk)
        hp = m["hp"]
        g.gim_answer(tl["ans"])
        self.assertEqual(b["gim"]["meter"], 100)                               # 한 번만
        self.assertEqual(m["hp"], hp)

    def test_interest_grows_every_round_and_resets(self):
        g, clk = mk()
        hatch(g, clk)
        at_chapter(g, clk, 11)
        ready(g, D.CHAPTERS[11]["boss"]["lvl"] + 40)
        self.assertTrue(g.start_story_boss())
        b = g.battle
        tl = until_tele(g, clk)
        self.assertEqual(b["gim"]["meter"], 2)       # 2라운드 = 이자 2겹
        self.assertGreater(g._gim_atk(b), 1.0)
        self.assertIn("2겹", tl["text"])
        g.gim_answer(tl["ans"])
        self.assertEqual(b["gim"]["meter"], 0)
        self.assertEqual(g._gim_atk(b), 1.0)
        tl = until_tele(g, clk)
        g.gim_answer("1")                            # 나중에 갚는다 → 이자 +2
        self.assertEqual(b["gim"]["meter"], 3 + 2)


class PerfectClear(unittest.TestCase):
    def test_perfect_bonus_and_achievement(self):
        g, clk = mk()
        hatch(g, clk)
        for i in range(3):
            at_chapter(g, clk, i)
            ready(g, D.CHAPTERS[i]["boss"]["lvl"] + 30)
            self.assertTrue(g.start_story_boss())
            while g.battle:
                tl = until_tele(g, clk, 2000)
                if tl:
                    g.gim_answer(tl["ans"])
            s = g.last_summary[0]
            self.assertTrue(s["win"])
            self.assertTrue(s["perfect"], s)
            self.assertEqual(s["gim"][0], s["gim"][1])
        self.assertEqual(g.stat("gim_perfect"), 3)
        self.assertIn("gim_perfect3", g.s["ach"])
        self.assertGreaterEqual(g.stat("gim_ok"), 6)


class GimmickUI(unittest.TestCase):
    SIZES = ((40, 14), (48, 16), (60, 20), (80, 24), (120, 34))

    def test_telegraph_renders_and_keys_answer(self):
        for ch in range(len(D.CHAPTERS)):
            g, clk = mk("ui_gim")
            hatch(g, clk)
            at_chapter(g, clk, ch)
            ready(g, D.CHAPTERS[ch]["boss"]["lvl"] + 10)
            ui = UI.PetUI(g)
            ui.boot_until = 0
            ui.tab = 6
            g.input_seen()
            self.assertTrue(g.start_story_boss())
            tl = until_tele(g, clk)
            self.assertIsNotNone(tl, ch)
            for W, H in self.SIZES:
                lines = ui.render(W, H)
                self.assertLessEqual(len(lines), H)
                for ln in lines:
                    self.assertLessEqual(vlen(ln), W, (ch, W, H, ln))
            screen = re.sub(r"\x1b\[[0-9;]*m", "", "\n".join(ui.render(80, 24)))
            self.assertIn("TELEGRAPH", screen)
            self.assertIn(D.GIMMICKS[D.CHAPTERS[ch]["boss"]["mid"]]["name"], screen)
            pairs = ui._hint_pairs()
            self.assertEqual([p[0] for p in pairs[:len(tl["opts"])]], [k.upper() for k, _ in tl["opts"]])
            tab = ui.tab
            ui.key(tl["opts"][0][0])                 # 숫자 키도 탭 전환이 아니라 대응
            self.assertEqual(ui.tab, tab)
            self.assertIsNone(g.battle["tele"])


if __name__ == "__main__":
    unittest.main()
