"""oc_monitor 회귀 테스트 (서버 없이 돌아가는 부분)"""
import argparse, os, sys, tempfile, threading, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))  # 저장소 루트
TMP = tempfile.mkdtemp()
os.environ["LOCALAPPDATA"] = TMP
import oc_monitor as M  # noqa: E402


def setUpModule():
    os.environ["LOCALAPPDATA"] = TMP


def args(**kw):
    a = argparse.Namespace(name="t", url="http://127.0.0.1:1", color=None, dir=None, password=None,
                           interval=2.0, max_sessions=15)
    a.__dict__.update(kw)
    return a


class NeedStats(unittest.TestCase):
    def test_busy_session_is_refetched_only_every_interval(self):
        inst = M.Instance("t", "http://127.0.0.1:1")
        self.assertTrue(inst.need_stats("s1", 1, busy=True, now=100.0))   # 처음 본 세션은 바로
        inst.stats_ver["s1"], inst.stats_at["s1"] = 1, 100.0
        self.assertFalse(inst.need_stats("s1", 2, busy=True, now=102.0))  # 일하는 중: 2초 뒤엔 안 받음
        self.assertFalse(inst.need_stats("s1", 3, busy=True, now=109.9))
        self.assertTrue(inst.need_stats("s1", 3, busy=True, now=110.0))   # 간격이 지나면 받음

    def test_idle_session_is_refetched_when_changed(self):
        inst = M.Instance("t", "http://127.0.0.1:1")
        inst.stats_ver["s1"], inst.stats_at["s1"] = 5, 100.0
        self.assertFalse(inst.need_stats("s1", 5, busy=False, now=101.0))
        self.assertTrue(inst.need_stats("s1", 6, busy=False, now=101.0))  # 끝난 직후 최종 값은 바로


class ComposeDoesNotPoll(unittest.TestCase):
    def test_single_instance_without_start_spawns_no_threads(self):
        before = threading.active_count()
        inst = M.single_instance(args(), start=False)
        self.assertEqual(threading.active_count(), before)
        self.assertEqual(inst.url, "http://127.0.0.1:1")
        inst.alive = False


class ServerPassword(unittest.TestCase):
    def setUp(self):
        self.old = os.environ.pop("OPENCODE_SERVER_PASSWORD", None)
        self.path = os.path.join(os.path.dirname(M.registry_path()), "server-password")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def tearDown(self):
        if self.old is not None:
            os.environ["OPENCODE_SERVER_PASSWORD"] = self.old
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_env_then_file(self):
        self.assertIsNone(M.server_password())
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("from-file\n")
        self.assertEqual(M.server_password(), "from-file")
        os.environ["OPENCODE_SERVER_PASSWORD"] = "from-env"
        try:
            self.assertEqual(M.server_password(), "from-env")
        finally:
            del os.environ["OPENCODE_SERVER_PASSWORD"]


class ComposeBus(unittest.TestCase):
    def test_sent_text_is_not_written_to_disk(self):
        import ocmux_pet as P
        inst = M.Instance("bus-t", "http://127.0.0.1:1")
        M.compose_after_send(inst, "버그 고쳐줘 password=hunter2", True, "")
        with open(P.bus_path("bus-t"), encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn("hunter2", raw)
        self.assertEqual(M.json.loads(raw.splitlines()[-1])["ctx"], "compose_bug")

    def test_old_text_is_scrubbed_when_pet_starts(self):
        import ocmux_pet as P
        path = P.bus_path("bus-old")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(M.json.dumps({"type": "compose", "chars": 9, "text": "비밀번호 hunter2", "ts": 1}, ensure_ascii=False) + "\n")
            f.write(M.json.dumps({"type": "other", "ts": 2}) + "\n")
        P.BusReader("bus-old")
        with open(path, encoding="utf-8") as f:
            lines = [M.json.loads(x) for x in f]
        self.assertEqual(lines, [{"type": "compose", "chars": 9, "ts": 1}, {"type": "other", "ts": 2}])
        self.assertFalse(P.scrub_bus("bus-old"))  # 두 번째부터는 다시 쓰지 않음


class RegDir(unittest.TestCase):
    def test_status_pane_reads_folder_from_registry(self):
        reg = M.registry_path()
        os.makedirs(os.path.dirname(reg), exist_ok=True)
        with open(reg, "w", encoding="utf-8") as f:
            M.json.dump([{"name": "api", "url": "http://127.0.0.1:4096", "dir": "C:\\work\\100%done", "headless": True}], f)
        try:
            with_reg = M.single_instance(args(name="api", url="http://127.0.0.1:1", reg_dir=True), start=False)
            plain = M.single_instance(args(name="api", url="http://127.0.0.1:1"), start=False)
        finally:
            os.remove(reg)
        self.assertEqual((with_reg.api.dir, with_reg.url), ("C:\\work\\100%done", "http://127.0.0.1:1"))
        self.assertIsNone(plain.api.dir)  # 다른 칸(usage·펫·compose)은 예전처럼 폴더 없이


if __name__ == "__main__":
    unittest.main()
