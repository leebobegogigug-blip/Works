"""시즌 2 1부 (S2-1): 챕터 13~16 콘텐츠 · 문제 은행 기믹 · 시즌 1 → 2 실제 전환 · 준비 중 대기 · 조연 · 반응"""
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
S2 = [i for i, c in enumerate(D.CHAPTERS) if P.season_of(i)["season"] == 2]


def setUpModule():
    TS.setUpModule()


def plain(lines):
    return re.sub(r"\x1b\[[0-9;]*m", "", "\n".join(lines))


def boss_ready(g, i):
    """시즌 2 에 온 펫답게: 전설 형태 · 보스보다 30 높은 레벨로 보스전 시작"""
    ready(g, D.CHAPTERS[i]["boss"]["lvl"] + 30)
    g.p["form"] = "singularity"
    S = g.stats()
    g.p["hp"], g.p["mp"] = S["maxhp"], S["maxmp"]
    return g.start_story_boss()


def keep_alive(g):
    """문제를 여러 개 보려고: 보스 · 펫 체력을 다시 채워 싸움이 끝나지 않게"""
    g.battle["mon"]["hp"] = g.battle["mon"]["maxhp"]
    g.p["hp"] = g.stats()["maxhp"]


def ui_for(g, tab=None):
    ui = UI.PetUI(g)
    ui.boot_until = 0
    if tab is not None:
        ui.tab = tab
    settle(g)
    return ui


class Data(unittest.TestCase):
    def test_season2_part1_is_in(self):
        self.assertEqual([D.CHAPTERS[i]["id"] for i in S2[:4]], ["c13", "c14", "c15", "c16"])
        self.assertEqual([P.ch_tag(i) for i in S2[:4]], ["S2 CH01", "S2 CH02", "S2 CH03", "S2 CH04"])
        for i in S2:
            c = D.CHAPTERS[i]
            self.assertIn(c["boss"]["mid"], D.GIMMICKS)
            self.assertEqual(len(D.MISSION_SAYS[c["id"]]), len(c["missions"]))
            self.assertEqual(len(D.STORY_EVENTS[c["id"]]), 2)
            z = D.ZONES[i]
            for mid in z["normals"] + [z["mini"], z["boss"]]:
                self.assertIn(mid, D.MONSTERS)
        # 시즌 2 는 시즌 1 끝 레벨(Lv.105 전후)에서 이어진다
        self.assertGreater(D.CHAPTERS[S2[0]]["boss"]["lvl"], D.CHAPTERS[S1 - 1]["boss"]["lvl"])
        self.assertGreaterEqual(D.ZONES[S2[0]]["base"], 100)

    def test_pools_are_fair(self):
        for mid in ("sb13", "sb14", "sb15", "sb16"):
            gd = D.GIMMICKS[mid]
            keys = [k for k, _ in gd["opts"]]
            pool = D.GIM_POOLS[gd["pool"]]
            self.assertGreaterEqual(len(pool), 8, mid)                    # 최근 3문제를 빼도 고를 게 남는다
            answers = {a for _, a, _ in pool}
            self.assertGreaterEqual(len(answers), 2, mid)                # 늘 같은 답이면 퍼즐이 아니다
            for q, a, why in pool:
                self.assertIn(a, keys)
                self.assertTrue(q and why)
                self.assertNotIn("{", q)
                self.assertLessEqual(vlen(gd["warn"].format(q=q, agenda="", n=0, clue="")), 120, q)   # 예고 상자 두 줄
        # 오토파일럿이 바라는 선택지('앞으로 전부 허락' · '바로 재시도')는 늘 오답
        self.assertNotIn("3", {a for _, a, _ in D.GIM_POOLS["approve"]})
        self.assertNotIn("1", {a for _, a, _ in D.GIM_POOLS["retry"]})
        # 숨은 지시: 예고가 선택을 시키면 늘 '출처 확인'
        for q, a, _ in D.GIM_POOLS["inject"]:
            self.assertEqual(a == "3", any(w in q for w in ("고를 것", "하세요", "할 것", "선택하시오", "정답")), q)

    def test_new_npcs_and_sides(self):
        for k in ("autopilot", "junior", "turtle"):
            self.assertIn(k, D.NPCS)
            self.assertTrue(all(vlen(ln) <= 11 for ln in D.NPCS[k]["art"]))
        s2 = [e for e in D.SIDE_EPISODES if P.season_of(e["need"])["season"] == 2]
        self.assertEqual([e["id"] for e in s2][:2], ["e_duck2", "e_turtle"])
        for e in s2:
            for iid in e["reward"].get("decos", []):
                self.assertIn(iid, D.DECO_ART)
        for iid in ("stamp_ring", "kb_noesc", "shell_pack", "kb_lowpro", "hood_techwear"):
            self.assertIn(D.ITEMS[iid]["kind"], D.EQUIP_SLOTS)


class PoolTelegraph(unittest.TestCase):
    def test_question_comes_from_pool_and_does_not_repeat(self):
        for i, mid in zip(S2[:4], ("sb13", "sb14", "sb15", "sb16")):
            g, clk = mk(f"s2pool{i}", seed=i)
            hatch(g, clk)
            at_chapter(g, clk, i)
            self.assertTrue(boss_ready(g, i))
            pool = D.GIM_POOLS[D.GIMMICKS[mid]["pool"]]
            seen = []
            for _ in range(4):
                tl = until_tele(g, clk)
                if tl is None:
                    break
                row = next(r for r in pool if D.GIMMICKS[mid]["warn"].format(q=r[0], agenda="", n=0, clue="") == tl["text"])
                self.assertEqual((tl["ans"], tl["why"]), (row[1], row[2]))
                seen.append(row[0])
                self.assertTrue(g.gim_answer(tl["ans"]))
                keep_alive(g)
            self.assertGreaterEqual(len(seen), 3, mid)
            self.assertEqual(len(seen[-3:]), len(set(seen[-3:])), seen)     # 최근 3문제는 겹치지 않는다

    def test_cron_meter_grows_on_wrong_and_hits_harder(self):
        i = S2[1]
        g, clk = mk("s2cron", seed=4)
        hatch(g, clk)
        at_chapter(g, clk, i)
        self.assertTrue(boss_ready(g, i))
        tl = until_tele(g, clk)
        a0 = g._gim_atk(g.battle)
        wrong = next(k for k, _ in tl["opts"] if k != tl["ans"])
        g.gim_answer(wrong)
        self.assertEqual(g.gim_info()["meter"]["value"], 2)                   # 덩굴이 하나 더 자랐다
        self.assertGreater(g._gim_atk(g.battle), a0)

    def test_retry_budget_runs_out(self):
        i = S2[2]
        g, clk = mk("s2retry", seed=5)
        hatch(g, clk)
        at_chapter(g, clk, i)
        self.assertTrue(boss_ready(g, i))
        for _ in range(3):
            tl = until_tele(g, clk)
            g.gim_answer(tl["ans"])
            keep_alive(g)
        self.assertEqual(g.gim_info()["meter"]["value"], 0)
        self.assertTrue(g.battle["gim"]["full"])

    def test_telegraph_box_shows_whole_question(self):
        i = S2[3]
        g, clk = mk("s2tele", seed=6)
        hatch(g, clk)
        at_chapter(g, clk, i)
        self.assertTrue(boss_ready(g, i))
        tl = until_tele(g, clk)
        gd = D.GIMMICKS["sb16"]
        longest = max(D.GIM_POOLS["inject"], key=lambda r: vlen(r[0]))
        tl["text"] = gd["warn"].format(q=longest[0], agenda="", n=0, clue="")
        ui = ui_for(g, tab=1)
        screen = plain(ui.render(80, 24))
        self.assertIn("출처를 확인한다", screen)
        self.assertIn("고를 것)", screen)                                     # 긴 문제도 끝까지 보인다


class RealTransition(unittest.TestCase):
    def test_season1_end_leads_into_real_season2(self):
        g, clk = mk("s2real")
        hatch(g, clk)
        st = g.story()
        st["cleared"] = [c["id"] for c in D.CHAPTERS[:S1]]
        st["ch"], st["phase"], st["pending"] = S1 - 1, "end", S1 - 1
        g.story_mark_seen(S1 - 1, "outro")
        tick_for(g, clk, 2)
        self.assertEqual((st["ch"], st["phase"]), (S2[0], "play"))
        self.assertEqual(g.story_released_n(clk.t), S2[0] + D.STORY_SEASONS[1]["fast"])     # 1 · 2장은 바로
        scene = g.story_scene(S2[0], "intro")
        self.assertIn("오토파일럿", "\n".join(t for _, t, _ in scene) + "".join(n for n, _, _ in scene))
        # 1부 마지막 장(4장): 업적 · 장비. 5장 공개일 전이면 기다린다
        st["cleared"] = [c["id"] for c in D.CHAPTERS[:S2[3]]]
        st["rel"] = S2[3] + 1
        g._story_begin(S2[3], clk.t, quiet=True)
        g._story_clear(S2[3], clk.t)
        self.assertEqual((st["ch"], st["phase"]), (S2[3], "wait"))
        self.assertIn("story_s2_4", g.s["ach"])
        self.assertTrue(any(it["id"] == "shell_pack" for it in g.s["inv"]["gear"]))

    def test_last_chapter_in_this_version_waits_as_coming_soon(self):
        g, clk = mk("s2soon")
        hatch(g, clk)
        st = g.story()
        last = S2[-1]
        st["cleared"] = [c["id"] for c in D.CHAPTERS[:last]]
        st["fast"] = st["rel"] = len(D.CHAPTERS)
        g._story_begin(last, clk.t, quiet=True)
        g._story_clear(last, clk.t)
        g.story_mark_seen(last, "outro")
        tick_for(g, clk, 2)
        self.assertEqual((st["ch"], st["phase"]), (last, "wait"))
        clk.t += 30 * 86400
        tick_for(g, clk, 2)
        self.assertEqual(st["phase"], "wait")                                # 몇 주가 지나도 없는 장은 열리지 않는다
        ui = ui_for(g, tab=6)
        for i in range(len(D.CHAPTERS)):
            g.story_mark_seen(i, "intro")
        screen = plain(ui.render(80, 24))
        self.assertIn("준비 중", screen)
        self.assertIn(f"Esc 조각 #{P.ch_no(last)}", screen)                  # 조각 번호는 시즌 안에서 센다


class Season2Cast(unittest.TestCase):
    def test_duck_speaks_again_and_turtle_joins(self):
        g, clk = mk("s2side")
        hatch(g, clk)
        st = g.story()
        st["side_done"] = [e["id"] for e in D.SIDE_EPISODES if P.season_of(e["need"])["season"] == 1]
        st.update(cleared=[c["id"] for c in D.CHAPTERS[:S2[0] + 1]], fast=len(D.CHAPTERS), rel=len(D.CHAPTERS),
                  side_t=0, side_at=-9)
        g._story_begin(S2[1], clk.t, quiet=True)
        tick_for(g, clk, 2)
        self.assertEqual(g.side_info()["ep"]["id"], "e_duck2")
        finish_side(g, clk)
        self.assertIn("duck_mic", g.s["inv"]["decos"])
        st["cleared"] = [c["id"] for c in D.CHAPTERS[:S2[3] + 1]]
        st.update(side_t=0, ch=S2[3], phase="wait")
        tick_for(g, clk, 2)
        self.assertEqual(g.side_info()["ep"]["id"], "e_turtle")
        finish_side(g, clk)
        self.assertEqual([h["npc"] for h in g.story_helpers()][-2:], ["duck", "turtle"])

    def test_abort_reaction_changes_after_season2_starts(self):
        g, clk = mk("s2abort")
        hatch(g, clk)
        g.rng.random = lambda: 0.0
        at_chapter(g, clk, S1 - 1)
        for _ in range(12):
            g.s["timers"]["react"] = 0
            g.signal("abort", sid="s")
        text = "\n".join([b[0] for b in g.banners] + ([g.banner[0]] if g.banner else []))
        self.assertNotIn("오토파일럿", text)                              # 아직 못 만났다
        g2, clk2 = mk("s2abort2")
        hatch(g2, clk2)
        g2.rng.random = lambda: 0.0
        at_chapter(g2, clk2, S2[0])
        said = set()
        for _ in range(40):
            g2.s["timers"]["react"] = 0
            g2.banners.clear()
            g2.banner = None
            g2.signal("abort", sid="s")
            said |= {b[0] for b in g2.banners} | ({g2.banner[0]} if g2.banner else set())
        self.assertTrue(any("Esc" in t or "오토파일럿" in t for t in said), said)


if __name__ == "__main__":
    unittest.main()
