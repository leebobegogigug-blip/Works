"""v5 세상이 이야기를 안다: 미션 한마디 · 던전 스토리 이벤트 · 실제 업무에 NPC 반응 · NPC 방문 · 커밋 조각 선반"""
import datetime
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_story as TS  # noqa: E402
from test_story import P, D, UI, vlen, mk, hatch, fill_missions, tick_for, ts, settle  # noqa: E402

EFFECTS = {"gold", "exp", "hp_pct", "mp_pct", "energy", "mood", "full", "health", "bugs", "item", "items", "mat", "buff",
           "status", "int", "cure", "ach", "fight"}


def setUpModule():
    TS.setUpModule()


def plain(lines):
    return re.sub(r"\x1b\[[0-9;]*m", "", "\n".join(lines))


def at_chapter(g, clk, i):
    st = g.story()
    st["cleared"] = [c["id"] for c in D.CHAPTERS[:i]]
    st["fast"] = st["rel"] = len(D.CHAPTERS)
    g._story_begin(i, clk.t, quiet=True)
    return st


class Data(unittest.TestCase):
    def test_mission_says_match_missions(self):
        for c in D.CHAPTERS:
            says = D.MISSION_SAYS[c["id"]]
            self.assertEqual(len(says), len(c["missions"]), c["id"])
            for npc, text in says:
                self.assertIn(npc, D.NPCS)
                self.assertLessEqual(vlen(D.NPCS[npc]["name"] + ": " + text), 78, text)

    def test_story_events_are_well_formed(self):
        ids = set()
        for c in D.CHAPTERS:
            evs = D.STORY_EVENTS[c["id"]]
            self.assertEqual(len(evs), 2, c["id"])
            for ev in evs:
                self.assertNotIn(ev["id"], ids)
                ids.add(ev["id"])
                self.assertEqual(len(ev["options"]), 2)
                for label, outs in ev["options"]:
                    self.assertAlmostEqual(sum(o[0] for o in outs), 1.0)
                    for _, eff, msg in outs:
                        self.assertLessEqual(set(eff), EFFECTS, ev["id"])
                        self.assertNotIn("{", msg)
                        if "fight" in eff:
                            self.assertIn(eff["fight"], D.MONSTERS)
                        if "item" in eff:
                            self.assertIn(eff["item"], D.ITEMS)
                        if "mat" in eff:
                            self.assertIn(eff["mat"][0], D.ITEMS)

    def test_reacts_and_visits_point_at_real_npcs(self):
        for kind, rows in D.WORLD_REACTS.items():
            for npc, need, text in rows:
                self.assertIn(npc, D.NPCS)
                self.assertTrue(0 <= need < len(D.CHAPTERS))
                text.format(n=1, m=1, cmp="", name="x")
        for npc, need, text in D.NPC_VISITS:
            self.assertIn(npc, D.NPCS)


class MissionSays(unittest.TestCase):
    def test_npc_speaks_when_mission_done(self):
        g, clk = mk("wm")
        hatch(g, clk)
        fill_missions(g)
        tick_for(g, clk, 2)
        says = [f"{D.NPCS[n]['name']}: " for n, _ in D.MISSION_SAYS["c01"][:3]]
        text = "\n".join(t for _, t in g.log) if hasattr(g, "log") else ""
        banners = [b[0] for b in g.banners] + ([g.banner[0]] if g.banner else [])
        joined = "\n".join(banners) + text
        self.assertTrue(any(s in joined for s in says), joined[:400])


class StoryEvents(unittest.TestCase):
    def expedition(self, g, zidx):
        g.p.update(energy=100.0, full=90.0, sleeping=False, sick=None)
        g.p["lvl"] = max(g.p["lvl"], D.ZONES[zidx]["lvl"] + 5)
        g.s["prog"]["cleared"] = [z["id"] for z in D.ZONES[:zidx]]
        S = g.stats()
        g.p["hp"], g.p["mp"] = S["maxhp"], S["maxmp"]
        self.assertTrue(g.start_expedition(zidx), g.can_depart())

    def test_events_show_once_in_the_chapter_zone(self):
        g, clk = mk("wse", seed=3)
        hatch(g, clk)
        st = at_chapter(g, clk, 2)
        self.expedition(g, 2)
        seen = []
        for _ in range(60000):
            clk.t += 1.0
            g.input_seen()
            g.tick()
            if g.event and g.event.get("story") and g.event["ev"]["id"] not in seen:
                seen.append(g.event["ev"]["id"])
                g.event_choose(0)
            if g.event and not g.event.get("result"):
                g.event_choose(0)
            if not g.expd:
                if len(seen) >= 2:
                    break
                self.expedition(g, 2)
        self.assertEqual(seen, ["s03a", "s03b"])
        self.assertEqual(st["sev"], ["s03a", "s03b"])
        self.assertIsNone(g._story_event_for(D.ZONES[2]))
        self.assertIsNone(g._story_event_for(D.ZONES[1]))          # 다른 지역에선 안 나온다

    def test_event_box_says_story(self):
        g, clk = mk("wsb")
        hatch(g, clk)
        at_chapter(g, clk, 0)
        self.expedition(g, 0)
        g._start_event(g._story_event_for(D.ZONES[0]), clk.t, story=True)
        ui = UI.PetUI(g)
        ui.boot_until = 0
        ui.tab = 1
        settle(g)
        screen = plain(ui.render(80, 24))
        self.assertIn("STORY", screen)
        self.assertIn("CI 봇", screen)


class WorldReacts(unittest.TestCase):
    def banners(self, g):
        return "\n".join([b[0] for b in g.banners] + ([g.banner[0]] if g.banner else []))

    def test_night_error_wakes_the_wolf_only_after_meeting(self):
        g, clk = mk("wr1", t=ts(2026, 9, 22, 2, 30))
        hatch(g, clk)
        g.signal("error", msg="boom")
        self.assertNotIn("온콜 늑대", self.banners(g))                 # 아직 못 만났다
        at_chapter(g, clk, 3)
        g.s["timers"]["react"] = 0
        g.signal("error", msg="boom")
        self.assertIn("온콜 늑대", self.banners(g))
        n = g.stat("reacts")
        g.signal("error", msg="boom again")                          # 25분 쉬는 시간
        self.assertEqual(g.stat("reacts"), n)

    def test_ratelimit_and_big_todo_and_compaction(self):
        g, clk = mk("wr2")
        hatch(g, clk)
        at_chapter(g, clk, 11)
        g.rng.random = lambda: 0.0                                   # 확률 대사도 꼭 나오게
        g.signal("error", msg="429 Too Many Requests")
        self.assertTrue(re.search("429|백오프", self.banners(g)))
        g.s["timers"]["react"] = 0
        g.signal("todos", sid="s", title="big", todos=[{"content": f"t{i}", "status": "pending"} for i in range(8)])
        self.assertIn("8개", self.banners(g))
        g.s["timers"]["react"] = 0
        g.signal("compacted", sid="s")
        self.assertTrue(re.search("128K|첫 번째 지시", self.banners(g)))

    def test_long_wait_compares_with_the_canyon(self):
        g, clk = mk("wr3")
        hatch(g, clk)
        at_chapter(g, clk, 11)
        g.rng.random = lambda: 0.0
        g.signal("busy", sid="b", title="t")
        clk.t += 50 * 60
        g.signal("idle", sid="b", title="t")
        self.assertTrue(re.search("50분", self.banners(g)))

    def test_friday_deploy_owl(self):
        g, clk = mk("wr4", t=ts(2026, 9, 25, 16, 0))                 # 금요일
        hatch(g, clk)
        at_chapter(g, clk, 7)
        g.signal("compose", chars=40, ctx="compose_deploy")
        self.assertIn("금요일", self.banners(g))


class Visits(unittest.TestCase):
    def test_met_npc_visits_home_and_is_drawn(self):
        g, clk = mk("wv")
        hatch(g, clk)
        at_chapter(g, clk, 4)
        g.rng.random = lambda: 0.1
        tm = g.s["timers"]
        tm["next_visit"] = clk.t - 1
        tm["next_home_event"] = clk.t + 9999
        g.input_seen()
        g.tick()
        self.assertIsNotNone(g.visitor)
        self.assertIn(g.visitor["npc"], D.NPCS)
        self.assertTrue(g.npc_met(dict((n, need) for n, need, _ in D.NPC_VISITS)[g.visitor["npc"]]))
        ui = UI.PetUI(g)
        ui.boot_until = 0
        settle(g)
        art = D.NPCS[g.visitor["npc"]]["art"]
        screen = plain(ui.render(80, 24))
        self.assertIn(art[1].strip(), screen)
        clk.t = g.visitor["until"] + 1
        g.tick()
        self.assertIsNone(g.visitor)


class Shelf(unittest.TestCase):
    def test_room_shows_commit_shards(self):
        g, clk = mk("wsh")
        hatch(g, clk)
        at_chapter(g, clk, 5)
        ui = UI.PetUI(g)
        ui.boot_until = 0
        settle(g)
        screen = plain(ui.render(80, 24))
        self.assertIn("[" + "▮" * 5 + "·" * 7 + "]", screen)
        for W, H in ((40, 14), (60, 20), (120, 34)):
            for ln in ui.render(W, H):
                self.assertLessEqual(vlen(ln), W)


if __name__ == "__main__":
    unittest.main()
