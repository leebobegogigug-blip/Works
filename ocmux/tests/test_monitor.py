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


    def test_bus_survives_coarse_clock(self):
        """Windows(Python 3.8 등)는 time.time() 이 ~15ms 단위라 연달아 쓴 이벤트의 ts 가 같다 → 전부 받아야 한다"""
        import ocmux_pet as P
        real = P.time.time
        P.time.time = lambda: int(real() * 10) / 10  # 100ms 단위 시계로 흉내 (내림 — 실제 시각보다 앞서지 않게)
        try:
            r = P.BusReader("bus-coarse")
            for i in range(20):
                P.bus_write("bus-coarse", {"type": "compose", "i": i})
            got = r.poll()
        finally:
            P.time.time = real
        self.assertEqual([e["i"] for e in got], list(range(20)))
        self.assertEqual(r.poll(), [])
        again = P.BusReader("bus-coarse")        # 새로 뜬 펫 창은 예전 이벤트를 다시 받지 않는다
        self.assertEqual(again.poll(), [])
        with open(P.bus_path("bus-coarse"), "w", encoding="utf-8") as f:  # 잘려서 처음부터 읽혀도 재생 안 됨
            f.write("")
        P.bus_write("bus-coarse", {"type": "compose", "i": 99})
        self.assertEqual([e["i"] for e in r.poll()], [99])


class FakeApi:
    def __init__(self, down=False):
        self.calls, self.down = [], down

    def get(self, path, timeout=5):
        self.calls.append(path)
        if self.down:
            raise OSError("connection refused")
        if path == "/global/health":
            return {"version": "1.2"}
        if path == "/session":
            return [{"id": "s1", "time": {"updated": 100, "created": 50}}]
        if path == "/session/status":
            return {"s1": {"type": "busy"}}
        return [{"info": {"role": "assistant", "tokens": {"input": 10, "output": 5}, "cost": 0.1, "modelID": "m"}}]


class SharedPolling(unittest.TestCase):
    """같은 서버를 보는 칸은 리더 하나만 opencode 를 조회하고, 나머지는 스냅샷을 읽는다"""

    def pair(self, url):
        a, b = M.Instance("a", url), M.Instance("b", url)
        a.api, b.api = FakeApi(), FakeApi()
        return a, b

    def test_follower_uses_leader_snapshot(self):
        a, b = self.pair("http://127.0.0.1:7001")
        a.poll_once()
        b.poll_once()
        self.assertTrue(a.api.calls)
        self.assertEqual(b.api.calls, [])          # 팔로워는 서버를 부르지 않는다
        self.assertEqual((b.connected, b.ready, list(b.sessions), b.version), (True, True, ["s1"], "1.2"))
        self.assertEqual(b.totals(), a.totals())
        self.assertEqual(b.status["s1"]["type"], "busy")
        self.assertIn("online", [e[2] for e in b.events])

    def test_takeover_when_leader_goes_quiet_and_offline_propagates(self):
        a, b = self.pair("http://127.0.0.1:7002")
        a.poll_once()
        b.poll_once()
        self.assertFalse(b.share.leader())
        future = M.time.time() + 60                 # 리더가 60초 동안 잠금을 갱신하지 않음 → 이어받기
        self.assertTrue(b.share.leader(now=future))
        self.assertFalse(a.share.leader(now=future))
        c, d = self.pair("http://127.0.0.1:7003")
        c.api.down = True
        c.poll_once()
        d.connected = True
        d.poll_once()
        self.assertFalse(d.connected)               # 리더가 본 offline 도 그대로 전달
        self.assertIn("offline", [e[2] for e in d.events])

    def test_different_folder_is_not_shared(self):
        a = M.Instance("a", "http://127.0.0.1:7004", directory="C:\\x")
        b = M.Instance("b", "http://127.0.0.1:7004")
        self.assertNotEqual(a.share.snap_path, b.share.snap_path)
        self.assertIsNone(M.Instance("c", "http://127.0.0.1:7004", share=False).share)


class OnceFlag(unittest.TestCase):
    """--once (한 장 찍고 끝내기) 는 모든 칸에서 통해야 한다 — 설치 점검 · 스크린샷이 쓰는 경로.
    compose 는 키 입력(원시 모드) 없이, logs 는 계속 따라가지 않고 끝나야 한다"""

    def run_mode(self, *args):
        import subprocess
        env = dict(os.environ, LOCALAPPDATA=TMP, PYTHONUTF8="1")
        return subprocess.run([sys.executable, os.path.join(os.path.dirname(M.__file__), "oc_monitor.py"), *args,
                               "--url", "http://127.0.0.1:9", "--name", "once", "--once", "0.2", "--cols", "80", "--rows", "14"],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", timeout=60, env=env)

    def test_compose_and_logs_exit(self):
        for mode, extra, word in (("compose", [], "COMPOSE"), ("compose", ["--guide"], "GUIDE"), ("logs", [], "LOGS")):
            r = self.run_mode(mode, *extra)
            self.assertEqual(r.returncode, 0, (mode, r.stderr[-400:]))
            self.assertIn(word, r.stdout, mode)


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
