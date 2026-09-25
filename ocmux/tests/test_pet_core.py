import os
import sys
import json
import shutil
import tempfile
import unittest
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))  # 저장소 루트
TMP = tempfile.mkdtemp()
os.environ["LOCALAPPDATA"] = TMP
import ocmux_pet as P  # noqa: E402


def setUpModule():
    # 여러 테스트 파일을 한 번에 돌려도 저장 폴더가 섞이지 않게: 이 파일의 테스트는 이 파일의 임시 폴더만 쓴다
    os.environ["LOCALAPPDATA"] = TMP


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def mk(scope="t", t=None, persist=False, seed=1):
    clk = Clock(t or datetime.datetime(2026, 9, 21, 10, 0).timestamp())
    return P.PetGame(scope, "토큰이", clock=clk, seed=seed, persist=persist), clk


def hatch(g, clk):
    clk.t += 200
    g.signal("busy", sid="a", title="t", agent="build")
    g.signal("idle", sid="a", title="t")
    g.tick()
    assert not g.is_egg()


class EngineTests(unittest.TestCase):
    def test_hatch_and_needs(self):
        g, clk = mk()
        self.assertTrue(g.is_egg())
        g.tick()
        self.assertTrue(g.is_egg())
        hatch(g, clk)
        self.assertEqual(g.p["form"], "bit")
        self.assertIn("hatch", g.s["ach"])
        f0 = g.p["full"]
        for _ in range(720):   # 1 hour
            clk.t += 5
            g.input_seen()
            g.tick()
        self.assertLess(g.p["full"], f0)

    def test_feed_clean_pat_calls(self):
        g, clk = mk()
        hatch(g, clk)
        g.p["full"] = 10
        g.input_seen()
        g.tick()
        self.assertEqual(g.s["call"]["kind"], "hungry")
        self.assertTrue(g.use_item("kimbap"))
        self.assertIsNone(g.s["call"])
        g.p["bugs"] = 5
        self.assertTrue(g.clean())
        self.assertEqual(g.p["bugs"], 0)
        self.assertEqual(g.s["inv"]["mats"]["bug_shell"], 5)
        clk.t += 10
        self.assertTrue(g.pat())
        self.assertFalse(g.pat())  # cooldown

    def test_overfeed_and_med(self):
        g, clk = mk()
        hatch(g, clk)
        g.p["full"] = 95
        g.s["inv"]["items"]["chicken"] = 1
        g.use_item("chicken")
        self.assertEqual(g.p["sick"], "overfed")
        g.s["gold"] = 100
        self.assertTrue(g.buy("digestive"))
        self.assertTrue(g.use_item("digestive"))
        self.assertIsNone(g.p["sick"])

    def test_expedition_auto_cycle(self):
        g, clk = mk()
        hatch(g, clk)
        g.signal("busy", sid="b", title="work", agent="build")
        self.assertIsNotNone(g.expd)
        self.assertTrue(g.expd["auto"])
        for _ in range(400):
            clk.t += 0.5
            g.input_seen()
            g.tick()
        g.signal("idle", sid="b", title="work")
        for _ in range(400):
            clk.t += 0.5
            g.tick()
            if not g.expd:
                break
        self.assertIsNone(g.expd)
        self.assertGreater(g.stat("kills") + g.stat("floors"), 0)
        self.assertIsNotNone(g.last_summary)

    def test_subagent_ally_and_tools(self):
        g, clk = mk()
        hatch(g, clk)
        g.signal("sub_start", sid="s1", agent="explore")
        self.assertIn("s1", g.allies)
        self.assertEqual(g.allies["s1"]["name"], "탐색 요정")
        g.signal("sub_end", sid="s1")
        self.assertNotIn("s1", g.allies)
        for _ in range(200):
            g.signal("tool", tool="edit", ok=True)
        self.assertGreater(g.s["inv"]["mats"].get("shard_edit", 0), 10)
        b0 = g.p["bugs"]
        for _ in range(30):
            g.signal("tool", tool="bash", ok=False)
        self.assertGreater(g.p["bugs"], b0)

    def test_error_boss_flag(self):
        g, clk = mk()
        hatch(g, clk)
        g.signal("error", msg="429 Too Many Requests")
        self.assertEqual(g.s["boss_flag"], "dragon429")

    def test_tokens_feed_exp_int(self):
        g, clk = mk()
        hatch(g, clk)
        g.p["full"] = 10
        lvl0, full0 = g.p["lvl"], g.p["full"]
        g.signal("tokens", tin=500000, tout=50000)
        self.assertGreater(g.p["full"], full0)
        self.assertLessEqual(g.p["full"], P.T["tok_full_cap"])
        self.assertGreater(g.p["lvl"], lvl0)
        self.assertGreaterEqual(g.p["int_bonus"], 1)

    def test_shop_equip_enhance_craft(self):
        g, clk = mk()
        hatch(g, clk)
        g.s["gold"] = 100000
        g.p["lvl"] = 20
        self.assertTrue(g.buy("kb_topre"))
        idx = len(g.s["inv"]["gear"]) - 1
        self.assertTrue(g.equip(idx))
        self.assertEqual(g.s["equip"]["weapon"]["id"], "kb_topre")
        g.s["inv"]["mats"]["shard_edit"] = 500
        res = None
        for _ in range(40):
            res = g.enhance("equip", "weapon")
            if g.s["equip"]["weapon"]["plus"] >= 10:
                break
        self.assertIsNotNone(res)
        g.s["inv"]["mats"].update({"shard_exec": 10})
        self.assertTrue(g.craft("r_energy"))
        self.assertEqual(g.s["inv"]["items"]["energydrink"], 2)
        self.assertTrue(g.buy("plant"))
        self.assertTrue(g.toggle_deco("plant"))
        self.assertIn("plant", g.s["inv"]["placed"])

    def test_minigames(self):
        g, clk = mk()
        hatch(g, clk)
        self.assertTrue(g.start_minigame("dir"))
        for _ in range(5):
            g.minigame_key("LEFT")
            clk.t += 1.5
            g.tick()
        self.assertEqual(g.mg["phase"], "result")
        clk.t += 5
        g.tick()
        self.assertIsNone(g.mg)
        self.assertTrue(g.start_minigame("type"))
        for _ in range(3):
            target = g.mg["phrases"][g.mg["idx"]]
            for ch in target:
                g.minigame_key(ch)
            clk.t += 3
            g.minigame_key("ENTER")
        self.assertEqual(g.mg["phase"], "result")
        clk.t += 5
        g.tick()
        self.assertTrue(g.start_minigame("whack"))
        for _ in range(250):
            clk.t += 0.1
            g.tick()
            if g.mg and g.mg.get("cells"):
                g.minigame_key(next(iter(g.mg["cells"])))
            if g.mg and g.mg.get("phase") == "result":
                break
        self.assertEqual(g.mg["phase"], "result")
        self.assertGreater(g.stat("games"), 2)

    def test_save_load_offline_and_live(self):
        scope = "persist1"
        g, clk = mk(scope, persist=True)
        hatch(g, clk)
        g.s["gold"] = 777
        g.save(force=True)
        g.write_live(force=True)
        g.close()
        sm = P.pet_summary(scope, now=clk.t)
        self.assertEqual(sm["name"], "토큰이")
        clk2 = Clock(clk.t + 5 * 3600)
        g2 = P.PetGame(scope, clock=clk2, seed=2)
        self.assertEqual(g2.s["gold"], 777 + 0)
        self.assertIsNotNone(g2.welcome)
        self.assertFalse(g2.readonly)
        # second instance → readonly (lock held)
        g3 = P.PetGame(scope, clock=clk2, seed=3)
        self.assertTrue(g3.readonly)
        self.assertIsNone(g3.take_over())            # 주인 창이 살아 있으면 확인 요청
        self.assertTrue(g3.take_over(force=True))    # 두 번 누르면 강제로
        clk2.t += 6
        g2.tick()                                    # 옛 주인은 하트비트에서 잠금을 잃은 걸 알아채고 관전 모드로
        self.assertTrue(g2.readonly)
        g2.close()
        g3.close()

    def test_legacy_migration(self):
        scope = "legacy1"
        os.makedirs(P.data_dir(), exist_ok=True)
        with open(P.legacy_path(scope), "w", encoding="utf-8") as f:
            json.dump({"name": "Bob", "lvl": 7, "gold": 500, "coffee": 4, "kills": 33}, f)
        g, clk = mk(scope, persist=True)
        self.assertIn("legacy", g.s["ach"])
        self.assertGreaterEqual(g.s["gold"], 600)
        self.assertEqual(g.s["stats"]["kills"], 33)
        g.close()

    def test_bus(self):
        scope = "bus1"
        r = P.BusReader(scope)
        P.bus_write(scope, {"type": "compose", "chars": 10, "text": "버그 고쳐줘"})
        evs = r.poll()
        self.assertEqual(evs[0]["type"], "compose")
        self.assertEqual(r.poll(), [])
        self.assertEqual(P.reaction_context("버그 고쳐줘"), "compose_bug")

    def test_daily_rollover(self):
        g, clk = mk()
        hatch(g, clk)
        d0 = g.s["daily"]["date"]
        clk.t += 86400
        g.input_seen()
        g.tick()
        self.assertNotEqual(g.s["daily"]["date"], d0)
        self.assertEqual(g.s["daily"]["streak"], 2)
        self.assertEqual(len(g.s["daily"]["quests"]), 3)

    def test_battle_manual_actions(self):
        g, clk = mk()
        hatch(g, clk)
        g.p["lvl"] = 12
        g.stats()
        g.start_expedition(0)
        g.start_battle("slime", "normal", 3)
        g.s["settings"]["auto_battle"] = False
        for act in (("attack", None), ("skill", "slash"), ("defend", None), ("item", "coffee"), ("skill", "duck")):
            clk.t += 0.5
            g.battle_action(*act)
            if not g.battle or g.battle["over"]:
                break
        self.assertTrue(g.battle is None or g.battle["round"] >= 1)

    def test_evolution_chain(self):
        g, clk = mk()
        hatch(g, clk)
        g.p["lvl"] = 3
        clk.t += 21 * 60
        g.input_seen()
        g.tick()
        self.assertEqual(g.p["form"], "byte")
        g.p["lvl"] = 8
        clk.t += 2 * 3600
        g.input_seen()
        g.tick()
        self.assertIn(g.p["form"], ("junior", "kiddie"))
        g.p["lvl"] = 16
        g.s["traits"]["bug"] = 500
        clk.t += 12 * 3600
        g.input_seen()
        g.tick()
        self.assertEqual(g.p["form"], "hunter")
        self.assertIn("breakpoint", g.available_skills())


if __name__ == "__main__":
    try:
        unittest.main(verbosity=1)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
