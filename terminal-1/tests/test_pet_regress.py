"""2차 검수 수정 회귀 테스트"""
import os, sys, tempfile, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))  # 저장소 루트
TMP = tempfile.mkdtemp()
os.environ["LOCALAPPDATA"] = TMP
import t1_pet as P  # noqa: E402
import t1_pet_data as D  # noqa: E402
import t1_pet_ui as UI  # noqa: E402
import t1_pet_run as R  # noqa: E402
import t1_monitor as M  # noqa: E402
from test_pet_game import Clock, ts, mk, hatch, FakeInst, Rec  # noqa: E402


def setUpModule():
    # 여러 테스트 파일을 한 번에 돌려도 저장 폴더가 섞이지 않게: 이 파일의 테스트는 이 파일의 임시 폴더만 쓴다
    os.environ["LOCALAPPDATA"] = TMP


class RaidEdges(unittest.TestCase):
    def test_raid_across_week_boundary(self):
        g, clk = mk("wkA", persist=True, seed=1, t=ts(2026, 10, 11, 23, 50))   # 일요일 23:50
        hatch(g, clk)
        clk.t = ts(2026, 10, 11, 23, 59) + 50
        g.p["energy"] = g.p["full"] = 95
        self.assertTrue(g.start_raid())
        wk0 = g.battle["week"]
        clk.t += 20          # 월요일로 넘어감
        for _ in range(200):
            clk.t += 0.5
            g.input_seen()
            g.tick()
            if not g.battle:
                break
        self.assertNotEqual(P.week_key(clk.t), wk0)
        self.assertEqual(g.s["raid"]["dmg"], 0)
        self.assertFalse(g.s["raid"]["cleared"])
        g.close()

    def test_malformed_raid_file(self):
        wk = P.week_key(time.time())
        os.makedirs(P.data_dir(), exist_ok=True)
        P.write_json(P.raid_path("bad"), {"week": wk, "lvl": None, "dmg": "x"})
        with open(os.path.join(P.data_dir(), "raid-bad2.json"), "w") as f:
            f.write("[1,2")
        P.write_json(P.raid_path("bad3"), {"week": wk, "lvl": 5, "dmg": 100, "name": None})
        rows = P.raid_board(wk, fresh=True)
        self.assertEqual([r["dmg"] for r in rows], [100])

    def test_raid_clock_backwards(self):
        g, clk = mk("rcb", seed=2, t=ts(2026, 10, 14, 12))
        hatch(g, clk)
        r = g._raid_state()
        r["tries"]["n"] = 3
        r["dmg"] = 3000
        clk.t -= 86400
        self.assertEqual(g.raid_info()["tries_left"], 0)
        clk.t -= 7 * 86400
        self.assertEqual(g._raid_state()["dmg"], 3000)

    def test_no_sleep_in_raid(self):
        g, clk = mk("rsl", seed=3, t=ts(2026, 10, 21, 12))
        hatch(g, clk)
        g.p["energy"] = g.p["full"] = 95
        self.assertTrue(g.start_raid())
        self.assertFalse(g.toggle_sleep())
        self.assertFalse(g.p["sleeping"])


class TakeOverEdges(unittest.TestCase):
    def test_take_over_refuses_newer_version(self):
        scope = "tonew"
        g1, clk = mk(scope, persist=True)
        hatch(g1, clk)
        g1.save(force=True)
        g2 = P.PetGame(scope, clock=clk, seed=2)
        self.assertTrue(g2.readonly)
        st = P.read_json(P.pet_path(scope))
        st["v"] = D.SAVE_VERSION + 1
        st["gold"] = 4242
        g1.readonly = True          # 옛 창은 멈춤
        P.write_json(P.pet_path(scope), st)
        self.assertFalse(g2.take_over(force=True))
        self.assertEqual(P.read_json(P.pet_path(scope))["gold"], 4242)

    def test_take_over_recovers_snapshot_and_spectator_does_not(self):
        scope = "tosnap"
        g1, clk = mk(scope, persist=True)
        hatch(g1, clk)
        g1.p["energy"] = g1.p["full"] = 90
        g1.start_expedition(0)
        g1.expd["carry"]["gold"] = 321
        g1.save(force=True)
        g1._heartbeat(clk.t + 5)
        gold0 = P.read_json(P.pet_path(scope))["gold"]
        clk2 = Clock(clk.t + 6)
        g2 = P.PetGame(scope, clock=clk2, seed=2)        # g1 이 살아 있음 → 관전
        self.assertTrue(g2.readonly)
        self.assertFalse(any("전리품" in w for w in (g2.welcome or [])))
        clk2.t += 60                                      # g1 죽음 → 잠금 만료
        self.assertTrue(g2.take_over())
        self.assertEqual(g2.s["gold"], gold0 + 321)
        g2.close()


class CloseEdges(unittest.TestCase):
    def test_close_with_pending_loss_applies_faint(self):
        g, clk = mk(seed=4)
        hatch(g, clk)
        g.p["energy"] = g.p["full"] = 90
        g.start_expedition(0)
        g.expd["carry"]["gold"] = 1000
        g.start_battle("slime", "normal", 1)
        g.p["hp"] = 0
        g._check_end(g.battle)
        self.assertEqual(g.battle["over"], "lose")
        gold0 = g.s["gold"]
        g.close()
        self.assertEqual(g.stat("faints"), 1)
        self.assertEqual(g.s["gold"] - gold0, 500)

    def test_close_after_raid_retreat_keeps_damage(self):
        g, clk = mk("rret", seed=5, t=ts(2026, 10, 28, 12))
        hatch(g, clk)
        g.p["energy"] = g.p["full"] = 95
        g.start_raid()
        g.battle["mon"]["hp"] -= 314
        g.raid_retreat()
        g.close()
        self.assertEqual(g.s["raid"]["dmg"], 314)


class TodoEdges(unittest.TestCase):
    def test_finished_list_refetched_no_bonus(self):
        g, clk = mk(seed=6)
        hatch(g, clk)
        a = [{"content": "x", "status": "pending"}, {"content": "y", "status": "pending"}]
        g.signal("todos", sid="A", title="a", todos=a, root=True)
        done = [{"content": "x", "status": "completed"}, {"content": "y", "status": "completed"}]
        g.signal("todos", sid="A", title="a", todos=done, root=True)
        self.assertEqual(g.stat("todo_lists"), 1)
        for i in range(4):
            g.signal("todos", sid="B", title="b", todos=[{"content": f"b{i}", "status": "pending"}], root=True)
            g.signal("todos", sid="A", title="a", todos=done, root=True)     # 다시 받아옴
        self.assertEqual(g.stat("todo_lists"), 1)

    def test_new_list_same_session_gets_bonus(self):
        g, clk = mk(seed=7)
        hatch(g, clk)
        for names in (("a", "b"), ("c", "d")):
            g.signal("todos", sid="S", title="", todos=[{"content": n, "status": "pending"} for n in names], root=True)
            g.signal("todos", sid="S", title="", todos=[{"content": n, "status": "completed"} for n in names], root=True)
        self.assertEqual(g.stat("todo_lists"), 2)


class MiscEdges(unittest.TestCase):
    def test_heir_name_long(self):
        names = set()
        n = "가나다라마바사아자차"
        for gen in (2, 3, 4):
            n = P.heir_name(n, gen)
            names.add(n)
            self.assertTrue(n.endswith(f"{gen}세"))
            self.assertLessEqual(len(n), 12)
        self.assertEqual(len(names), 3)

    def test_quiz_diminishing(self):
        g, clk = mk(seed=8)
        hatch(g, clk)
        gold = []
        for i in range(12):
            g.p["energy"] = 100
            g.start_minigame("quiz")
            for _ in range(5):
                q = D.QUIZ[g.mg["qs"][g.mg["idx"]]]
                g.minigame_key("o" if q[1] else "x")
                g.minigame_key("ENTER")
            g0 = g.s["gold"]
            g.mg = None
            gold.append(g0)
        self.assertLessEqual(g.p["int_bonus"], 1)

    def test_clock_back_still_saves(self):
        scope = "clkb"
        g, clk = mk(scope, persist=True)
        hatch(g, clk)
        g.save(force=True)
        clk.t -= 3600
        g.s["gold"] += 777
        g.mark()
        for _ in range(30):
            clk.t += 1
            g.tick()
        self.assertEqual(P.read_json(P.pet_path(scope))["gold"], g.s["gold"])
        g.close()

    def test_sub_end_clears_waits_and_gone(self):
        g, clk = mk(seed=9)
        hatch(g, clk)
        g.signal("wait", id="w1", sid="kid", wkind="perm", label="x")
        g.signal("sub_end", sid="kid")
        self.assertNotIn("w1", g.waits)
        g.p["energy"] = g.p["full"] = 90
        g.signal("busy", sid="R", title="t")
        self.assertIsNotNone(g.expd)
        g.signal("gone", sid="R")
        self.assertTrue(g.expd["ret"])

    def test_token_delta_unknown_created(self):
        inst = FakeInst()
        td = M.TokenDelta(start_ms=time.time() * 1000)
        inst.stats["old"] = {"tin": 0, "tout": 0}
        self.assertEqual(td.update(inst), (0, 0))
        inst.stats["old"] = {"tin": 400000, "tout": 20000}
        inst.created_ms["old"] = time.time() * 1000 - 86400000
        self.assertEqual(td.update(inst), (0, 0))

    def test_bridge_unknown_todos_not_root(self):
        inst = FakeInst()
        b = R.SignalBridge(inst, M.TokenDelta(), M.wait_info, M.WAIT_ASK_EVENTS, M.WAIT_DONE_EVENTS)
        g = Rec()
        inst.emit("todo.updated", sessionID="who", todos=[{"content": "a", "status": "pending"}])
        b.poll(g)
        self.assertEqual([d["root"] for k, d in g.sig if k == "todos"], [False])


class UiEdges(unittest.TestCase):
    def test_spectator_overlay_cleared(self):
        g, clk = mk(seed=10)
        hatch(g, clk)
        ui = UI.PetUI(g)
        g.welcome = None
        g.fx.pop("evolve", None)
        ui.overlay = dict(kind="retire")
        g.readonly = True
        ui.key("ESC")
        self.assertIsNone(ui.overlay)

    def test_summary_does_not_eat_evolve_skip(self):
        g, clk = mk(seed=11)
        hatch(g, clk)
        ui = UI.PetUI(g)
        g.welcome = None
        g.last_summary = (dict(zone="z", floor=1, floors=1, kills=1, gold=1, loot=[], reason="r", fainted=False, mins=1), g.now() + 9)
        g.fx["evolve"] = ("bit", "byte", g.now() + 4)
        ui.key("ENTER")
        self.assertLessEqual(g.fx["evolve"][2], g.now())

    def test_popup_key_falls_through(self):
        g, clk = mk(seed=12)
        ui = UI.PetUI(g)
        self.assertTrue(g.welcome)
        b0 = g.s["timers"].get("egg_bonus", 0)
        ui.key("j")                 # 환영창을 닫으면서 쓰다듬기도
        self.assertIsNone(g.welcome)
        self.assertGreater(g.s["timers"].get("egg_bonus", 0), b0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
