"""v5 주인공: 성격마다 다른 펫 대사 · 대사 표정 · 형태 공명 대사 · 새 세대가 이어받는 이야기"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_story as TS  # noqa: E402
from test_story import P, D, UI, vlen, mk, hatch, tick_for  # noqa: E402


def setUpModule():
    TS.setUpModule()


def pet_lines():
    out = []
    for c in D.CHAPTERS:
        for part in (c["intro"], c["boss"]["intro"], c["outro"], c["boss"].get("phase2_lines") or []):
            out += [t for s, t in part if s.partition(":")[0] == "pet"]
    return out


class Data(unittest.TestCase):
    def test_variants_point_at_real_lines(self):
        base = set(pet_lines())
        for text, var in D.PET_LINES.items():
            self.assertIn(text, base)
            self.assertLessEqual(set(var), set(D.PERSONALITIES), text)
            for v in var.values():
                self.assertNotEqual(v, text)
                self.assertLessEqual(vlen(v), 76, v)
        # 성격 7종 모두 적어도 세 장면에서 자기 목소리를 낸다
        for k in D.PERSONALITIES:
            self.assertGreaterEqual(sum(1 for v in D.PET_LINES.values() if k in v), 3, k)

    def test_every_pet_line_has_a_face(self):
        for c in D.CHAPTERS:
            for part in (c["intro"], c["boss"]["intro"], c["outro"]):
                for spk, t in part:
                    if spk.startswith("pet"):
                        self.assertIn(spk.partition(":")[2], D.FACES, t)

    def test_form_lines(self):
        ids = {c["id"] for c in D.CHAPTERS}
        for cid, forms in D.FORM_LINES.items():
            self.assertIn(cid, ids)
            for form, lines in forms.items():
                self.assertIn(form, D.FORMS)
                self.assertGreaterEqual(D.FORMS[form]["stage"], 3)
                for spk, _ in lines:
                    base, _, face = spk.partition(":")
                    self.assertTrue(base in D.NPCS or base == "pet", spk)
                    self.assertTrue(not face or face in D.FACES)
        # 성체 6종 + 전설 2종 + 청소년 2종이 저마다 한 번은 공명한다
        forms = {f for v in D.FORM_LINES.values() for f in v}
        self.assertEqual(forms, set(D.ADULT_FORMS + D.LEGEND_FORMS + ["junior", "kiddie"]))


class Scene(unittest.TestCase):
    def setUp(self):
        self.g, self.clk = mk("hero")
        hatch(self.g, self.clk)

    def test_personality_changes_pet_line(self):
        g = self.g
        g.p["personality"] = "foodie"
        lines = g.story_scene(0, "intro")
        pet = [t for s, t, _ in lines if s == "pet"]
        self.assertIn("청포도 사탕", pet[0])
        g.p["personality"] = "brave"
        self.assertIn("다시 켜면", [t for s, t, _ in g.story_scene(0, "intro") if s == "pet"][0])
        g.p["personality"] = "tidy"                    # 변주가 없는 대사는 그대로
        self.assertIn("12년 동안 67%라고?!", [t for s, t, _ in g.story_scene(2, "boss") if s == "pet"])

    def test_faces_and_names_are_resolved(self):
        lines = self.g.story_scene(6, "outro")
        self.assertIn(("pet", "선배님…?!", "sad"), lines)
        for s, t, f in self.g.story_scene(9, "boss"):
            self.assertNotIn("{name}", t)
            self.assertNotIn("은(는)", t)

    def test_form_resonance_inserted_before_last_line(self):
        g = self.g
        plain = g.story_scene(6, "intro")
        g.p["form"] = "zombie"
        lines = g.story_scene(6, "intro")
        self.assertEqual(len(lines), len(plain) + 2)
        self.assertIn("고향 냄새", lines[-3][1])
        self.assertEqual(lines[-3][2], "sleepy")
        self.assertEqual(lines[-1], plain[-1])
        g.p["form"] = "monk"
        self.assertEqual(len(g.story_scene(6, "intro")), len(plain))      # 다른 형태는 그대로

    def test_replay_joins_three_parts(self):
        rp = self.g.story_scene(0, "replay")
        n = sum(len(self.g.story_scene(0, p)) for p in ("intro", "boss", "outro"))
        self.assertEqual(len(rp), n + 2)


class Heir(unittest.TestCase):
    def test_new_generation_hears_the_ancestor(self):
        g, clk = mk("heir")
        hatch(g, clk)
        st = g.story()
        g.story_mark_seen(0, "intro")
        old = g.p["name"]
        g.p.update(form="tenx", lvl=30)
        g.s["hatched"] = clk.t - 5 * 86400
        self.assertTrue(g.can_retire()[0], g.can_retire())
        self.assertTrue(g.retire())
        self.assertTrue(st["heir"])
        self.assertFalse(g.story_seen(st["ch"], "intro"))           # 지금 챕터 프롤로그를 다시 본다
        lines = g.story_scene(st["ch"], "intro")
        self.assertEqual(lines[0][0], "owl")
        self.assertIn(old, lines[0][1])
        # 알인 동안에는 자동으로 틀지 않는다
        ui = UI.PetUI(g)
        ui.boot_until = 0
        ui.tab = 6
        g.fx.pop("retire", None)
        g.welcome = None
        ui.render(80, 24)
        self.assertIsNone(ui.scene)
        # 깨어나면 틀고, 다 보면 인사는 끝
        clk.t += 700
        g.signal("busy", sid="b", title="t")
        g.signal("idle", sid="b", title="t")
        tick_for(g, clk, 2)
        self.assertFalse(g.is_egg())
        TS.settle(g)
        ui.render(80, 24)
        self.assertIsNotNone(ui.scene)
        self.assertEqual(ui.scene["part"], "intro")
        self.assertIn(old, ui.scene["lines"][0][1])
        ui.key("ESC")
        self.assertFalse(st["heir"])
        self.assertEqual(g.story_scene(st["ch"], "intro")[0][0], "narr")


class SceneUI(unittest.TestCase):
    def test_pet_face_follows_the_line(self):
        g, clk = mk("hero_ui")
        hatch(g, clk)
        ui = UI.PetUI(g)
        ui.boot_until = 0
        ui.tab = 6
        ui._scene_start(6, "outro")
        idx = next(i for i, ln in enumerate(ui.scene["lines"]) if ln[0] == "pet")
        ui.scene["idx"] = idx
        screen = re.sub(r"\x1b\[[0-9;]*m", "", "\n".join(ui.render(80, 24)))
        self.assertIn(D.FACES["sad"], screen)
        for W, H in ((40, 14), (60, 20), (120, 34)):
            for ln in ui.render(W, H):
                self.assertLessEqual(vlen(ln), W)


if __name__ == "__main__":
    unittest.main()
