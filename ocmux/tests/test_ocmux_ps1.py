"""ocmux.ps1 실제 실행 테스트 (pwsh 가 있는 Linux/macOS 에서만 · Windows 는 CI 에서 문법만 검사)

wt · opencode 는 가짜 실행 파일로 바꿔서, ocmux add 가 Windows Terminal 에 넘기는 명령줄을 그대로 받아 본다.
PWSH 환경변수로 pwsh 경로를 줄 수 있다."""
import json, os, shutil, stat, subprocess, sys, tempfile, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PS1 = os.path.join(HERE, "..", "ocmux.ps1")
PWSH = os.environ.get("PWSH") or shutil.which("pwsh")


@unittest.skipUnless(PWSH and os.name != "nt", "pwsh 가 없음 (Windows 는 CI 에서 문법 검사)")
class OcmuxPs1(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.appdata = os.path.join(self.tmp, "appdata")
        self.bin = os.path.join(self.tmp, "bin")
        self.wt_log = os.path.join(self.tmp, "wt.log")
        os.makedirs(self.bin)
        self.stub("wt", f'printf "%s\\n" "$*" >> "{self.wt_log}"')
        self.stub("opencode", "exit 0")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stub(self, name, body):
        path = os.path.join(self.bin, name)
        with open(path, "w") as f:
            f.write("#!/bin/sh\n" + body + "\n")
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)

    def run_ps(self, *args, cwd=None, password=None):
        env = dict(os.environ, LOCALAPPDATA=self.appdata, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""))
        env.pop("OPENCODE_SERVER_PASSWORD", None)
        if password:
            env["OPENCODE_SERVER_PASSWORD"] = password
        return subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", PS1, *args], cwd=cwd or self.tmp,
                              env=env, capture_output=True, text=True, timeout=120)

    def project(self, name):
        path = os.path.join(self.tmp, name)
        os.makedirs(path, exist_ok=True)
        return path

    def wt_calls(self, n):
        for _ in range(100):  # Start-Process 는 기다리지 않는다
            if os.path.exists(self.wt_log):
                with open(self.wt_log) as f:
                    lines = f.read().splitlines()
                if len(lines) >= n:
                    return lines
            time.sleep(0.05)
        self.fail("wt 가 불리지 않음")

    def registry(self):
        with open(os.path.join(self.appdata, "ocmux", "instances.json"), encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]

    def test_add_ls_rm_and_password_file(self):
        r = self.run_ps("add", self.project("a&b"), password="s3cret")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        wt = self.wt_calls(1)[0]
        # (Linux 의 가짜 wt 는 따옴표 없이 받는다)
        self.assertIn("--title 00 overview", wt)               # 처음이면 overview 탭도
        self.assertIn("--name a_b --color", wt)                # cmd 특수문자는 이름에서 _ 로
        self.assertIn("status --url http://127.0.0.1:4096", wt)
        self.assertIn("--reg-dir", wt)                         # 폴더는 명령줄 대신 레지스트리에서
        self.assertNotIn("s3cret", wt)                         # 비밀번호는 명령줄에 없다
        pw = os.path.join(self.appdata, "ocmux", "server-password")
        with open(pw, encoding="utf-8") as f:
            self.assertEqual(f.read(), "s3cret")
        self.assertEqual([(x["name"], x["ch"]) for x in self.registry()], [("a_b", 1)])
        r = self.run_ps("add", self.project("web"))
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertFalse(os.path.exists(pw))                   # 비밀번호 환경변수가 없으면 파일도 지운다
        self.assertEqual([x["port"] for x in self.registry()], [4096, 4097])
        self.assertIn("web", self.run_ps("ls").stdout)
        r = self.run_ps("rm", "a_b")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual([x["name"] for x in self.registry()], ["web"])

    def test_rejects_bad_name_and_headless_percent_folder(self):
        r = self.run_ps("add", self.project("p"), "-Name", 'x"y')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("name must not contain", r.stderr + r.stdout)
        r = self.run_ps("add", self.project("100%done"), "-Headless")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("-Headless cannot use a folder", r.stderr + r.stdout)
        self.assertFalse(os.path.exists(self.wt_log))


if __name__ == "__main__":
    unittest.main()
