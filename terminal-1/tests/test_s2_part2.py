"""시즌 2 2부 (S2-2): 5~8장 · 동료 편성과 특기 · 거울 기믹 · 코드 리뷰 미니게임 · 벌집 반응 · 고슴도치 · 주니어"""
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
S1_SIDES = [e["id"] for e in D.SIDE_EPISODES if P.season_of(e["need"])["season"] == 1]


def setUpModule():
    TS.setUpModule()


def plain(lines):
    return re.sub(r"\x1b\[[0-9;]*m", "", "\n".join(lines))


def with_sides(g, clk, ch, sides):
    """챕터 ch 의 보스 신호가 잡힌 상태 + 사이드 에피소드 sides 를 끝낸 상태"""
    at_chapter(g, clk, ch)
    st = g.story()
    st["side_done"] = list(sides)
    return st


def boss(g, i):
    ready(g, D.CHAPTERS[i]["boss"]["lvl"] + 30)
    g.p["form"] = "singularity"
    S = g.stats()
    g.p["hp"], g.p["mp"] = S["maxhp"], S["maxmp"]
    return g.start_story_boss()


def ui_for(g, tab=6):
    ui = UI.PetUI(g)
    ui.boot_until = 0
    ui.tab = tab
    settle(g)
    return ui


class Data(unittest.TestCase):
    def test_part2_is_in(self):
        ids = [c["id"] for c in D.CHAPTERS]
        self.assertEqual(ids[S1 + 4:S1 + 8], ["c17", "c18", "c19", "c20"])
        self.assertEqual(D.CHAPTERS[CH["c19"]]["boss"].get("phase2"), 0.5)          # 반전 장은 2페이즈
        for mid in ("sb17", "sb18", "sb20"):
            gd = D.GIMMICKS[mid]
            pool = D.GIM_POOLS[gd["pool"]]
            keys = [k for k, _ in gd["opts"]]
            self.assertGreaterEqual(len(pool), 8, mid)
            self.assertGreaterEqual(len({a for _, a, _ in pool}), 2, mid)
            for q, a, why in pool:
                self.assertIn(a, keys)
                self.assertLessEqual(vlen(gd["warn"].format(q=q, agenda="", n=0, clue="")), 120, q)
        self.assertTrue(D.GIMMICKS["sb19"].get("mirror"))
        self.assertIn("hedgehog", D.NPCS)

    def test_every_counter_is_a_real_boss_kind(self):
        tags = {gd.get("tag") or gd.get("pool") for gd in D.GIMMICKS.values()} - {None}
        self.assertLessEqual(tags, set(D.GIM_TAGS))
        for e in D.SIDE_EPISODES:
            self.assertTrue(e["help"].get("counters"), e["id"])
            self.assertLessEqual(set(e["help"]["counters"]), set(D.GIM_TAGS), e["id"])
        # 시즌 2 보스마다 특기가 맞는 동료가 적어도 하나 (그 보스 전에 사귈 수 있는)
        for i in range(S1, len(D.CHAPTERS)):
            tag = D.GIMMICKS[D.CHAPTERS[i]["boss"]["mid"]].get("tag") or D.GIMMICKS[D.CHAPTERS[i]["boss"]["mid"]].get("pool")
            pros = [e for e in D.SIDE_EPISODES if tag in e["help"]["counters"] and e["need"] < i]
            self.assertTrue(pros, (D.CHAPTERS[i]["id"], tag))

    def test_code_reviews(self):
        self.assertGreaterEqual(len(D.CODE_REVIEWS), 15)
        for lines, ans, why in D.CODE_REVIEWS:
            self.assertEqual(len(lines), 3)
            self.assertIn(ans, ("1", "2", "3"))
            self.assertTrue(why)
            for ln in lines:
                self.assertLessEqual(vlen(ln), 44, ln)
        for k in ("1", "2", "3"):
            self.assertGreaterEqual(sum(1 for _, a, _ in D.CODE_REVIEWS if a == k), 5, k)     # 번호가 한쪽으로 쏠리지 않게


class Party(unittest.TestCase):
    def test_default_is_recent_three_and_toggle(self):
        g, clk = mk("pty1")
        hatch(g, clk)
        st = with_sides(g, clk, CH["c14"], S1_SIDES)
        self.assertIsNone(st["party"])
        self.assertEqual([h["eid"] for h in g.story_helpers()], S1_SIDES[-3:])        # 기본 = 최근 셋 (시즌 1 그대로)
        self.assertTrue(g.party_toggle("e_pm"))                                     # 빼기
        self.assertEqual([h["eid"] for h in g.story_helpers()], [x for x in S1_SIDES[-3:] if x != "e_pm"])
        self.assertTrue(g.party_toggle("e_duck"))                                   # 넣기
        self.assertFalse(g.party_toggle("e_ci"))                                    # 셋이 꽉 찼다
        self.assertEqual(len(g.story_helpers()), 3)
        self.assertFalse(g.party_toggle("e_nope"))
        for eid in [h["eid"] for h in g.story_helpers()]:
            g.party_toggle(eid)
        self.assertEqual((st["party"], g.story_helpers()), ([], []))                 # 아무도 안 데려가기도 된다

    def test_suggest_puts_the_specialist_first(self):
        g, clk = mk("pty2")
        hatch(g, clk)
        with_sides(g, clk, CH["c14"], S1_SIDES)                                     # 크론 정글 → 온콜 늑대
        opts = {o["eid"]: o for o in g.party_options()}
        self.assertTrue(opts["e_wolf"]["match"])
        self.assertFalse(opts["e_pm"]["match"])
        g.party_suggest()
        self.assertEqual(g.story_helpers()[0]["eid"], "e_wolf")
        self.assertEqual(len(g.story_helpers()), 3)

    def test_specialist_raises_auto_answer_only_in_season2(self):
        for ch, pro in ((CH["c14"], "온콜 늑대"), (3, None)):                         # 시즌 1 보스엔 특기가 없다
            g, clk = mk(f"pty3_{ch}", seed=2)
            hatch(g, clk)
            st = with_sides(g, clk, ch, S1_SIDES)
            st["party"] = ["e_wolf"]
            self.assertTrue(boss(g, ch))
            tl = until_tele(g, clk)
            gd = D.GIMMICKS[D.CHAPTERS[ch]["boss"]["mid"]]
            base = min(0.95, gd["auto"] + g.rnd_value("auto") / 100)
            self.assertEqual(tl["pro"], pro)
            self.assertAlmostEqual(tl["auto_p"], base + (D.PARTY_BONUS if pro else 0.0))
            if pro:
                self.assertIn(f"{pro} ★", plain(ui_for(g, tab=6).render(80, 24)))    # 예고 상자 아래에 누가 거드는지

    def test_sanitize_party(self):
        scope = "pty4"
        g, clk = mk(scope, persist=True)
        hatch(g, clk)
        st = g.story()
        st["side_done"] = S1_SIDES[:3]
        st["party"] = ["e_ci", "e_ci", "e_owl", "zzz", 7]
        g.save(force=True)
        g.close()
        g2 = P.PetGame(scope, clock=clk, seed=2, persist=True)
        self.assertEqual(g2.story()["party"], ["e_ci"])                              # 안 끝낸 조연 · 중복 · 이상한 값은 빠진다
        g2.close()

    def test_party_screen(self):
        g, clk = mk("pty5")
        hatch(g, clk)
        with_sides(g, clk, CH["c14"], S1_SIDES)
        for i in range(len(D.CHAPTERS)):
            g.story_mark_seen(i, "intro")
        ui = ui_for(g)
        screen = plain(ui.render(80, 24))
        self.assertIn("PARTY", screen)
        self.assertIn("F", [p[0] for p in ui._hint_pairs()])
        ui.key("f")
        self.assertEqual(ui.overlay["kind"], "party")
        screen = plain(ui.render(80, 24))
        self.assertIn("★ 이번 보스", screen)
        ui.key("r")
        self.assertEqual(g.story_helpers()[0]["eid"], "e_wolf")
        ui.key("1")                                                                 # 1번(러버덕) 넣기 · 빼기
        for W, H in ((60, 20), (80, 24), (120, 34)):
            for ln in ui.render(W, H):
                self.assertLessEqual(vlen(ln), W)
        ui.key("ESC")
        self.assertIsNone(ui.overlay)

    def test_no_helpers_no_party(self):
        g, clk = mk("pty6")
        hatch(g, clk)
        at_chapter(g, clk, 2)
        ui = ui_for(g)
        ui.key("f")
        self.assertIsNone(ui.overlay)
        self.assertNotIn("F", [p[0] for p in ui._hint_pairs()])


class Mirror(unittest.TestCase):
    def test_mirror_copies_my_skills(self):
        i = CH["c19"]
        g, clk = mk("mir", seed=5)
        hatch(g, clk)
        at_chapter(g, clk, i)
        self.assertTrue(boss(g, i))
        names = {D.SKILLS[s]["name"]: s for s in g.available_skills()}
        for _ in range(3):
            tl = until_tele(g, clk)
            sk = next(n for n in names if f"'{n}'" in tl["text"])
            self.assertEqual(tl["ans"], D.MIRROR_ANS[names[sk]])
            self.assertNotIn("을(를)", tl["text"])                                  # 조사도 맞춰 붙인다
            g.gim_answer(tl["ans"])
            g.battle["mon"]["hp"] = g.battle["mon"]["maxhp"]
            g.p["hp"] = g.stats()["maxhp"]

    def test_kills_in_the_twist(self):
        g, clk = mk("mir2")
        hatch(g, clk)
        g.s["stats"]["kills"] = 12345
        text = "\n".join(t for _, t, _ in g.story_scene(CH["c19"], "intro"))
        self.assertIn("12,345마리", text)
        self.assertNotIn("{", text)


class Review(unittest.TestCase):
    def test_review_round(self):
        g, clk = mk("rev")
        hatch(g, clk)
        g.p["energy"] = 100.0
        self.assertTrue(g.start_minigame("review"))
        ui = ui_for(g, tab=0)
        lines, ans, _ = D.CODE_REVIEWS[g.mg["qs"][0]]
        self.assertIn(lines[0].strip(), plain(ui.render(80, 24)))
        self.assertIn("1-3", [p[0] for p in ui._hint_pairs()])
        for k in range(5):
            q = D.CODE_REVIEWS[g.mg["qs"][g.mg["idx"]]]
            g.minigame_key(q[1])
            self.assertTrue(g.mg["ok"])
            self.assertIn(q[2], plain(ui.render(80, 24)))                           # 풀이를 보여 준다
            g.minigame_key("ENTER")
        self.assertEqual(g.mg["phase"], "result")
        self.assertIn("review_perfect", g.s["ach"])

    def test_timeout_counts_wrong(self):
        g, clk = mk("rev2")
        hatch(g, clk)
        g.p["energy"] = 100.0
        g.start_minigame("review")
        clk.t += D.REVIEW_TIME + 0.5
        g.tick()
        self.assertEqual(g.mg["hist"], [False])
        g.minigame_key("9")                                                         # 없는 키는 무시
        self.assertEqual(g.mg["phase"], "show")


class Cast(unittest.TestCase):
    def test_hedgehog_and_junior_sides(self):
        g, clk = mk("s22side")
        hatch(g, clk)
        st = g.story()
        before = [e["id"] for e in D.SIDE_EPISODES if e["id"] not in ("e_hedgehog", "e_junior")]
        st.update(side_done=before, fast=len(D.CHAPTERS), rel=len(D.CHAPTERS), side_t=0, side_at=-9,
                  cleared=[c["id"] for c in D.CHAPTERS[:CH["c17"] + 1]])
        g._story_begin(CH["c18"], clk.t, quiet=True)
        tick_for(g, clk, 2)
        self.assertEqual(g.side_info()["ep"]["id"], "e_hedgehog")
        finish_side(g, clk)
        self.assertIn("yes_stamp", g.s["inv"]["decos"])
        st.update(side_t=0, cleared=[c["id"] for c in D.CHAPTERS[:CH["c20"] + 1]], ch=CH["c20"], phase="wait")
        tick_for(g, clk, 2)
        self.assertEqual(g.side_info()["ep"]["id"], "e_junior")
        scene = "\n".join(t for _, t, _ in g.side_scene())
        self.assertIn("여쭤볼", scene)
        finish_side(g, clk)
        self.assertIn("ask_sign", g.s["inv"]["decos"])

    def test_hive_reaction(self):
        g, clk = mk("hive")
        hatch(g, clk)
        at_chapter(g, clk, CH["c20"])
        g.rng.random = lambda: 0.0
        said = set()
        for k in range(12):
            g.s["timers"]["react"] = 0
            g.banners.clear()
            g.banner = None
            for j in range(3):
                g.signal("sub_start", sid=f"a{k}{j}", agent="general")
            said |= {b[0] for b in g.banners} | ({g.banner[0]} if g.banner else set())
            g.allies.clear()
        self.assertTrue(any("서브에이전트가" in t or "에이전트 3명" in t for t in said), said)


if __name__ == "__main__":
    unittest.main()
