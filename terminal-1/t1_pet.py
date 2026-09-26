"""
t1_pet.py - TOKEN QUEST: 토큰펫 게임 엔진 (화면 없음 / 순수 로직 + 저장)

다마고치 + RPG:
  - 돌봄: 포만·기분·체력·건강, 방에 쌓이는 버그(=똥), 잠, 병, 몸무게, 관심 요청(호출), 돌봄 점수
  - 성장: 알 → 비트 → 바이트 → 청소년(2갈래) → 성체(6갈래) → 전설. 키운 방식이 진화를 결정
  - RPG: 레벨/능력치/스킬, 던전 원정(12지역 x 10층), 이벤트 선택지, 장비·강화·제작·상점·방 꾸미기
  - 메인 스토리(v4): 시즌 1 「초록불을 찾아서」 챕터 12개 = 지역 12개. 첫 주에 4장, 그다음 매주 한 장씩 열린다
  - opencode 연동: 토큰=밥/경험치, 응답 도착=퀘스트 보상, 서브에이전트=동료, 도구=재료, 에러=보스/버그
  - 저장: %LOCALAPPDATA%\\terminal-1\\pet-<이름>.json (+ 다른 창용 live 요약, 이벤트 버스, 중복 실행 잠금)
"""
import collections
import datetime
import difflib
import itertools
import json
import os
import random
import re
import time

import t1_pet_data as D

# ============================================================== 튜닝
T = dict(
    # 욕구 (시간당)
    full_decay=18.0, full_decay_sleep=6.0, mood_decay=12.0, energy_decay=12.0, energy_sleep=40.0,
    health_regen=6.0, health_starve=18.0, health_bug=6.0, health_exhaust=8.0, health_sick=5.0,
    kb_decay=0.03,
    bug_every=55 * 60, bug_every_sleep=160 * 60, bug_max=9,
    call_min=25 * 60, call_max=70 * 60, call_expire=25 * 60, call_cool=30 * 60,
    absent_after=45 * 60, absent_factor=0.3,   # 주인이 45분 넘게 안 보이면 '기다림 모드' (천천히 닳고 호출/실수 없음)
    sick_chance=0.35,                 # 건강 35 미만일 때 시간당 감기 확률
    # 토큰
    tok_full=6000, tok_exp=1000, tok_int=60000, tok_mp=400, tok_full_cap=60,
    # 오프라인
    offline_factor=0.3, offline_cap=18 * 3600,
    # 집에서 회복 (10초당 최대치 비율)
    home_hp_regen=0.02, home_mp_regen=0.03,
    # 원정/전투 템포 (초)
    round_time=1.1, walk_time=3.2, result_time=1.4, pause_time=2.2, event_auto=5.0, event_manual=14.0,
    floor_energy=4.5, floor_full=2.5,
    # 저장
    save_every=20, live_every=2, lock_every=5, lock_stale=20,
    # 훈육 / 떼쓰기 (필요는 다 채워졌는데 괜히 부르는 호출 → [G] 훈육이 정답)
    tantrum_chance=0.22, disc_scold=10, disc_spoil=6, disc_ignore=3,
    # opencode 할 일(todo) 완료 보상 하루 상한 / 응답 대기(허락·질문) 만료
    todo_daily_cap=30, wait_expire=30 * 60,
)
DEFAULT_NAME = "토큰이"
# 토큰 → 경험치는 하루에 먹은 양이 많을수록 효율이 떨어진다 (하루 2백만까지 100%, 1천만까지 25%, 그 뒤 5%).
# 캐시 토큰을 따로 알려 주지 않는 모델은 하루 수천만 토큰도 나오는데, 그래도 스토리가 며칠 만에 끝나지 않게.
TOK_TIERS = ((2_000_000, 1.0), (10_000_000, 0.25), (None, 0.05))
MAT_SELL = {"shard_scan": 4, "shard_edit": 4, "shard_exec": 4, "shard_team": 8, "shard_web": 8, "bug_shell": 2,
            "boss_core": 150, "legacy_scroll": 60}
NOTHING_LINES = [
    "조용한 복도다. 형광등이 깜빡인다.", "벽에 적힌 TODO 주석: 'TODO: 나중에 고치기 (2019)'",
    "멀리서 빌드 서버 팬 소리가 들린다.", "바닥에 떨어진 키캡을 주웠다. …쓸 데는 없다.",
    "누군가의 .env 파일이 굴러다닌다. 못 본 걸로 했다.", "'여기서부터 레거시' 라는 표지판이 있다.",
    "빈 커피컵 탑이 쌓여 있다. 누군가 여기서 밤을 샜다.",
]
ATTACK_LINES = ["{p}의 몸통 박치기!", "{p}의 git blame 찌르기!", "{p}의 Ctrl+C Ctrl+V 연타!", "{p}의 들여쓰기 베기!",
                "{p}의 키보드 샷건!", "{p}의 console.log 난사!"]
ENEMY_LINES = ["{m}의 공격!", "{m}이(가) 달려들었다!", "{m}이(가) 요구사항을 바꿨다!", "{m}의 새벽 3시 알림!",
               "{m}이(가) 빌드를 깨뜨렸다!", "{m}의 스택트레이스 투척!"]


# ============================================================== 경로 / 입출력
def data_dir():
    from t1_term import data_dir as where   # 폴더 규칙은 한곳에서
    return where()


def safe_scope(scope):
    s = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (scope or "pet"))
    return s or "pet"


def pet_path(scope):
    return os.path.join(data_dir(), f"pet-{safe_scope(scope)}.json")


def live_path(scope):
    return os.path.join(data_dir(), f"pet-{safe_scope(scope)}.live.json")


def lock_path(scope):
    return os.path.join(data_dir(), f"pet-{safe_scope(scope)}.lock")


def bus_path(scope):
    return os.path.join(data_dir(), f"bus-{safe_scope(scope)}.jsonl")


def legacy_path(scope):
    return os.path.join(data_dir(), f"rpg-{safe_scope(scope)}.json")


def _dumps(obj):
    try:
        data = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        data.encode("utf-8")          # 짝 없는 서로게이트가 섞였으면 여기서 걸린다
        return data
    except UnicodeEncodeError:
        return json.dumps(obj, ensure_ascii=True, separators=(",", ":"))


def write_json(path, obj):
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = _dumps(obj)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
        for _ in range(6):
            try:
                os.replace(tmp, path)
                return True
            except PermissionError:  # Windows: 다른 프로세스가 읽는 중
                time.sleep(0.04)
    except Exception:
        pass
    try:
        os.remove(tmp)
    except OSError:
        pass
    return False


def read_json(path, default=None):
    for _ in range(3):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except (PermissionError, ValueError):
            time.sleep(0.03)
        except Exception:
            return default
    return default


def read_save(path, tries=10):
    """저장 파일 읽기 → (상태, 내용). 상태: missing / ok / corrupt(깨짐) / locked(계속 못 읽음)"""
    last = "locked"
    for _ in range(tries):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except FileNotFoundError:
            return "missing", None
        except PermissionError:
            last = "locked"
            time.sleep(0.1)
            continue
        except (OSError, UnicodeDecodeError):
            last = "corrupt"
            time.sleep(0.1)
            continue
        try:
            return "ok", json.loads(raw)
        except ValueError:
            last = "corrupt"
            time.sleep(0.1)
    return last, None


_BUS_SEQ = itertools.count(1)


def bus_write(scope, event):
    """다른 창(compose 등) → 펫 창으로 이벤트 전달 (append-only JSONL).
    id 는 이 프로세스 안에서 유일 — 시계가 거친 PC(Windows 는 ~15ms)에서 같은 ts 가 겹쳐도 구분한다"""
    ev = dict(event)
    ev.setdefault("ts", time.time())
    ev.setdefault("id", f"{os.getpid()}-{next(_BUS_SEQ)}")
    path = bus_path(scope)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path) and os.path.getsize(path) > 256 * 1024:
            with open(path, "r", encoding="utf-8") as f:
                keep = f.readlines()[-100:]
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(keep)
        with open(path, "a", encoding="utf-8") as f:
            f.write(_dumps(ev) + "\n")
    except Exception:
        pass


def scrub_bus(scope):
    """예전 버전이 버스 파일에 남긴 compose 원문(text)을 지운다. 원문이 있을 때만 다시 쓴다 → 지웠으면 True"""
    path = bus_path(scope)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return False
    out, changed = [], False
    for ln in lines:
        try:
            ev = json.loads(ln)
        except ValueError:
            out.append(ln)
            continue
        if isinstance(ev, dict) and "text" in ev:
            ev.pop("text")
            changed = True
            out.append(_dumps(ev) + "\n")
        else:
            out.append(ln)
    if not changed:
        return False
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(out)
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


class BusReader:
    """bus 파일 tail. 파일이 잘려(오래된 줄 정리) 처음부터 다시 읽어도 이미 받은 이벤트는 (ts, id) 로 걸러낸다.
    ts 가 같은 이벤트끼리는 id 로 구분한다 (시계가 거친 PC 에서 연달아 쓴 이벤트가 버려지지 않게)"""

    def __init__(self, scope):
        scrub_bus(scope)  # 예전 compose 원문 정리 (펫 창이 뜰 때 한 번)
        self.path = bus_path(scope)
        self.last_ts, self.seen = 0.0, set()  # seen: ts == last_ts 인 이벤트들의 id
        try:
            self.pos = os.path.getsize(self.path)
            with open(self.path, "rb") as f:  # 이미 있던 이벤트는 받은 것으로 친다 (잘린 뒤 다시 읽혀도 재생 안 되게)
                for line in f.read().decode("utf-8", "replace").splitlines():
                    self._accept(line)
        except OSError:
            self.pos = 0

    @staticmethod
    def _key(ev, line):
        return str(ev.get("id") or line)

    def _accept(self, line):
        """처음 보는 이벤트면 기록하고 돌려준다. 이미 받았으면 None"""
        try:
            ev = json.loads(line)
        except ValueError:
            return None
        ts = ev.get("ts", 0) if isinstance(ev, dict) else 0
        if not isinstance(ts, (int, float)) or ts < self.last_ts:
            return None
        key = self._key(ev, line)
        if ts == self.last_ts:
            if key in self.seen:
                return None
            self.seen.add(key)
        else:
            self.last_ts, self.seen = ts, {key}
        return ev

    def poll(self):
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return []
        if size < self.pos:
            self.pos = 0
        if size == self.pos:
            return []
        out = []
        try:
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                data = f.read()
            end = data.rfind(b"\n")
            if end < 0:
                return []
            self.pos += end + 1
            for line in data[:end].decode("utf-8", "replace").splitlines():
                ev = self._accept(line)
                if ev is not None:
                    out.append(ev)
        except OSError:
            pass
        return out


# ============================================================== 헬퍼
_JOSA_RE = re.compile(r"이\(가\)|은\(는\)|을\(를\)|과\(와\)|와\(과\)|으로\(로\)|아\(야\)")
_JOSA = {"이(가)": ("이", "가"), "은(는)": ("은", "는"), "을(를)": ("을", "를"), "과(와)": ("과", "와"),
         "와(과)": ("과", "와"), "으로(로)": ("으로", "로"), "아(야)": ("아", "야")}
# 숫자를 한국어로 읽을 때의 받침: 영(ㅇ) 일(ㄹ) 이 삼(ㅁ) 사 오 육(ㄱ) 칠(ㄹ) 팔(ㄹ) 구
_DIGIT_JONG = {"0": (True, False), "1": (True, True), "2": (False, False), "3": (True, False), "4": (False, False),
               "5": (False, False), "6": (True, False), "7": (True, True), "8": (True, True), "9": (False, False)}
_JOSA_SKIP = set(")]}」』\"'>")


def _batchim(text, end):
    """text[:end] 의 마지막 글자 받침 → (받침 있음, ㄹ 받침) / 모르면 None"""
    i = end - 1
    while i >= 0 and text[i] in _JOSA_SKIP:      # 「코코」이(가) → 코
        i -= 1
    if i < 0:
        return None
    ch = text[i]
    code = ord(ch) - 0xAC00
    if 0 <= code <= 11171:
        jong = code % 28
        return jong != 0, jong == 8
    if ch in _DIGIT_JONG:
        return _DIGIT_JONG[ch]
    if not ("a" <= ch.lower() <= "z"):
        return None
    prev = text[i - 1] if i > 0 else " "
    if ch.isupper() and not prev.islower():
        # 약어(API, IBM M …)는 알파벳 이름으로 읽는다: 엘·엠·엔·알 만 받침
        return ch in "LMNR", ch in "LR"
    low = ch.lower()
    if low in "lmn":
        return True, low == "l"
    if low in "kpbtc" or (low == "g" and prev.lower() == "n"):
        return True, False        # Slack을, Git을, Web을, Spring을
    return False, False


def fix_josa(text):
    """'토큰이이(가)' → '토큰이가' 처럼 받침에 맞게 조사 정리 (한글·숫자·영문 뒤)"""
    if not text or "(" not in text:
        return text
    out, last = [], 0
    for m in _JOSA_RE.finditer(text):
        j = m.group(0)
        info = _batchim(text, m.start())
        out.append(text[last:m.start()])
        if info is None:
            out.append(j)
        else:
            has, rieul = info
            a, b = _JOSA[j]
            out.append(b if (j == "으로(로)" and rieul) else (a if has else b))
        last = m.end()
    out.append(text[last:])
    return "".join(out)


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def day_key(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def local_hour(ts):
    return datetime.datetime.fromtimestamp(ts).hour


def weekday(ts):
    return datetime.datetime.fromtimestamp(ts).weekday()  # 월=0


def current_season(ts):
    """오늘이 시즌 이벤트 기간이면 그 dict, 아니면 None"""
    d = datetime.datetime.fromtimestamp(ts)
    ymd, md = d.strftime("%Y-%m-%d"), d.strftime("%m-%d")
    for se in D.SEASONS:
        for a, b in se["dates"]:
            if len(a) == 10:
                if a <= ymd <= b:
                    return se
            elif a <= md <= b:
                return se
    return None


def exp_to_next(lvl):
    return int(30 + 20 * lvl ** 1.75)


def token_weight(start, tot):
    """오늘 이미 start 개를 먹은 상태에서 tot 개를 더 먹을 때 경험치로 치는 '유효 토큰' 수 (TOK_TIERS 체감)"""
    w, at, left = 0.0, max(0, int(start)), max(0, int(tot))
    for hi, f in TOK_TIERS:
        if left <= 0:
            break
        if hi is not None and at >= hi:
            continue
        seg = left if hi is None else min(left, hi - at)
        w += seg * f
        at += seg
        left -= seg
    return w


def token_rate(n_today):
    """지금 토큰 경험치 효율 (1.0 = 100%)"""
    for hi, f in TOK_TIERS:
        if hi is None or n_today < hi:
            return f
    return TOK_TIERS[-1][1]


def new_story(now, fast=None):
    """메인 스토리 진행 상태 (펫이 은퇴해도 가문의 이야기로 이어진다)"""
    fast = D.STORY["fast"] if fast is None else fast
    fast = int(max(1, min(len(D.CHAPTERS), fast)))
    return {"start": day_key(now), "fast": fast, "rel": fast, "ch": 0, "phase": "play", "since": now,
            "base": {}, "mdone": [], "bonus": False, "bonus_n": 0, "seen": [], "cleared": [], "log": [],
            "fails": 0, "fail_lvl": 0, "pending": None}


def fmt_age(sec):
    sec = max(0, int(sec))
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return f"{d}일 {h}시간"
    if h:
        return f"{h}시간 {m}분"
    return f"{m}분"


def fmt_num(n):
    return f"{int(n):,}"


def item_name(iid):
    it = D.ITEMS.get(iid)
    return it["name"] if it else iid


def is_gear(iid):
    return D.ITEMS.get(iid, {}).get("kind") in ("weapon", "armor", "acc")


def gear_name(g):
    if not g:
        return "-"
    return item_name(g["id"]) + (f" +{g['plus']}" if g.get("plus") else "")


def monster_stats(mid, level, rank="normal"):
    m, r = D.MONSTERS[mid], D.RANK_MULT[rank]
    lv = max(1, level)
    hp = int((24 + 11.5 * lv) * m["hp"] * r["hp"])
    return dict(
        id=mid, name=m["name"], art=m["art"], rank=rank, level=lv, special=m["special"], chance=m["chance"],
        hp=hp, maxhp=hp,
        atk=(3.5 + 1.75 * lv) * m["atk"] * r["atk"],
        df=(1.5 + 1.0 * lv) * m["df"] * r["df"],
        spd=(5 + 0.7 * lv) * m["spd"],
        exp=int((5 + 2.2 * lv) * m["exp"] * r["exp"]),
        gold=int((3 + 1.5 * lv) * m["gold"] * r["gold"]),
        st={}, revived=False,
    )


def new_pet(name):
    return {"name": name or DEFAULT_NAME, "form": "egg", "prev_form": None, "lvl": 1, "exp": 0.0,
            "hp": None, "mp": None, "full": 80.0, "mood": 75.0, "energy": 90.0, "health": 100.0,
            "kb": 0.5, "bugs": 0, "sleeping": False, "sick": None, "int_bonus": 0, "title": None,
            "care": 70.0, "discipline": 50.0, "personality": None}


def new_state(scope, name, now):
    return {
        "v": D.SAVE_VERSION, "scope": scope, "created": now, "last_seen": now, "hatched": None,
        "pet": new_pet(name),
        "equip": {"weapon": {"id": "kb_laptop", "plus": 0}, "armor": {"id": "hood_holed", "plus": 0}, "acc": None},
        "inv": {"items": {"kimbap": 3, "samgak": 2, "coffee": 3}, "gear": [], "mats": {}, "decos": [], "placed": []},
        "gold": 100,
        "prog": {"floor": {}, "cleared": []},
        "traits": {"battle": 0.0, "bug": 0.0, "plan": 0.0, "tokens": 0.0, "play": 0.0, "care": 0.0, "mistakes": 0.0},
        "stats": {},
        "dex": {}, "seen": {},
        "ach": {},
        "daily": {"date": None, "quests": [], "streak": 0, "todo_n": 0},
        "settings": {"auto_exp": True, "auto_battle": True, "auto_items": True, "toast": False, "bell": False,
                     "perm_bell": True},
        "buffs": {},
        "carry": {"full": 0, "exp": 0, "int": 0, "mp": 0},
        "call": None,
        "boss_flag": None,
        "timers": {"next_call": now + 40 * 60, "starve": 0.0, "egg_bonus": 0.0, "overfed_until": 0, "pat": 0},
        "legacy_exp": 0,
        "tok_day": {"date": day_key(now), "n": 0},
        # v3
        "family": {"gen": 1, "hall": [], "forms_seen": ["egg"], "base": {}},
        "quest_log": None,          # opencode todo 목록 = 메인 퀘스트
        "raid": {"week": None, "dmg": 0, "best": 0, "claimed": False, "cleared": False, "tries": {"date": None, "n": 0}},
        "expd_snap": None,          # 원정 도중 창이 비정상 종료되면 다음 실행 때 전리품을 챙긴다
        "anniv_w": 0,
        # v4
        "story": None,              # 메인 스토리 (부화하면 시작, new_story 참고)
    }


def _fill_defaults(dst, src):
    for k, v in src.items():
        if k not in dst:
            dst[k] = v
        elif isinstance(v, dict) and isinstance(dst[k], dict) and k not in ("dex", "seen", "ach", "stats", "floor", "base"):
            _fill_defaults(dst[k], v)
    return dst


def heir_name(name, gen):
    """'토큰이' → '토큰이 2세', '토큰이 2세' → '토큰이 3세' (12자 안에서 '세'가 잘리지 않게)"""
    base = re.sub(r"\s*\d+세$", "", (name or DEFAULT_NAME).strip()) or DEFAULT_NAME
    suffix = f" {gen}세"
    return base[:max(1, 12 - len(suffix))].rstrip() + suffix


def week_key(ts):
    y, w, _ = datetime.date.fromtimestamp(ts).isocalendar()
    return f"{y}-W{w:02d}"


def raid_boss_for(wk):
    try:
        y, w = wk.split("-W")
        return D.RAID_BOSSES[(int(y) * 53 + int(w)) % len(D.RAID_BOSSES)]
    except (ValueError, AttributeError):
        return D.RAID_BOSSES[0]


def raid_path(scope):
    return os.path.join(data_dir(), f"raid-{safe_scope(scope)}.json")


_RAID_CACHE = {"t": 0.0, "wk": None, "rows": []}


def raid_board(wk, now=None, fresh=False):
    """이번 주 레이드 참가 기록 (모든 인스턴스의 raid-*.json) → [dict(scope, name, lvl, dmg, cleared)]"""
    now = now or time.time()
    if not fresh and _RAID_CACHE["wk"] == wk and now - _RAID_CACHE["t"] < 5:
        return list(_RAID_CACHE["rows"])
    rows = []
    try:
        names = os.listdir(data_dir())
    except OSError:
        names = []
    for fn in names:
        if not (fn.startswith("raid-") and fn.endswith(".json")):
            continue
        r = read_json(os.path.join(data_dir(), fn))
        try:
            if not (isinstance(r, dict) and r.get("week") == wk):
                continue
            dmg, lvl = int(r.get("dmg") or 0), int(r.get("lvl") or 1)
            if dmg <= 0:
                continue
            rows.append(dict(scope=str(r.get("scope") or fn[5:-5]), name=str(r.get("name") or "?")[:12],
                             lvl=max(1, min(99, lvl)), dmg=max(0, dmg), cleared=bool(r.get("cleared"))))
        except (TypeError, ValueError):
            continue          # 손상된 파일 하나 때문에 모든 펫 창이 죽지 않게
    rows.sort(key=lambda r: -r["dmg"])
    _RAID_CACHE.update(t=now, wk=wk, rows=rows)
    return list(rows)


def raid_summary(wk, now=None, extra=None):
    """레이드 전체 현황: 보스, 공동 체력, 누적 피해, 격파 여부. extra: 아직 파일에 안 쓴 내 기록(dict)"""
    rows = raid_board(wk, now)
    if extra and extra.get("dmg", 0) > 0:
        rows = [r for r in rows if r["scope"] != extra["scope"]] + [extra]
        rows.sort(key=lambda r: -r["dmg"])
    R = D.RAID
    hp = sum(R["base"] + R["per_lvl"] * r["lvl"] for r in rows) or (R["base"] + R["per_lvl"] * (extra or {}).get("lvl", 1))
    dealt = sum(r["dmg"] for r in rows)
    cleared = any(r["cleared"] for r in rows) or (rows and dealt >= hp)
    return dict(week=wk, boss=raid_boss_for(wk), hp=hp, dealt=min(dealt, hp) if cleared else dealt,
                remaining=0 if cleared else max(0, hp - dealt), cleared=bool(cleared), rows=rows)


# ============================================================== 게임
class PetGame:
    def __init__(self, scope, name=None, clock=time.time, seed=None, persist=True, readonly=False):
        self.scope = scope or "pet"
        self.clock = clock
        self.rng = random.Random(seed)
        self.persist = persist
        self.readonly = readonly
        self.path = pet_path(self.scope)
        now = clock()
        # ---- 런타임 (저장 안 함)
        self.log = collections.deque(maxlen=80)
        self.banners = collections.deque(maxlen=12)
        self.banner = None
        self.fx = {}
        self.pops = []
        self.outbox = []
        self.ring = False
        self.speech = ("", 0.0)
        self.next_speech = now + 4
        self.battle = None
        self.expd = None
        self.event = None
        self.mg = None
        self.allies = {}
        self.stance = None
        self.busy_roots = {}
        self.anxious_until = 0.0
        self.manual_until = 0.0
        self.last_input = now
        self.last_activity = now
        self.absent_since = None
        self.last_tick = now
        self.last_save = now
        self.last_live = 0.0
        self.last_lock = 0.0
        self.last_reload = now
        self.welcome = None
        self.visitor = None
        self.last_summary = None
        self.enh_anim = None
        self.dirty = False
        self.lock_owner = False
        self.lock_id = "%x-%x" % (os.getpid(), random.getrandbits(40))
        self.readonly_reason = "lock" if readonly else None
        self.waits = {}           # opencode가 사용자 응답(허락/질문)을 기다리는 중: id -> dict
        self.last_housekeep = now
        self.last_raid_check = 0.0
        self.s = None
        self._load_or_create(name, now)
        if self.persist and not self.readonly:
            self._acquire_lock(now)
        if not self.readonly and self._loaded_existing:
            # 잠금을 얻은 창만 오프라인 정산/원정 전리품 회수를 한다 (관전 창이 먼저 하면 안 됨)
            self._recover_expedition(now)
            self._offline(now)

    # ------------------------------------------------------------ 기본 유틸
    def now(self):
        return self.clock()

    @property
    def p(self):
        return self.s["pet"]

    def inc(self, key, n=1):
        st = self.s["stats"]
        st[key] = st.get(key, 0) + n

    def stat(self, key):
        return self.s["stats"].get(key, 0)

    def note(self, text):
        self.log.append((time.strftime("%H:%M:%S", time.localtime(self.now())), fix_josa(text)))

    def flash(self, text, color="#6ABA23", dur=4.0):
        self.banners.append((fix_josa(text), color, dur))

    def pop(self, text, side, color="#6ABA23", dur=1.0):
        self.pops.append((text, side, color, self.now() + dur, self.now()))

    def notify(self, title, message, variant="info"):
        self.outbox.append((title, fix_josa(message), variant))

    def say(self, ctx, dur=7.0, **fmt):
        lines = D.LINES.get(ctx)
        if not lines:
            return
        try:
            text = self.rng.choice(lines).format(name=self.p["name"], kb=f"{self.p['kb']:.1f}", **fmt)
        except (KeyError, IndexError):
            text = self.rng.choice(lines)
        self.speech = (fix_josa(text), self.now() + dur)
        self.next_speech = self.now() + self.rng.uniform(28, 55)

    def is_egg(self):
        return self.p["form"] == "egg"

    def stage(self):
        return D.FORMS[self.p["form"]]["stage"]

    def age(self):
        h = self.s.get("hatched")
        return (self.now() - h) if h else 0

    def mark(self):
        self.dirty = True

    def input_seen(self):
        self.last_input = self.now()

    def present(self, now=None):
        now = now or self.now()
        return now - max(self.last_input, self.last_activity) < T["absent_after"]

    # ------------------------------------------------------------ 저장 / 불러오기
    def _load_or_create(self, name, now):
        self._loaded_existing = False
        status, s = read_save(self.path) if self.persist else ("missing", None)
        valid = isinstance(s, dict) and isinstance(s.get("pet"), dict) and isinstance(s.get("v"), int)
        if status == "ok" and valid and s["v"] > D.SAVE_VERSION:
            # 더 새로운 버전이 만든 저장 → 덮어쓰지 않도록 관전 모드로만 연다
            self.s = _fill_defaults(s, new_state(self.scope, name, now))
            self._sanitize(quiet=True)
            self.readonly, self.readonly_reason = True, "version"
            self.note("더 새로운 버전의 Terminal–1이 만든 저장 파일이에요. 덮어쓰지 않도록 관전 모드로 열었어요")
            return
        if status == "locked":
            # 다른 프로그램(백신 등)이 계속 잡고 있어 못 읽음 → 새 알로 덮어쓰지 않게 관전 모드
            self.s = new_state(self.scope, name, now)
            self.readonly, self.readonly_reason = True, "locked"
            self.note("저장 파일을 읽을 수 없어요 (다른 프로그램이 사용 중?). 덮어쓰지 않도록 관전 모드로 열었어요")
            return
        if status == "ok" and valid:
            self.s = _fill_defaults(self._migrate(s, now), new_state(self.scope, name, now))
            self._sanitize()
            self._loaded_existing = True
        else:
            backup = self._backup_corrupt() if status in ("ok", "corrupt") and self.persist else None
            self.s = new_state(self.scope, name, now)
            self._migrate_legacy()
            self.note("새 알을 받았다! …따뜻하다.")
            self.welcome = [f"새 친구가 도착했어요! 이름은 '{self.p['name']}'.",
                            "알을 [J] 쓰다듬어 주면 더 빨리 깨어나요.",
                            "opencode에게서 첫 응답을 받으면 부화 준비 완료!"]
            if backup:
                self.welcome = [f"저장 파일이 망가져 있어서 백업해 두고 새로 시작해요: {os.path.basename(backup)}"] + self.welcome
        self._daily_check(now, quiet=True)
        self.mark()

    def _backup_corrupt(self):
        """깨진 저장 파일은 지우지 않고 옆에 백업해 둔다"""
        dst = os.path.join(data_dir(), f"pet-{safe_scope(self.scope)}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}.json")
        try:
            os.replace(self.path, dst)
            return dst
        except OSError:
            return None

    def _migrate(self, s, now):
        """이전 버전 저장 → 현재 버전"""
        v = s.get("v", 1)
        if v < 3:
            p = s.get("pet", {})
            fam = s.setdefault("family", {"gen": 1, "hall": [], "forms_seen": ["egg"], "base": {}})
            seen = set(fam.get("forms_seen") or ["egg"])
            for f in (p.get("form"), p.get("prev_form")):
                if f in D.FORMS:
                    seen.add(f)
            if p.get("form") not in (None, "egg"):
                seen.update(["bit"] + (["byte"] if D.FORMS.get(p["form"], {}).get("stage", 0) >= 3 else []))
            fam["forms_seen"] = [f for f in D.FORM_ORDER if f in seen]
            if p.get("form") not in (None, "egg") and not p.get("personality"):
                r = random.Random(f"{s.get('scope')}:{s.get('created')}")
                p["personality"] = r.choice(sorted(D.PERSONALITIES))
                self.welcome = [f"◈ 업데이트 ◈ {p.get('name', DEFAULT_NAME)}에게 성격이 생겼어요: "
                                f"{D.PERSONALITIES[p['personality']]['name']}",
                                "새 기능: [G] 훈육(떼쓰기) · 진화/명예의 전당 · opencode 할 일 = 메인 퀘스트 · 주간 레이드 · 개발 퀴즈"]
            s["anniv_w"] = int(s.get("last_anniv", 0) or 0) // 7
            s["v"] = 3
        if s["v"] < 4:
            # 메인 스토리 추가: 이미 깬 지역까지(+다음 지역 하나)는 바로 열어 준다 (업데이트로 갈 수 있던 곳이 막히지 않게)
            p = s.get("pet", {})
            if s.get("hatched") and p.get("form") not in (None, "egg") and not isinstance(s.get("story"), dict):
                cleared = [z for z in (s.get("prog") or {}).get("cleared", []) if isinstance(z, str)]
                n = sum(1 for z in D.ZONES[:6] if z["id"] in cleared)
                s["story"] = new_story(now, max(D.STORY["fast"], n + 1))
                s["story"]["base"] = dict(s.get("stats") or {})     # 미션은 지금부터 센다
                self.welcome = (self.welcome or []) + [
                    f"◈ 업데이트 ◈ 메인 스토리 시즌 1 「{D.STORY['title']}」 시작!",
                    "[7] 스토리 화면: 챕터 대화 · 미션 · 챕터 보스 [B] · 커밋 조각 12개",
                    f"새 지역 6곳(야근의 탑 ~ 메인 브랜치 성)은 챕터가 열릴 때마다 {D.STORY['every']}일에 하나씩 열려요"]
            s["v"] = 4
        return s

    def _sanitize(self, quiet=False):
        """없어진 아이템/형태 같은 이상한 값 정리 (옛 저장 호환). 없어진 물건은 골드로 환불"""
        s, refund = self.s, 0
        inv = s["inv"]
        for key in ("items", "mats"):
            if not isinstance(inv.get(key), dict):
                inv[key] = {}
            for iid in list(inv[key]):
                n = inv[key][iid]
                if iid not in D.ITEMS or not isinstance(n, int) or n <= 0:
                    if iid not in D.ITEMS and isinstance(n, int) and n > 0:
                        refund += 10 * n
                    del inv[key][iid]
        gear = []
        for g in inv.get("gear") or []:
            if isinstance(g, dict) and is_gear(g.get("id")):
                g["plus"] = int(clamp(int(g.get("plus", 0) or 0), 0, D.ENHANCE_MAX))
                gear.append(g)
            else:
                refund += 50
        inv["gear"] = gear
        eq = s.get("equip") if isinstance(s.get("equip"), dict) else {}
        for slot in ("weapon", "armor", "acc"):
            g = eq.get(slot)
            if g and not (isinstance(g, dict) and D.ITEMS.get(g.get("id"), {}).get("kind") == slot):
                refund += 50
                g = None
            eq[slot] = g
        s["equip"] = eq
        inv["decos"] = [d for d in (inv.get("decos") or []) if D.ITEMS.get(d, {}).get("kind") == "deco"]
        inv["placed"] = [d for d in (inv.get("placed") or []) if d in inv["decos"]][:D.MAX_PLACED_DECO]
        p = s["pet"]
        if p.get("form") not in D.FORMS:
            p["form"] = "bit" if s.get("hatched") else "egg"
        if p.get("prev_form") not in D.FORMS:
            p["prev_form"] = None
        if p.get("form") != "egg" and p.get("personality") not in D.PERSONALITIES:
            p["personality"] = random.Random(str(s.get("created"))).choice(sorted(D.PERSONALITIES))
        if p.get("sick") not in (None, "cold", "overfed", "burnout"):
            p["sick"] = None
        call = s.get("call")
        if call and not (isinstance(call, dict) and call.get("kind") in D.CALLS):
            s["call"] = None
        if s.get("boss_flag") not in D.MONSTERS:
            s["boss_flag"] = None
        s["prog"]["cleared"] = [z for z in s["prog"].get("cleared", []) if any(zz["id"] == z for zz in D.ZONES)]
        fresh = new_state(self.scope, p.get("name"), s.get("created") or time.time())
        for key in ("family", "raid", "daily", "timers", "settings", "buffs", "carry", "tok_day"):
            if not isinstance(s.get(key), dict):
                s[key] = fresh[key]
        if s.get("quest_log") is not None and not isinstance(s.get("quest_log"), dict):
            s["quest_log"] = None
        if not isinstance(s.get("todo_sigs", []), list):
            s["todo_sigs"] = []
        fam = s["family"]
        if not isinstance(fam.get("hall"), list):
            fam["hall"] = []
        if not isinstance(fam.get("forms_seen"), list):
            fam["forms_seen"] = ["egg"]
        if not isinstance(fam.get("gen"), int) or fam["gen"] < 1:
            fam["gen"] = 1
        if not isinstance(s["raid"].get("tries"), dict):
            s["raid"]["tries"] = {"date": None, "n": 0}
        self._sanitize_story()
        if refund:
            s["gold"] = int(s.get("gold", 0)) + refund
            if not quiet:
                self.note(f"더 이상 없는 물건을 정리하고 {refund}G 로 환불했다")

    def _recover_expedition(self, now):
        """원정 도중 창이 강제로 닫혔으면(작업 관리자, 정전…) 다음 실행 때 전리품을 챙겨 온다"""
        snap = self.s.get("expd_snap")
        self.s["expd_snap"] = None
        if not isinstance(snap, dict):
            return
        c = snap.get("carry") or {}
        self.s["gold"] += int(c.get("gold", 0))
        for iid, n in (c.get("items") or {}).items():
            self.add_item(iid, int(n))
        for iid, n in (c.get("mats") or {}).items():
            self.add_item(iid, int(n))
        for iid in c.get("gear") or []:
            self.add_item(iid)
        z = D.ZONES[snap["zone"]]["short"] if isinstance(snap.get("zone"), int) and 0 <= snap["zone"] < len(D.ZONES) else "던전"
        msg = f"지난번 원정({z}) 도중 창이 닫혔어요. 전리품을 챙겨 돌아왔어요 (+{int(c.get('gold', 0))}G)"
        self.note(msg)
        self.welcome = (self.welcome or []) + [msg]

    def _migrate_legacy(self):
        old = read_json(legacy_path(self.scope)) if self.persist else None
        if not isinstance(old, dict) or "lvl" not in old:
            return
        self.s["gold"] += int(old.get("gold", 0))
        items = self.s["inv"]["items"]
        items["coffee"] = items.get("coffee", 0) + int(old.get("coffee", 0))
        self.s["stats"]["kills"] = int(old.get("kills", 0))
        self.s["legacy_exp"] = int(old.get("lvl", 1)) * 25
        self.s["ach"]["legacy"] = self.now()
        self.s["gold"] += next(a[3] for a in D.ACHIEVEMENTS if a[0] == "legacy")
        self.note(f"선대 용사 Lv.{old.get('lvl')}의 유산을 물려받았다! (골드·커피·경험치)")

    def save(self, force=False):
        if not self.persist or self.readonly:
            return
        now = self.now()
        if force or (self.dirty and now - self.last_save >= 1.0) or now - self.last_save >= T["save_every"]:
            self.s["last_seen"] = now
            e = self.expd
            self.s["expd_snap"] = (dict(zone=e["zone"], floor=e["floor"], carry=e["carry"], start=e["start"]) if e else None)
            if write_json(self.path, self.s):
                self.last_save = now
                self.dirty = False

    def _lock_fresh(self, lk, now):
        """다른 창의 잠금이 살아 있나 (시계가 뒤로 가서 미래 시각이 찍힌 잠금은 죽은 것으로 본다)"""
        if not (isinstance(lk, dict) and lk.get("id") not in (None, self.lock_id)):
            return False
        ts = lk.get("ts", 0)
        return isinstance(ts, (int, float)) and -5 <= now - ts < T["lock_stale"]

    def _acquire_lock(self, now):
        lk = read_json(lock_path(self.scope))
        if self._lock_fresh(lk, now):
            self.readonly, self.readonly_reason = True, "lock"
            self.note("다른 창에서 이 펫을 돌보는 중 → 관전 모드 ([O] 키로 이 창에서 돌보기)")
            return
        self.lock_owner = write_json(lock_path(self.scope), {"id": self.lock_id, "pid": os.getpid(), "ts": now})

    def _heartbeat(self, now):
        if self.lock_owner and now - self.last_lock >= T["lock_every"]:
            lk = read_json(lock_path(self.scope))
            if self._lock_fresh(lk, now):
                # 다른 창이 [O] 로 가져갔다 → 두 창이 같은 파일을 덮어쓰지 않게 이쪽은 관전 모드로
                self.lock_owner = False
                self.readonly, self.readonly_reason = True, "lock"
                self.expd = self.battle = self.event = self.mg = None
                self.note("다른 창이 이 펫을 가져갔어요 → 관전 모드")
                return
            write_json(lock_path(self.scope), {"id": self.lock_id, "pid": os.getpid(), "ts": now})
            self.last_lock = now

    def other_window_alive(self):
        return self._lock_fresh(read_json(lock_path(self.scope)), self.now())

    def take_over(self, force=False):
        """관전 모드 → 이 창에서 직접 돌보기. 다른 창이 아직 살아 있으면 force 일 때만 (확인용으로 None 반환)"""
        if not self.readonly:
            return False
        if self.readonly_reason == "version":
            self._nope("더 새로운 버전의 저장이라 이 창에선 돌볼 수 없어요")
            return False
        if self.other_window_alive() and not force:
            return None
        now = self.now()
        status, s = read_save(self.path, tries=3)
        valid = isinstance(s, dict) and isinstance(s.get("pet"), dict) and isinstance(s.get("v"), int)
        if status == "ok" and valid and s["v"] > D.SAVE_VERSION:
            self.readonly_reason = "version"
            self._nope("더 새로운 버전의 저장이라 이 창에선 돌볼 수 없어요")
            return False
        if status in ("locked", "corrupt") or (status == "ok" and not valid):
            self._nope("저장 파일을 지금 읽을 수 없어요 (잠시 뒤 다시)")
            return False
        loaded = status == "ok"
        if loaded:
            self.s = _fill_defaults(self._migrate(s, now), new_state(self.scope, None, now))
            self._sanitize()
        self.readonly, self.readonly_reason = False, None
        self.lock_owner = write_json(lock_path(self.scope), {"id": self.lock_id, "pid": os.getpid(), "ts": now})
        self.last_lock = now
        self.last_tick = now
        self.expd = self.battle = self.event = self.mg = None
        if loaded:
            self._recover_expedition(now)
            self._offline(now)
        self.note("이 창에서 돌보기 시작 (관전 모드 해제)")
        self.mark()
        return True

    def close(self):
        if self.readonly:
            return
        if self.battle and self.battle.get("over"):
            # 결과 연출(1~2초) 중에 닫아도 결과(보스 격파/기절/레이드 피해)는 그대로 반영
            self._battle_resolve(self.now())
        if self.battle and self.battle.get("raid") and not self.battle.get("over"):
            self.battle["over"] = "retreat"
            self._raid_finish(self.battle)
            self.battle = None
        if self.battle and self.battle.get("story") is not None and not self.battle.get("over"):
            self.battle["over"] = "retreat"          # 스토리 보스전은 창을 닫으면 페널티 없이 물러난다
            self._story_battle_end(self.battle, self.now())
            self.battle = None
        if self.expd:
            b = self.battle
            if b and not b.get("over"):
                c = self.expd["carry"]
                lost = int(c["gold"] * 0.3)
                c["gold"] -= lost
                self.end_expedition("창을 닫아 급히 퇴각" + (f" (골드 {lost}G 흘림)" if lost else ""))
            else:
                self.end_expedition("창을 닫아 귀환")
        self.save(force=True)
        self.write_live(force=True)
        if self.lock_owner:
            lk = read_json(lock_path(self.scope))
            if isinstance(lk, dict) and lk.get("id") == self.lock_id:
                try:
                    os.remove(lock_path(self.scope))
                except OSError:
                    pass

    def write_live(self, force=False):
        if not self.persist:
            return
        now = self.now()
        if force or now - self.last_live >= T["live_every"]:
            self.last_live = now
            write_json(live_path(self.scope), self.live_dict())

    def live_dict(self):
        p, now = self.p, self.now()
        f = D.FORMS[p["form"]]
        e = self.expd
        where = "exp" if e else ("sleep" if p["sleeping"] else "home")
        call = self.s["call"]
        if self.battle and self.battle.get("raid"):
            where = "raid"
        elif self.battle and self.battle.get("story") is not None:
            where = "story"
        w = next(iter(self.waits.values()), None)
        q = self.quest_progress()
        return dict(
            ts=now, name=p["name"], form=p["form"], form_name=f["name"], stage=f["stage"], color=f["color"],
            lvl=p["lvl"], face=D.FACES.get(self.face_key(now) or "normal", "o_o"),
            full=int(p["full"]), mood=int(p["mood"]), energy=int(p["energy"]), health=int(p["health"]),
            bugs=p["bugs"], sick=p["sick"], sleeping=p["sleeping"], where=where,
            zone=D.ZONES[e["zone"]]["short"] if e else None, floor=e["floor"] if e else None,
            battle=self.battle["mon"]["name"] if self.battle else None,
            call=D.CALLS[call["kind"]][0] if call else None, gold=self.s["gold"], title=p["title"],
            speech=self.speech[0] if self.speech[1] > now else "",
            tok_today=self.s["tok_day"]["n"] if self.s["tok_day"]["date"] == day_key(now) else 0,
            kills=self.stat("kills"), readonly=self.readonly,
            gen=self.s["family"]["gen"], personality=p.get("personality"), discipline=int(p.get("discipline", 50)),
            wait=(w["label"] if w else None), wait_kind=(w["kind"] if w else None),
            quest=(dict(done=q[0], total=q[1], cur=q[2]) if q else None),
            raid_dmg=self.s["raid"].get("dmg", 0) if self.s["raid"].get("week") == week_key(now) else 0,
            story=self.story_brief(),
        )

    # ------------------------------------------------------------ 오프라인 / 일일
    def _offline(self, now):
        el = now - self.s.get("last_seen", now)
        if el < 90:
            return
        p = self.p
        # 창이 꺼져 있던 동안의 호출은 없던 일로 (다시 켜자마자 '호출 무시'로 벌점 받지 않게)
        self.s["call"] = None
        self.s["timers"]["next_call"] = now + 10 * 60
        el_c = min(el, T["offline_cap"])
        hrs = el_c / 3600
        if p["form"] == "egg":
            self.welcome = (self.welcome or []) + [f"자리를 비운 {fmt_age(el)} 동안 알이 조용히 기다렸어요."]
            return
        b = dict(full=p["full"], mood=p["mood"], energy=p["energy"], health=p["health"], bugs=p["bugs"])
        f = T["offline_factor"]
        p["full"] = max(5.0, p["full"] - T["full_decay"] * hrs * f)
        p["mood"] = max(15.0, p["mood"] - T["mood_decay"] * hrs * f)
        p["energy"] = min(100.0, p["energy"] + 25 * hrs)
        p["health"] = clamp(p["health"] + (2 if p["full"] > 10 else -3) * hrs, 20.0, 100.0)
        p["bugs"] = min(T["bug_max"], p["bugs"] + min(3, int(el_c // (3 * 3600))))
        p["sleeping"] = False
        S = self.stats()
        p["hp"], p["mp"] = S["maxhp"], S["maxmp"]
        diff = []
        for k, label in (("full", "포만"), ("mood", "기분"), ("energy", "체력"), ("health", "건강")):
            d = int(p[k] - b[k])
            if d:
                diff.append(f"{label} {'+' if d > 0 else ''}{d}")
        if p["bugs"] > b["bugs"]:
            diff.append(f"버그 +{p['bugs'] - b['bugs']}")
        self.welcome = (self.welcome or []) + [f"자리를 비운 {fmt_age(el)} 동안…", (" · ".join(diff) or "별일 없었어요."),
                                               self.rng.choice(D.LINES["welcome"])]

    def _daily_check(self, now, quiet=False):
        key = day_key(now)
        d = self.s["daily"]
        if d.get("date") == key:
            return
        prev = d.get("date")
        if prev and key < prev:
            return          # 시계가 뒤로 갔다 → 출근 도장/퀘스트를 다시 주지 않는다
        d["todo_n"] = 0
        d["lists_n"] = 0
        d["games_n"] = 0
        d["quiz_int"] = False
        try:
            gap = (datetime.date.fromisoformat(key) - datetime.date.fromisoformat(prev)).days if prev else None
        except ValueError:
            gap = None
        d["streak"] = d.get("streak", 0) + 1 if gap == 1 else 1
        d["date"] = key
        seed = sum(ord(c) * (i + 1) for i, c in enumerate(self.scope + key))
        r = random.Random(seed)
        qs = []
        for t in r.sample(D.DAILY_QUESTS, 3):
            n = r.randint(t[2], t[3])
            qs.append(dict(id=t[0], text=t[1].format(n=n), target=n * (10000 if t[0] == "tokens" else 1),
                           prog=0, gold=t[4], exp=t[5], done=False))
        d["quests"] = qs
        # 어제의 개발 일지
        if prev:
            entry = self._make_diary(prev)
            if entry:
                self.s.setdefault("diary", []).append(entry)
                self.s["diary"] = self.s["diary"][-14:]
                lines = self.diary_lines(entry)
                self.welcome = (self.welcome or []) + ([""] if self.welcome else []) + lines
                if len(self.s["diary"]) >= 7:
                    self.unlock("diary7")
        d["snap"] = dict(self.s["stats"])
        bonus = 30 + 10 * min(d["streak"], 7)
        self.s["gold"] += bonus
        if not quiet or prev:
            self.flash(f"출근 도장 쾅! {d['streak']}일 연속 · +{bonus}G", "#95D85A", 5)
            self.note(f"출근 도장 {d['streak']}일 연속 (+{bonus}G). 오늘의 퀘스트가 도착했다.")
        if d["streak"] >= 7:
            self.unlock("streak7")
        if self.s.get("hatched"):
            weeks = int((now - self.s["hatched"]) // (7 * 86400))
            if weeks >= 1 and weeks > self.s.get("anniv_w", 0):
                # 그날 창을 안 켰어도 다음에 켤 때 챙겨준다 (한 번만)
                self.s["anniv_w"] = weeks
                self.add_item("cake")
                self.flash(f"◈ {weeks}주 기념일! {self.p['name']}이(가) 태어난 지 {weeks * 7}일 ◈ (케이크 선물)", "#6ABA23", 6)
                self.unlock("anniv")
        se = current_season(now)
        if se:
            self.flash(se["greet"].format(name=self.p["name"]), "#6ABA23", 7)
            self.note(f"시즌 이벤트: {se['name']}" + (f" (상점에 {D.ITEMS[se['item']]['name']} 입고)" if se.get("item") else ""))
        self.mark()

    def _make_diary(self, date):
        snap = self.s["daily"].get("snap") or {}
        st = self.s["stats"]
        diff = {k: st.get(k, 0) - snap.get(k, 0) for k in ("quests", "tokens", "tools", "errors", "kills", "floors", "allies",
                                                           "meals", "cleaned", "games", "compose", "faints", "bosses",
                                                           "todos_done", "raids", "scolds")}
        if not any(diff.values()):
            return None
        return dict(date=date, lvl=self.p["lvl"], form=self.p["form"], **diff)

    def diary_lines(self, e):
        md = e["date"][5:].replace("-", "/")
        todo = e.get("todos_done", 0)
        out = [f"◈ {md} 개발 일지 ◈",
               f"응답 {e['quests']}번 · 토큰 {fmt_num(e['tokens'])} · 도구 {e['tools']}번 · 에러 {e['errors']}번 · 컴포즈 {e['compose']}번"
               + (f" · 할 일 {todo}개 완료" if todo else ""),
               f"몬스터 {e['kills']}마리 · 던전 {e['floors']}층 · 보스 {e['bosses']} · 동료 합류 {e['allies']}번"
               + (f" · 레이드 {e['raids']}번" if e.get("raids") else ""),
               f"밥 {e['meals']} · 청소 {e['cleaned']} · 놀이 {e['games']}" + (f" · 훈육 {e['scolds']}" if e.get("scolds") else "")
               + (f" · 기절 {e['faints']}" if e["faints"] else "")]
        if e["tokens"] >= 1_000_000:
            c = "AI를 아주 열심히 부렸네요… 선배님께 커피라도 한 잔"
        elif e["errors"] >= 5:
            c = "에러가 많았던 하루. 오늘은 차근차근 가요"
        elif e["quests"] == 0:
            c = "어제는 AI랑 안 놀았네요. 쉬는 날이었나요?"
        elif e["quests"] >= 30:
            c = "응답을 서른 번 넘게 받았어요! 프롬프트 장인 인정"
        elif e["cleaned"] == 0 and e["meals"] == 0:
            c = "…저도 좀 챙겨주세요 (밥, 청소)"
        else:
            c = "오늘도 무사히 퇴근하길!"
        out.append(f"{self.p['name']}의 한마디: {c}")
        return [fix_josa(x) for x in out]

    def quest(self, kind, n=1):
        for q in self.s["daily"]["quests"]:
            if q["id"] == kind and not q["done"]:
                q["prog"] = min(q["target"], q["prog"] + n)
                if q["prog"] >= q["target"]:
                    q["done"] = True
                    self.s["gold"] += q["gold"]
                    self.gain_exp(q["exp"], quiet=True)
                    self.flash(f"일일 퀘스트 완료! {q['text']} (+{q['gold']}G)", "#95D85A", 4)
                    self.note(f"일일 퀘스트 완료: {q['text']}")
                    self.mark()

    # ------------------------------------------------------------ 업적
    def unlock(self, aid):
        if aid in self.s["ach"]:
            return False
        a = next((x for x in D.ACHIEVEMENTS if x[0] == aid), None)
        if not a:
            return False
        self.s["ach"][aid] = self.now()
        self.s["gold"] += a[3]
        if a[4] and not self.p["title"]:
            self.p["title"] = a[4]
        self.flash(f"업적 달성! 「{a[1]}」 +{a[3]}G", "#6ABA23", 4.5)
        self.note(f"업적: {a[1]} — {a[2]}")
        self.notify("업적 달성", f"{self.p['name']}: 「{a[1]}」")
        self.mark()
        return True

    def _check_counters(self):
        st, s = self.s["stats"], self.s
        checks = (("meal50", st.get("meals", 0) >= 50), ("tokens1m", st.get("tokens", 0) >= 1_000_000),
                  ("tokens10m", st.get("tokens", 0) >= 10_000_000), ("clean50", st.get("cleaned", 0) >= 50),
                  ("clean300", st.get("cleaned", 0) >= 300), ("kill100", st.get("kills", 0) >= 100),
                  ("kill1000", st.get("kills", 0) >= 1000), ("quests10", st.get("quests", 0) >= 10),
                  ("quests100", st.get("quests", 0) >= 100), ("rich10k", s["gold"] >= 10000),
                  ("allies50", st.get("allies", 0) >= 50), ("craft10", st.get("crafts", 0) >= 10),
                  ("deco4", len(s["inv"]["placed"]) >= 4),
                  ("todo100", st.get("todos_done", 0) >= 100), ("todolist10", st.get("todo_lists", 0) >= 10),
                  ("compact10", st.get("compactions", 0) >= 10), ("scold10", st.get("scolds", 0) >= 10),
                  ("discipline100", self.p.get("discipline", 0) >= 100),
                  ("dex_all", all(s["dex"].get(m, 0) > 0 for m in D.MONSTERS if m not in D.RAID_BOSSES)))
        for aid, ok in checks:
            if ok and aid not in s["ach"]:
                self.unlock(aid)

    # ------------------------------------------------------------ 능력치
    def _mods(self, key, default=1.0):
        """장신구 + 배치한 꾸미기의 배율 효과 곱"""
        v = default
        acc = self.s["equip"].get("acc")
        srcs = ([acc["id"]] if acc else []) + list(self.s["inv"]["placed"])
        for iid in srcs:
            e = D.ITEMS.get(iid, {}).get("eff", {})
            if key in e:
                v *= e[key]
        return v

    def _sum_eff(self, key):
        acc = self.s["equip"].get("acc")
        srcs = ([acc["id"]] if acc else []) + list(self.s["inv"]["placed"])
        return sum(D.ITEMS.get(i, {}).get("eff", {}).get(key, 0) for i in srcs)

    def pers(self, key, default=1.0):
        """성격 효과 값 (성격이 없거나 해당 효과가 없으면 default)"""
        pp = D.PERSONALITIES.get(self.p.get("personality") or "", {})
        return pp.get(key, default)

    def family_bonus(self, kind):
        """은퇴한 선대 수만큼 붙는 가문 보너스 (exp / gold 비율)"""
        past = min(self.s["family"].get("gen", 1) - 1, D.FAMILY["cap_gen"])
        return past * D.FAMILY["exp_per_gen" if kind == "exp" else "gold_per_gen"]

    def gold_mult(self):
        return 1 + self._sum_eff("gold") + self.family_bonus("gold")

    def exp_mult(self):
        now = self.now()
        m = 1 + self._sum_eff("exp") + self.family_bonus("exp") + self.pers("exp", 0.0)
        if self.s["buffs"].get("exp_boost", 0) > now:
            m *= 2
        if self.s["buffs"].get("inspired", 0) > now:
            m *= 1.1
        if self.p["mood"] < 25:
            m *= 0.8
        return m

    def stats(self):
        p = self.p
        lv = p["lvl"]
        mu = D.FORMS[p["form"]]["mult"]
        st = dict(hp=30 + 11 * lv, mp=12 + 2.6 * lv, atk=6 + 2.5 * lv, df=3 + 1.25 * lv,
                  int=5 + 1.7 * lv + p.get("int_bonus", 0), spd=6 + 0.7 * lv, luk=5 + 0.25 * lv)
        for k, m in zip(("hp", "atk", "df", "int", "spd", "luk"), mu):
            st[k] *= m
        for slot, g in self.s["equip"].items():
            if not g:
                continue
            e = D.ITEMS.get(g["id"], {}).get("eff", {})
            plus = g.get("plus", 0)
            for k in ("hp", "atk", "df", "int", "spd", "luk"):
                v = e.get(k, 0)
                if v > 0:
                    st[k] += v * (1 + 0.12 * plus) + plus * 0.8
                elif v < 0:
                    st[k] += v
        st["int"] += sum(D.ITEMS[i]["eff"].get("int", 0) for i in self.s["inv"]["placed"] if i in D.ITEMS)
        # 욕구에 따른 보정
        if p["full"] < 25:
            st["atk"] *= 0.85
        if p["energy"] < 20:
            st["spd"] *= 0.75
        if p["mood"] >= 80:
            st["luk"] += 5
        elif p["mood"] < 25:
            st["atk"] *= 0.9
        if p["sick"] in ("cold", "burnout"):
            for k in ("atk", "df", "int", "spd"):
                st[k] *= 0.88
        if p["sick"] == "overfed":
            st["spd"] *= 0.85
        ideal = D.FORMS[p["form"]]["ideal"]
        st["spd"] *= clamp(1 - max(0.0, p["kb"] - ideal * 1.5) / (ideal * 3), 0.7, 1.0)
        st["spd"] *= 1 + self.pers("spd", 0.0)
        # opencode agent 태세
        if self.stance == "build":
            st["atk"] *= 1.08
        elif self.stance == "plan":
            st["df"] *= 1.08
            st["int"] *= 1.08
        out = {k: max(1, int(round(v))) for k, v in st.items()}
        out["maxhp"], out["maxmp"] = out.pop("hp"), out.pop("mp")
        if p["hp"] is None or p["hp"] > out["maxhp"]:
            p["hp"] = out["maxhp"] if p["hp"] is None else min(p["hp"], out["maxhp"])
        if p["mp"] is None or p["mp"] > out["maxmp"]:
            p["mp"] = out["maxmp"] if p["mp"] is None else min(p["mp"], out["maxmp"])
        return out

    # ------------------------------------------------------------ 경험치 / 레벨 / 진화
    def gain_exp(self, n, quiet=False):
        if n <= 0:
            return
        p = self.p
        if p["form"] == "egg":
            self.s["legacy_exp"] = self.s.get("legacy_exp", 0) + n
            return
        p["exp"] += n * self.exp_mult()
        leveled = False
        while p["exp"] >= exp_to_next(p["lvl"]):
            p["exp"] -= exp_to_next(p["lvl"])
            p["lvl"] += 1
            leveled = True
        if leveled:
            S = self.stats()
            p["hp"], p["mp"] = S["maxhp"], S["maxmp"]
            self.fx["levelup"] = self.now() + 2.5
            self.flash(f"◈ LEVEL UP!! Lv.{p['lvl']} ◈  HP·MP 회복", "#6ABA23", 4)
            self.note(f"레벨 업! Lv.{p['lvl']}")
            self.say("levelup")
            new_sk = [sk["name"] for sid, sk in D.SKILLS.items() if sk["lvl"] == p["lvl"] and sid in D.BASIC_SKILLS]
            if new_sk:
                self.note(f"새 스킬 습득: {', '.join(new_sk)}")
            self.notify("레벨 업", f"{p['name']} Lv.{p['lvl']}")
            self.mark()

    def evolution_hint(self):
        p = self.p
        form = p["form"]
        key = "adult" if D.FORMS[form]["stage"] == 4 else form
        r = D.EVOLVE_RULES.get(key)
        if not r:
            return "최종 형태입니다. 전설 그 자체."
        if form == "egg":
            left = max(0, 180 - (self.now() - self.s["created"]) - self.s["timers"].get("egg_bonus", 0))
            if left <= 0 and self.stat("quests") < 1:
                wait = max(0, 600 - (self.now() - self.s["created"]) - self.s["timers"].get("egg_bonus", 0))
                return f"첫 응답을 기다리는 중… opencode에 아무거나 물어보세요 (늦어도 {int(wait // 60) + 1}분 뒤 부화)"
            return f"{r['hint']} · 남은 시간 약 {int(left // 60)}분 {int(left % 60)}초"
        return f"{r['hint']} · 현재 Lv.{p['lvl']}, 나이 {fmt_age(self.age())}"

    def _hatch(self):
        p, now = self.p, self.now()
        p["form"] = "bit"
        self.s["hatched"] = now
        p["full"], p["mood"], p["energy"] = 70.0, 85.0, 90.0
        p["personality"] = self.rng.choice(sorted(D.PERSONALITIES))
        p["discipline"] = 50.0
        fam = self.s["family"]
        self._saw_form("bit")
        fam["base"] = dict(self.s["stats"])      # 명예의 전당 기록용: 이 아이가 태어난 시점의 누적 기록
        S = self.stats()
        p["hp"], p["mp"] = S["maxhp"], S["maxmp"]
        self.fx["evolve"] = ("egg", "bit", now + 4.0)
        pp = D.PERSONALITIES[p["personality"]]
        self.flash(f"부화!! {p['name']} 탄생 ◈ 성격: {pp['name']}", "#6ABA23", 5)
        self.note(f"알이 깨지고 {p['name']}이(가) 태어났다! 성격: {pp['name']} — {pp['desc']}")
        self.notify("부화!", f"{p['name']}이(가) 태어났어요 ({pp['name']})")
        self.speech = ("…안녕하세요? 주인님?", now + 8)
        if self.s["family"].get("gen", 1) <= 1 or not self.s["family"].get("hall"):
            self.welcome = [f"{p['name']} 탄생! 성격: {pp['name']} — {pp['desc']}",
                            "호출(!)이 뜨면 25분 안에 응답: [F]밥 [C]청소 [Z]잠 [M]약 [P]놀기 [J]쓰담",
                            "필요한 게 다 찼는데 떼를 쓰면 [G] 훈육 (받아주면 응석받이가 돼요)",
                            "AI가 일하면 알아서 던전에 가요 · 모험 탭 맨 아래엔 모든 탭 펫이 함께 싸우는 주간 레이드 [W]",
                            f"[7] 스토리: 시즌 1 「{D.STORY['title']}」 1장이 열렸어요 (첫 주에 4장, 그다음 매주 한 장)"]
        self.unlock("hatch")
        if self.s.get("legacy_exp"):
            n = self.s["legacy_exp"]
            self.s["legacy_exp"] = 0
            self.gain_exp(n, quiet=True)
        if not self.story():
            # 첫 부화 = 메인 스토리 시작 (은퇴 후 새 세대는 가문의 이야기를 이어 간다)
            self._story_init(now)
        self.mark()

    def _evolve_to(self, new_form):
        p, now = self.p, self.now()
        old = p["form"]
        if D.FORMS[old]["stage"] == 4:
            p["prev_form"] = old
        p["form"] = new_form
        S = self.stats()
        p["hp"], p["mp"] = S["maxhp"], S["maxmp"]
        f = D.FORMS[new_form]
        self.fx["evolve"] = (old, new_form, now + 4.5)
        self.flash(f"진화!! {D.FORMS[old]['name']} → {f['name']}", "#6ABA23", 6)
        self.note(f"진화: {D.FORMS[old]['name']} → {f['name']} ({f['desc']})")
        self.notify("진화!", f"{p['name']}: {D.FORMS[old]['name']} → {f['name']}")
        self.say("evolve")
        self.unlock({2: "evolve2", 3: "evolve3", 4: "evolve4", 5: "evolve5"}.get(f["stage"], ""))
        if f["stage"] == 4 and p["care"] >= 90:
            self.unlock("careful")
        self._saw_form(new_form)
        if new_form == "maintainer":
            self.unlock("maintainer")
        self.mark()

    def _saw_form(self, form):
        """진화 도감(세대 누적)에 기록"""
        fam = self.s["family"]
        seen = set(fam.get("forms_seen") or [])
        if form not in seen:
            seen.add(form)
            fam["forms_seen"] = [f for f in D.FORM_ORDER if f in seen]
            if form not in ("egg", "bit"):
                self.note(f"진화 도감에 새 형태 등록: {D.FORMS[form]['name']}")
        if all(f in seen for f in D.ADULT_FORMS):
            self.unlock("forms6")

    def adult_scores(self):
        t, p = self.s["traits"], self.p
        care = p["care"]
        disc = p.get("discipline", 50)
        sc = {   # 각 성향을 '보통 사용자 3일치' 기준으로 정규화해서 비교
            "tenx": t["battle"] / 400 + (0.4 if care >= 70 else 0) + (0.15 if disc >= 70 else 0),
            "hunter": t["bug"] / 40,
            "architect": t["plan"] / 120 + (0.15 if disc >= 70 else 0),
            "zombie": (t["mistakes"] / 10 + (0.5 if p["form"] == "kiddie" else 0) + (0.3 if care < 50 else 0)
                       + (0.2 if disc < 30 else 0)),
            "monk": t["play"] / 15 + (0.4 if care >= 80 else 0) + (0.1 if disc >= 50 else 0),
        }
        vals = list(sc.values())
        sc["fullstack"] = 0.95 if max(vals) - min(vals) < 0.35 else 0.5
        for k, v in (self.pers("adult", {}) or {}).items():   # 성격이 살짝 섞인다
            sc[k] = sc.get(k, 0) + v
        return sc

    def _adult_form(self):
        sc = self.adult_scores()
        return max(sc, key=lambda k: (sc[k], k == "fullstack"))

    def _teen_form(self):
        p = self.p
        # 돌봄 점수가 기본, 훈육이 좋으면 보정 (훈육 50 = 보정 없음)
        return "junior" if p["care"] + 0.3 * (p.get("discipline", 50) - 50) >= 60 else "kiddie"

    def _legend_form(self):
        seen = set(self.s["family"].get("forms_seen") or [])
        return "maintainer" if sum(1 for f in D.ADULT_FORMS if f in seen) >= 4 else "singularity"

    def _check_retire_hint(self):
        fam = self.s["family"]
        if fam.get("retire_hint") == fam.get("gen", 1):
            return
        ok, _ = self.can_retire()
        if ok:
            fam["retire_hint"] = fam.get("gen", 1)
            self.flash("◈ 은퇴식 가능! 도감 [6] → 프로필 → [R] (명예의 전당 + 다음 세대 알)", "#6ABA23", 7)
            self.note("은퇴식을 열 수 있게 됐다. 서두를 필요는 없어요 (도감 > 프로필 > [R])")

    def _check_evolve(self):
        p = self.p
        form, lvl, age_m = p["form"], p["lvl"], self.age() / 60
        if form == "bit" and lvl >= 3 and age_m >= 20:
            self._evolve_to("byte")
        elif form == "byte" and lvl >= 8 and age_m >= 120:
            self._evolve_to(self._teen_form())
        elif form in ("junior", "kiddie") and lvl >= 16 and age_m >= 720:
            self._evolve_to(self._adult_form())
        elif (D.FORMS[form]["stage"] == 4 and lvl >= 35 and "z6" in self.s["prog"]["cleared"]
              and p["care"] >= 75 and age_m >= 7200):
            self._evolve_to(self._legend_form())

    # ------------------------------------------------------------ 표정
    def face_key(self, now=None):
        now = now or self.now()
        p = self.p
        if p["form"] == "egg":
            return None
        if p["sick"] == "burnout":
            return "burnout"
        if self.fx.get("hurt", 0) > now:
            return "hurt"
        if p["sleeping"]:
            return "sleep"
        if self.fx.get("scold", 0) > now:
            return "sad"
        if self.fx.get("eat", 0) > now:
            return "eat1" if int(now * 4) % 2 else "eat2"
        if self.fx.get("love", 0) > now or self.fx.get("levelup", 0) > now:
            return "love"
        if self.battle:
            return "battle"
        if p["sick"] == "cold":
            return "sick"
        if p["sick"] == "overfed":
            return "dizzy"
        if self.anxious_until > now:
            return "anxious"
        if p["full"] < 15:
            return "hungry"
        if p["energy"] < 15:
            return "sleepy"
        if p["mood"] < 25:
            return "sad"
        if self.s["call"]:
            k = self.s["call"]["kind"]
            return "angry" if k == "tantrum" else "bored" if k in ("play", "pat") else "sad"
        if self.waits:
            return "anxious"
        if int(now) % 6 == 0 and (now % 1) < 0.18:
            return "blink"
        if p["mood"] >= 80:
            return "joy" if int(now / 2) % 3 == 0 else "happy"
        return "normal"

    # ------------------------------------------------------------ 메인 틱
    def tick(self):
        now = self.now()
        if self.readonly:
            if now - self.last_reload >= 3 or now < self.last_reload:
                self.last_reload = now
                s = read_json(self.path)
                if isinstance(s, dict) and isinstance(s.get("pet"), dict) and isinstance(s.get("v"), int):
                    if s["v"] < 3:
                        s = self._migrate(s, now)
                    self.s = _fill_defaults(s, new_state(self.scope, None, now))
                    self._sanitize(quiet=True)
            self._tick_banners(now)
            return
        dt = clamp(now - self.last_tick, 0.0, 5.0)
        self.last_tick = now
        if now < self.last_save or now < self.last_live or now < self.last_lock:
            # 시계가 뒤로 갔다 → 저장/하트비트 타이머가 멈추지 않게 기준점을 당긴다
            self.last_save = min(self.last_save, now - T["save_every"])
            self.last_live = min(self.last_live, now)
            self.last_lock = min(self.last_lock, now - T["lock_every"])
            self.last_housekeep = min(self.last_housekeep, now)
            self.last_raid_check = min(self.last_raid_check, now)
        self._daily_check(now)
        self._tick_presence(now)
        if self.is_egg():
            self._tick_egg(now)
        else:
            self._tick_needs(now, dt)
            self._tick_calls(now)
            self._tick_sleep(now)
            self._tick_home_life(now)
            self._check_evolve()
            if self.stance == "plan" and self.busy_roots:
                self.s["traits"]["plan"] += dt / 60
        self._tick_expedition(now)
        if self.battle and not self.expd and (self.battle.get("raid") or self.battle.get("story") is not None):
            self._tick_battle(now)
        if not self.is_egg():
            self._tick_story(now)
        self._tick_minigame(now)
        self._tick_speech(now)
        self._tick_banners(now)
        self.pops = [x for x in self.pops if x[3] > now]
        if now - self.last_housekeep >= 30:
            self.last_housekeep = now
            self._housekeep(now)
        self._check_counters()
        self.s["last_seen"] = now
        if self.persist:
            self.save()
            self.write_live()
            self._heartbeat(now)

    def _housekeep(self, now):
        """가끔 한 번씩: 끝났다는 신호를 못 받은 작업/대기 정리, 레이드 보상 확인"""
        for sid, t0 in list(self.busy_roots.items()):
            if now - t0 > 3 * 3600:          # 3시간 넘게 busy 인 루트 세션은 신호 유실로 본다
                del self.busy_roots[sid]
        for wid, w in list(self.waits.items()):
            if now - w["since"] > T["wait_expire"]:
                del self.waits[wid]
        for sid, a in list(self.allies.items()):
            if now - a.get("since", now) > 3 * 3600:
                del self.allies[sid]
        if now - self.last_raid_check >= 60 and not self.is_egg():
            self.last_raid_check = now
            self._raid_claim_check(now)
        if not self.is_egg():
            self._check_retire_hint()

    def _tick_presence(self, now):
        here = self.present(now)
        if not here and self.absent_since is None:
            self.absent_since = now
            self.note(f"주인님이 자리를 비웠다… {self.p['name']}은(는) 조용히 기다린다 (천천히 닳음)")
        elif here and self.absent_since is not None:
            away = now - self.absent_since
            self.absent_since = None
            if self.p["sleeping"] and not (local_hour(now) >= 23 or local_hour(now) < 7):
                self.p["sleeping"] = False
            if away >= 2 * 3600 and not self.is_egg():
                self.welcome = [f"주인님 오셨어요! ({fmt_age(away + T['absent_after'])} 만이에요)",
                                self.rng.choice(D.LINES["welcome"])]

    def _tick_banners(self, now):
        if self.banner and self.banner[2] <= now:
            self.banner = None
        if not self.banner and self.banners:
            text, color, dur = self.banners.popleft()
            self.banner = (text, color, now + dur)

    def _tick_egg(self, now):
        age = now - self.s["created"] + self.s["timers"].get("egg_bonus", 0)
        if age >= 180 and (self.stat("quests") >= 1 or age >= 600):
            self._hatch()

    def _tick_needs(self, now, dt):
        p, h = self.p, dt / 3600
        h_real = h
        absent = self.absent_since is not None
        if absent:
            gone = now - self.absent_since
            h *= 0.0 if gone > 8 * 3600 else T["absent_factor"]   # 8시간 넘게 비우면 '겨울잠' (안 닳음)
            if gone > 2 * 3600 and not p["sleeping"] and not self.expd and not self.mg:
                p["sleeping"] = True
                self.note("주인님을 기다리다 잠들었다… zZ")
        away = self.expd is not None
        sleeping = p["sleeping"]
        p["full"] -= ((T["full_decay_sleep"] if sleeping else T["full_decay"]) * h * self._mods("full_decay")
                      * self.pers("full_decay"))
        md = T["mood_decay"] * self._mods("mood_decay") * self.pers("mood_decay")
        if p["full"] < 20:
            md *= 1.8
        if p["bugs"] >= 3:
            md *= 1.5 * self.pers("dirty_mood")
        if p["sick"]:
            md *= 1.5
        if sleeping:
            md *= 0.3
        p["mood"] -= md * h
        floor = max([D.ITEMS[i]["eff"].get("mood_floor", 0) for i in self.s["inv"]["placed"] if i in D.ITEMS] or [0])
        if floor and p["mood"] < floor:
            p["mood"] = min(floor, p["mood"] + 10 * h)
        if sleeping:
            p["energy"] += T["energy_sleep"] * h * self._mods("sleep_regen")
        else:
            ed = self.pers("energy_decay")
            hour = local_hour(now)
            if hour >= 22 or hour < 4:
                ed *= self.pers("night_energy")
            elif 6 <= hour < 10:
                ed *= self.pers("morning_energy")
            p["energy"] -= T["energy_decay"] * h * self._mods("energy_decay") * ed
        hv = 0.0
        if p["full"] <= 0:
            hv -= T["health_starve"]
        hv -= T["health_bug"] * max(0, p["bugs"] - 3)
        if p["energy"] <= 0:
            hv -= T["health_exhaust"]
        if p["sick"] == "cold":
            hv -= T["health_sick"]
        elif p["sick"] == "overfed":
            hv -= 2
        if hv == 0 and p["full"] > 25 and p["energy"] > 15 and not p["sick"]:
            hv += T["health_regen"]
        hv += 3 * self._sum_eff("regen")
        p["health"] += hv * h
        if p["sick"] == "burnout" and sleeping and hv >= 0:
            # 번아웃은 푹 자면 낫는다 (하룻밤 정도, 주인이 없어도 실제 시간 기준). 휴가 쿠폰이 빠른 길
            p["health"] += 6.0 * h_real
        if absent:
            # 주인이 없을 땐 건강이 25 밑으로 떨어지지 않게 천천히 받쳐준다 (시간 기준)
            p["health"] = max(p["health"], min(25.0, p["health"] + 20 * (dt / 3600)))
        if p["sick"] == "burnout" and p["health"] >= 50 and p["energy"] >= 80:
            p["sick"] = None
            self.flash(f"푹 쉬었더니 {p['name']}이(가) 번아웃에서 벗어났다!", "#95D85A", 5)
            self.note("번아웃에서 회복했다 (휴식)")
            self.unlock("burnout")
            self.mark()
        # 잘 지내면 돌봄 점수가 서서히 회복
        if not absent and p["full"] > 40 and p["mood"] > 40 and p["bugs"] < 3 and not p["sick"]:
            p["care"] = clamp(p["care"] + 1.0 * h, 0, 100)
        p["full"] = clamp(p["full"], 0.0, 120.0)
        p["mood"] = clamp(p["mood"], 0.0, 100.0)
        p["energy"] = clamp(p["energy"], 0.0, 100.0)
        p["health"] = clamp(p["health"], 0.0, 100.0)
        ideal = D.FORMS[p["form"]]["ideal"]
        p["kb"] = max(ideal * 0.5, p["kb"] - T["kb_decay"] * h)
        tm = self.s["timers"]
        # 굶주림 방치
        if p["full"] <= 0 and not absent:
            tm["starve"] = tm.get("starve", 0) + dt
            if tm["starve"] >= 1800:
                tm["starve"] = 0
                self._mistake("굶주림 방치")
        # 병
        if not p["sick"] and p["health"] < 35 and self.rng.random() < T["sick_chance"] * h:
            p["sick"] = "cold"
            self.flash(f"{p['name']}이(가) 감기에 걸렸다! [M] 약", "#F2F2F3", 5)
            self.note("감기에 걸렸다… 콜록")
            self.say("sick")
            self.mark()
        if p["sick"] == "overfed" and now >= tm.get("overfed_until", 0):
            p["sick"] = None
        if p["health"] <= 0 and p["sick"] != "burnout":
            p["sick"] = "burnout"
            p["mood"] = min(p["mood"], 20.0)
            self._mistake("번아웃")
            self.flash(f"{p['name']}이(가) 번아웃에 빠졌다… [M] 휴가 쿠폰/약", "#F2F2F3", 6)
            self.note("번아웃… 아무것도 할 수 없다. 휴가 쿠폰이나 약과 휴식이 필요하다.")
            self.notify("번아웃", f"{p['name']}이(가) 쓰러졌어요. 돌봐주세요!", "error")
            if self.expd:
                self.faint("번아웃")
            self.mark()
        # 버그 생성 (원정/레이드 중엔 방이 비어 있음)
        if self.battle and self.battle.get("raid"):
            away = True
        if not away:
            every = (T["bug_every_sleep"] if sleeping else T["bug_every"]) / (self._mods("bug_rate") * self.pers("bug_rate"))
            if p["bugs"] < T["bug_max"] and self.rng.random() < dt / every:
                p["bugs"] += 1
                self.fx["bug_spawn"] = (p["bugs"] - 1, now + 1.2)
                self.mark()
            # 집에서 HP/MP 회복
            S = self.stats()
            k = (2.0 if sleeping else 1.0) * dt / 10
            p["hp"] = min(S["maxhp"], p["hp"] + S["maxhp"] * T["home_hp_regen"] * k)
            p["mp"] = min(S["maxmp"], p["mp"] + S["maxmp"] * T["home_mp_regen"] * k)

    def _tick_home_life(self, now):
        """집에서 생기는 소소한 일 + 다른 펫의 방문"""
        p, tm = self.p, self.s["timers"]
        if self.visitor and self.visitor["until"] <= now:
            self.note(f"{self.visitor['name']}이(가) 돌아갔다. 또 놀러와!")
            self.visitor = None
        home = not (self.expd or self.mg or p["sleeping"] or self.absent_since is not None)
        if not home:
            return
        if now >= tm.get("next_home_event", 0):
            if tm.get("next_home_event"):
                text, eff = self.rng.choice(D.HOME_EVENTS)
                self.note(f"[집] {text}")
                self.flash(text, "#75A1C7", 4)
                self._apply_effects(eff)
            tm["next_home_event"] = now + self.rng.uniform(60, 150) * 60
        if now >= tm.get("next_visit", 0):
            first = not tm.get("next_visit")
            tm["next_visit"] = now + self.rng.uniform(15, 35) * 60
            if first or self.visitor or self.rng.random() > 0.35:
                return
            friends = self._find_friends(now)
            if friends:
                sc, sm = self.rng.choice(friends)
                self.visitor = dict(scope=sc, name=sm["name"], form=sm.get("form", "bit"), face=sm.get("face", "^_^"),
                                    color=sm.get("color", "#D4D6D8"), until=now + 90)
                p["mood"] = clamp(p["mood"] + 6, 0, 100)
                self.inc("visits")
                self.unlock("friends")
                self.flash(f"{sc}의 {sm['name']}이(가) 놀러왔다!", "#D4D6D8", 4)
                self.note(f"{sc}의 {sm['name']} ({sm.get('form_name', '')})이(가) 놀러왔다! 기분 +6")
                self.speech = (fix_josa(f"{sm['name']}아(야) 안녕! 같이 놀자!"), now + 6)

    def _find_friends(self, now):
        out = []
        try:
            for fn in os.listdir(data_dir()):
                if not (fn.startswith("pet-") and fn.endswith(".live.json")):
                    continue
                sc = fn[4:-10]
                if sc == safe_scope(self.scope):
                    continue
                sm = read_json(os.path.join(data_dir(), fn))
                if (isinstance(sm, dict) and now - sm.get("ts", 0) < 15 and sm.get("where") == "home"
                        and sm.get("form") not in (None, "egg")):
                    out.append((sc, sm))
        except OSError:
            pass
        return out

    def _mistake(self, why, light=False):
        p = self.p
        self.s["traits"]["mistakes"] += 0.5 if light else 1
        p["care"] = clamp(p["care"] - (3 if light else 7), 0, 100)
        self.inc("mistakes")
        self.note(f"돌봄 실수: {why} (돌봄 점수 {int(p['care'])})")
        self.mark()

    def _care_good(self, amount=1.0):
        p = self.p
        p["care"] = clamp(p["care"] + amount, 0, 100)
        self.s["traits"]["care"] += amount

    # ------------------------------------------------------------ 호출 (관심 요청)
    def _tick_calls(self, now):
        p, s = self.p, self.s
        call = s["call"]
        if call and self.absent_since is not None:
            s["call"] = None          # 주인이 없을 땐 호출을 거둬들인다 (실수 아님)
            call = None
        if call and now - call["since"] > T["call_expire"]:
            s["call"] = None
            s["timers"]["call_cool"] = now + T["call_cool"]
            if call["kind"] == "tantrum":
                # 떼쓰기를 그냥 두면 실수는 아니지만 버릇이 조금 나빠진다
                p["discipline"] = clamp(p.get("discipline", 50) - T["disc_ignore"], 0, 100)
                self.note(f"{p['name']}은(는) 떼쓰다 지쳐 잠잠해졌다 (훈육 -{T['disc_ignore']})")
                call = None
            else:
                self.inc("calls_missed")
                self._mistake(f"호출 무시 ({D.CALLS[call['kind']][0]})", light=call["kind"] in ("play", "pat"))
                self.speech = (fix_josa(f"…({p['name']}이(가) 삐졌다)"), now + 6)
                call = None
        if (call or self.expd or self.mg or self.battle or p["sleeping"] or self.absent_since is not None
                or now < s["timers"].get("call_cool", 0)):
            return
        kind = None
        if p["sick"] in ("cold", "burnout") and self.cure_available(p["sick"]):
            kind = "sick"
        elif p["full"] < 18:
            kind = "hungry"
        elif p["bugs"] >= 4:
            kind = "dirty"
        elif p["energy"] < 12:
            kind = "sleepy"
        elif now >= s["timers"].get("next_call", 0):
            s["timers"]["next_call"] = now + self.rng.uniform(T["call_min"], T["call_max"])
            fine = p["full"] >= 40 and p["mood"] >= 30 and not p["sick"]
            if fine and self.rng.random() < T["tantrum_chance"] * self.pers("tantrum"):
                kind = "tantrum"
            else:
                kind = self.rng.choice(["play", "pat"])
        if kind:
            s["call"] = {"kind": kind, "since": now}
            self.note(f"호출! {p['name']}: \"{D.CALLS[kind][0]}\" [{D.CALLS[kind][1]}]"
                      + (" (필요한 건 다 채워져 있어요. 떼쓰는 거예요!)" if kind == "tantrum" else ""))
            if kind == "tantrum":
                self.say("tantrum", dur=10)
                self.speech = (self.speech[0] + " [G]", self.speech[1])
            else:
                self.speech = (f"{D.CALLS[kind][0]} [{D.CALLS[kind][1]}]", now + 10)
            self.mark()

    def cure_available(self, sick):
        """지금 그 병을 고칠 방법이 있나 (가진 약 or 지금 살 수 있는 약). 없으면 호출/벌점 없음"""
        for iid, n in self.s["inv"]["items"].items():
            if n > 0 and sick in D.ITEMS.get(iid, {}).get("eff", {}).get("cure", []):
                return True
        for iid, it in D.ITEMS.items():
            if (it["shop"] and sick in it["eff"].get("cure", []) and it["lvl"] <= self.p["lvl"]
                    and self.price(iid) <= self.s["gold"]):
                return True
        return False

    def satisfy(self, kind):
        call = self.s["call"]
        p = self.p
        if call and call["kind"] == "tantrum" and kind in ("play", "pat"):
            # 떼쓰는데 받아주면 기분은 좋지만 버릇이 나빠진다
            self.s["call"] = None
            p["discipline"] = clamp(p.get("discipline", 50) - T["disc_spoil"], 0, 100)
            p["mood"] = clamp(p["mood"] + 5, 0, 100)
            self.say("spoiled")
            self.note(f"떼쓰는 걸 받아줬다… 응석받이가 되어 간다 (훈육 -{T['disc_spoil']})")
            self.mark()
            return
        if call and call["kind"] == kind:
            self.s["call"] = None
            self.inc("calls_ok")
            self._care_good(3.0 if kind in ("hungry", "dirty", "sick", "sleepy") else 2.0)
            self.p["mood"] = clamp(self.p["mood"] + 4, 0, 100)
            self.note("호출에 응답했다! 돌봄 점수 상승")
            self.mark()

    # ------------------------------------------------------------ 잠
    def _tick_sleep(self, now):
        p = self.p
        hour = local_hour(now)
        night = hour >= 22 or hour < 8
        if p["sleeping"]:
            if self.absent_since is not None or p["sick"] == "burnout":
                return      # 주인을 기다리며 자는 중 / 번아웃 요양 중엔 스스로 깨지 않는다
            if (p["energy"] >= 99.5 and not night) or (8 <= hour < 10 and p["energy"] > 70):
                p["sleeping"] = False
                self.note(f"{p['name']}이(가) 개운하게 일어났다!")
                self.say("morning" if hour < 11 else "happy")
                self.mark()
            return
        if self.expd or self.mg or self.battle:
            return
        if p["sick"] == "burnout" and now - self.last_input > 120:
            p["sleeping"] = True
            self.note("번아웃… 이불 속으로 들어가 요양을 시작했다 (푹 자면 천천히 나아요)")
            self.mark()
            return
        if p["energy"] <= 0:
            p["sleeping"] = True
            self._mistake("기절하듯 잠듦")
            self.note("체력이 바닥나 기절하듯 잠들었다…")
            self.mark()
        elif (hour >= 23 or hour < 7) and now - self.last_input > 900:
            p["sleeping"] = True
            self.note("새벽이라 스르륵 잠들었다… zZ")
            self.mark()

    def toggle_sleep(self):
        p = self.p
        if self.is_egg():
            return self._nope("알은 늘 자고 있어요")
        if self.expd or self.battle:
            return self._nope("모험 중에는 잘 수 없어요")
        if p["sleeping"]:
            p["sleeping"] = False
            if p["energy"] < 50:
                p["mood"] = clamp(p["mood"] - 8, 0, 100)
                self.speech = ("으으… 5분만 더… (잠투정)", self.now() + 5)
            else:
                self.say("happy")
            self.note("깨웠다")
        else:
            p["sleeping"] = True
            self.satisfy("sleepy")
            self.speech = ("잘 자요… zZ", self.now() + 4)
            self.note("불을 끄고 재웠다")
        self.mark()
        return True

    def scold(self):
        """[G] 훈육. 떼쓰는 중이면 정답(훈육↑), 아무 잘못 없는데 혼내면 억울해한다"""
        p, now = self.p, self.now()
        if self.is_egg():
            return self._nope("알을 혼낼 순 없어요…")
        if p["sleeping"]:
            return self._nope("자는 아이를 깨워서 혼내면 안 돼요")
        call = self.s["call"]
        if call and call["kind"] == "tantrum":
            self.s["call"] = None
            p["discipline"] = clamp(p.get("discipline", 50) + T["disc_scold"], 0, 100)
            p["mood"] = clamp(p["mood"] - 3, 0, 100)
            self._care_good(1.0)
            self.inc("scolds")
            self.quest("scold")
            self.say("scold")
            self.fx["scold"] = now + 1.6
            self.note(f"떼쓰는 {p['name']}을(를) 훈육했다 (훈육 {int(p['discipline'])})")
        else:
            p["mood"] = clamp(p["mood"] - 8, 0, 100)
            p["care"] = clamp(p["care"] - 2, 0, 100)
            self.fx["scold"] = now + 1.6
            self.say("scold_wrong")
            self.note("아무 잘못도 안 했는데 혼냈다… (기분 -8, 돌봄 -2)")
        self.mark()
        return True

    def _nope(self, msg):
        self.speech = (msg, self.now() + 4)
        return False

    # ------------------------------------------------------------ 대사
    def _tick_speech(self, now):
        if now < self.next_speech:
            return
        p = self.p
        if p["form"] == "egg":
            self.say("egg")
            return
        ctx = "idle"
        hour, wd = local_hour(now), weekday(now)
        if p["sick"] == "burnout":
            ctx = "burnout"
        elif p["sleeping"]:
            ctx = "sleeping"
        elif p["sick"] == "cold":
            ctx = "sick"
        elif p["sick"] == "overfed":
            ctx = "overfed"
        elif p["full"] < 8:
            ctx = "starving"
        elif p["full"] < 25:
            ctx = "hungry"
        elif p["bugs"] >= 4:
            ctx = "dirty"
        elif p["energy"] < 20:
            ctx = "sleepy"
        elif self.busy_roots:
            ctx = "busy"
        elif p["mood"] < 40:
            ctx = "bored"
        elif 0 <= hour < 5:
            ctx = "night"
        elif wd == 4 and hour >= 15 and self.rng.random() < 0.4:
            ctx = "friday"
        elif wd == 0 and hour < 12 and self.rng.random() < 0.3:
            ctx = "monday"
        elif self.s["gold"] >= 3000 and self.rng.random() < 0.15:
            ctx = "rich"
        elif p["mood"] >= 80 and self.rng.random() < 0.4:
            ctx = "happy"
        se = current_season(now)
        if se and ctx in ("idle", "happy") and self.rng.random() < 0.35:
            self.speech = (fix_josa(self.rng.choice(se["lines"])), now + 7)
            self.next_speech = now + self.rng.uniform(28, 55)
            return
        pl = self.pers("lines", None)
        if pl and ctx in ("idle", "happy", "bored") and self.rng.random() < 0.3:
            self.speech = (fix_josa(self.rng.choice(pl)), now + 7)
            self.next_speech = now + self.rng.uniform(28, 55)
            return
        self.say(ctx)

    # ------------------------------------------------------------ 돌봄 행동
    def items_of(self, kinds):
        inv = self.s["inv"]["items"]
        rows = [(iid, n) for iid, n in inv.items() if n > 0 and D.ITEMS.get(iid, {}).get("kind") in kinds]
        return sorted(rows, key=lambda x: (D.ITEMS[x[0]]["kind"], D.ITEMS[x[0]]["price"], x[0]))

    def add_item(self, iid, n=1):
        it = D.ITEMS.get(iid)
        if not it or n <= 0:
            return
        inv = self.s["inv"]
        if it["kind"] in ("weapon", "armor", "acc"):
            for _ in range(n):
                inv["gear"].append({"id": iid, "plus": 0})
        elif it["kind"] == "mat":
            inv["mats"][iid] = inv["mats"].get(iid, 0) + n
        elif it["kind"] == "deco":
            if iid not in inv["decos"]:
                inv["decos"].append(iid)
            else:
                self.s["gold"] += int(it["price"] * 0.4)
        else:
            inv["items"][iid] = inv["items"].get(iid, 0) + n
        self.mark()

    def _take(self, iid, n=1):
        inv = self.s["inv"]["items"]
        if inv.get(iid, 0) < n:
            return False
        inv[iid] -= n
        if inv[iid] <= 0:
            del inv[iid]
        return True

    def use_item(self, iid):
        """집에서 쓰기 (음식/음료/약/특수)"""
        p, now = self.p, self.now()
        it = D.ITEMS.get(iid)
        if not it or self.s["inv"]["items"].get(iid, 0) <= 0:
            return self._nope("그 아이템이 없어요")
        if self.is_egg():
            return self._nope("알은 아직 먹을 수 없어요")
        if p["sick"] == "burnout" and it["kind"] in ("food", "drink") and p["full"] > 30:
            return self._nope("…아무것도 먹기 싫어요 (번아웃)")
        e = it["eff"]
        kind = it["kind"]
        if kind in ("food", "drink"):
            if p["sleeping"]:
                return self._nope("자고 있어요… zZ")
            if kind == "food" and p["full"] >= 100:
                self.say("eat_full")
                return False
            was_hungry = p["full"] < 50
            self._take(iid)
            p["full"] = clamp(p["full"] + e.get("full", 0), 0, 120)
            mood = e.get("mood", 0)
            if kind == "food" and mood > 0:
                mood *= self.pers("food_mood")
            p["mood"] = clamp(p["mood"] + mood, 0, 100)
            p["energy"] = clamp(p["energy"] + e.get("energy", 0), 0, 100)
            p["health"] = clamp(p["health"] + e.get("health", 0), 0, 100)
            p["kb"] = max(0.3, p["kb"] + e.get("kb", 0))
            if e.get("exp"):
                self.gain_exp(e["exp"])
            if self.rng.random() < e.get("bug", 0):
                p["bugs"] = min(T["bug_max"], p["bugs"] + 1)
            if p["full"] > 100 and p["sick"] is None:
                p["sick"] = "overfed"
                self.s["timers"]["overfed_until"] = now + 40 * 60
                p["mood"] = clamp(p["mood"] - 6, 0, 100)
                self.say("eat_full")
                self.note("과식했다! 배탈 (소화제로 해결)")
            else:
                self.say("eat")
            self.fx["eat"] = now + 2.2
            self.fx["eat_item"] = (iid, now + 2.2)
            if kind == "food":
                self.inc("meals")
                self.quest("feed")
                if was_hungry:
                    self._care_good(0.7)
                self.satisfy("hungry")
            self.note(f"{it['name']}을(를) 먹였다")
        elif kind == "med":
            self._take(iid)
            p["health"] = clamp(p["health"] + e.get("health", 0), 0, 100)
            p["energy"] = clamp(p["energy"] + e.get("energy", 0), 0, 100)
            p["mood"] = clamp(p["mood"] + e.get("mood", 0), 0, 100)
            cured = p["sick"] and p["sick"] in e.get("cure", [])
            if cured:
                was = p["sick"]
                p["sick"] = None
                if was == "burnout":
                    p["health"] = max(p["health"], 45.0)
                    self.unlock("burnout")
                self.flash("완치! 몸이 가벼워졌다", "#95D85A", 3)
                self._care_good(1.0)
                self.satisfy("sick")
            self.speech = ("약 먹었어요… 쓰다…" if not cured else "다 나았어요! 고마워요!", now + 5)
            self.note(f"{it['name']} 사용" + (" → 완치" if cured else ""))
        elif kind == "special":
            if iid == "exp_boost":
                self._take(iid)
                self.s["buffs"]["exp_boost"] = max(now, self.s["buffs"].get("exp_boost", 0)) + 1800
                self.flash("야근 수당 발동! 30분간 경험치 2배", "#6ABA23", 4)
                self.note("야근 수당 사용 (경험치 x2, 30분)")
            else:
                return self._nope("그건 여기서 쓰는 게 아니에요")
        elif kind == "battle":
            return self._nope("전투 중에만 쓸 수 있어요")
        else:
            return False
        self.mark()
        return True

    def clean(self):
        p, now = self.p, self.now()
        if self.is_egg():
            return self._nope("알 주변은 깨끗해요")
        n = p["bugs"]
        if n <= 0:
            return self._nope("이미 깨끗해요!")
        p["bugs"] = 0
        self.add_item("bug_shell", n)
        self.inc("cleaned", n)
        self.s["traits"]["bug"] += n
        self.quest("clean", n)
        if n >= 3:
            self._care_good(1.0)
        p["mood"] = clamp(p["mood"] + 3, 0, 100)
        self.fx["clean"] = now + 1.6
        self.satisfy("dirty")
        self.say("clean")
        self.note(f"버그 {n}마리를 청소했다 (+버그 껍질 {n})")
        self.mark()
        return True

    def pat(self):
        p, now = self.p, self.now()
        tm = self.s["timers"]
        if self.is_egg():
            if now - tm.get("pat", 0) >= 4:
                tm["pat"] = now
                tm["egg_bonus"] = tm.get("egg_bonus", 0) + 12
                self.speech = (self.rng.choice(D.LINES["egg"]), now + 3)
                self.fx["wobble"] = now + 0.8
                self.inc("pats")
            return True
        if p["sleeping"]:
            return self._nope("zZ… (자는 중)")
        if now - tm.get("pat", 0) < 6:
            self.speech = ("헤헤… 그만 쓰다듬어도 돼요", now + 3)
            return False
        tm["pat"] = now
        p["mood"] = clamp(p["mood"] + 3, 0, 100)
        self.fx["love"] = now + 1.5
        self.inc("pats")
        self.quest("pat")
        self.satisfy("pat")
        self.say("pat")
        self.mark()
        return True

    def rename(self, new_name):
        new_name = (new_name or "").strip()[:12]
        if not new_name:
            return False
        if not self._take("nametag"):
            return self._nope("이름표가 필요해요 (상점 60G)")
        old = self.p["name"]
        self.p["name"] = new_name
        self.note(f"이름을 바꿨다: {old} → {new_name}")
        self.mark()
        return True

    # ------------------------------------------------------------ 상점 / 장비 / 꾸미기
    def daily_specials(self):
        key = self.s["daily"].get("date") or day_key(self.now())
        pool = sorted(i for i, it in D.ITEMS.items() if it["shop"] and it["price"] > 0 and it["kind"] != "mat")
        r = random.Random(sum(ord(c) for c in key) * 7 + len(self.scope))
        return r.sample(pool, 3)

    def price(self, iid):
        base = D.ITEMS[iid]["price"]
        return int(base * 0.7) if iid in self.daily_specials() else base

    def season_item(self):
        se = current_season(self.now())
        return se.get("item") if se else None

    def shop_list(self):
        out = []
        si = self.season_item()
        if si:
            out.append(dict(id=si, price=D.ITEMS[si]["price"], special=True, locked=False, owned=False, season=True))
        for iid, it in D.ITEMS.items():
            if not it["shop"] or it["price"] <= 0:
                continue
            owned = iid in self.s["inv"]["decos"] if it["kind"] == "deco" else False
            out.append(dict(id=iid, price=self.price(iid), special=iid in self.daily_specials(),
                            locked=it["lvl"] > self.p["lvl"], owned=owned))
        order = {"food": 0, "drink": 1, "med": 2, "battle": 3, "special": 4, "weapon": 5, "armor": 6, "acc": 7, "deco": 8}
        out.sort(key=lambda x: (not x["special"], order.get(D.ITEMS[x["id"]]["kind"], 9), D.ITEMS[x["id"]]["lvl"], x["price"]))
        return out

    def buy(self, iid):
        it = D.ITEMS.get(iid)
        if not it or not (it["shop"] or iid == self.season_item()):
            return self._nope("팔지 않는 물건이에요")
        if it["lvl"] > self.p["lvl"]:
            return self._nope(f"Lv.{it['lvl']}부터 살 수 있어요")
        if it["kind"] == "deco" and iid in self.s["inv"]["decos"]:
            return self._nope("이미 갖고 있어요")
        pr = self.price(iid)
        if self.s["gold"] < pr:
            return self._nope("골드가 부족해요… 원정 가요!")
        self.s["gold"] -= pr
        self.add_item(iid)
        self.inc("bought")
        self.note(f"{it['name']} 구매 (-{pr}G)")
        self.mark()
        return True

    def sell_list(self):
        inv, out = self.s["inv"], []
        for iid, n in sorted(inv["items"].items()):
            if n > 0:
                out.append(dict(kind="item", id=iid, n=n, price=max(1, int(D.ITEMS[iid]["price"] * 0.4))))
        for idx, g in enumerate(inv["gear"]):
            base = D.ITEMS[g["id"]]["price"] or 200 * (D.ITEMS[g["id"]]["rarity"] + 1)
            out.append(dict(kind="gear", idx=idx, id=g["id"], n=1, plus=g.get("plus", 0),
                            price=max(1, int(base * 0.4 * (1 + 0.3 * g.get("plus", 0))))))
        for iid, n in sorted(inv["mats"].items()):
            if n > 0:
                out.append(dict(kind="mat", id=iid, n=n, price=MAT_SELL.get(iid, 3)))
        for iid in inv["decos"]:
            if iid not in inv["placed"]:
                out.append(dict(kind="deco", id=iid, n=1, price=int(D.ITEMS[iid]["price"] * 0.4)))
        return out

    def sell(self, entry):
        inv = self.s["inv"]
        k = entry["kind"]
        if k == "item":
            if not self._take(entry["id"]):
                return False
        elif k == "gear":
            if entry["idx"] >= len(inv["gear"]):
                return False
            inv["gear"].pop(entry["idx"])
        elif k == "mat":
            if inv["mats"].get(entry["id"], 0) <= 0:
                return False
            inv["mats"][entry["id"]] -= 1
            if inv["mats"][entry["id"]] <= 0:
                del inv["mats"][entry["id"]]
        elif k == "deco":
            if entry["id"] not in inv["decos"] or entry["id"] in inv["placed"]:
                return False
            inv["decos"].remove(entry["id"])
        self.s["gold"] += entry["price"]
        self.note(f"{item_name(entry['id'])} 판매 (+{entry['price']}G)")
        self.mark()
        return True

    def equip(self, idx):
        inv = self.s["inv"]
        if idx >= len(inv["gear"]):
            return False
        g = inv["gear"][idx]
        it = D.ITEMS[g["id"]]
        if it["lvl"] > self.p["lvl"]:
            return self._nope(f"Lv.{it['lvl']}부터 장착할 수 있어요")
        slot = it["kind"]
        inv["gear"].pop(idx)
        old = self.s["equip"].get(slot)
        if old:
            inv["gear"].append(old)
        self.s["equip"][slot] = g
        self.stats()
        self.note(f"{gear_name(g)} 장착")
        self.mark()
        return True

    def unequip(self, slot):
        g = self.s["equip"].get(slot)
        if not g:
            return False
        self.s["inv"]["gear"].append(g)
        self.s["equip"][slot] = None
        self.stats()
        self.mark()
        return True

    def toggle_deco(self, iid):
        inv = self.s["inv"]
        if iid not in inv["decos"]:
            return False
        if iid in inv["placed"]:
            inv["placed"].remove(iid)
            self.note(f"{item_name(iid)}을(를) 치웠다")
        else:
            if len(inv["placed"]) >= D.MAX_PLACED_DECO:
                return self._nope(f"방이 좁아요 (최대 {D.MAX_PLACED_DECO}개)")
            inv["placed"].append(iid)
            self.note(f"{item_name(iid)}을(를) 방에 놓았다")
            self.p["mood"] = clamp(self.p["mood"] + 5, 0, 100)
        self.mark()
        return True

    # ------------------------------------------------------------ 공방: 강화 / 제작
    def enhance_info(self, g):
        it = D.ITEMS[g["id"]]
        plus = g.get("plus", 0)
        if plus >= D.ENHANCE_MAX:
            return None
        shard = D.SLOT_SHARD[it["kind"]]
        return dict(rate=D.ENHANCE_RATES[plus], gold=int(60 * (plus + 1) ** 1.9), shard=shard, need=2 + plus,
                    down=plus >= D.ENHANCE_DOWNGRADE_FROM, have=self.s["inv"]["mats"].get(shard, 0))

    def enhance_targets(self):
        out = [("equip", slot, g) for slot, g in self.s["equip"].items() if g]
        out += [("gear", i, g) for i, g in enumerate(self.s["inv"]["gear"])]
        return out

    def enhance(self, where, key, protect=True):
        g = self.s["equip"].get(key) if where == "equip" else (
            self.s["inv"]["gear"][key] if key < len(self.s["inv"]["gear"]) else None)
        if not g:
            return None
        info = self.enhance_info(g)
        if not info:
            self._nope("이미 +10 최대 강화예요!")
            return None
        mats = self.s["inv"]["mats"]
        if self.s["gold"] < info["gold"] or mats.get(info["shard"], 0) < info["need"]:
            self._nope("재료나 골드가 부족해요")
            return None
        self.s["gold"] -= info["gold"]
        mats[info["shard"]] -= info["need"]
        if mats[info["shard"]] <= 0:
            del mats[info["shard"]]
        ok = self.rng.random() < info["rate"]
        before = g.get("plus", 0)
        res = dict(ok=ok, before=before, name=item_name(g["id"]), protected=False, down=False)
        if ok:
            g["plus"] = before + 1
            self.inc("enh_ok")
            self.s["stats"]["enh_fail_streak"] = 0
            self.note(f"강화 성공!! {item_name(g['id'])} +{g['plus']}")
            if g["plus"] >= 7:
                self.unlock("enh7")
            if g["plus"] >= 10:
                self.unlock("enh10")
                self.notify("+10 달성", f"{item_name(g['id'])} +10 !!!")
        else:
            self.inc("enh_fail")
            self.inc("enh_fail_streak")
            if self.stat("enh_fail_streak") >= 5:
                self.unlock("enhfail5")
            if info["down"]:
                if protect and self._take("duck_charm"):
                    res["protected"] = True
                    self.note("강화 실패… 하지만 축복받은 러버덕이 지켜줬다!")
                else:
                    g["plus"] = before - 1
                    res["down"] = True
                    self.note(f"강화 실패… 키캡이 날아갔다 (+{before} → +{g['plus']})")
            else:
                self.note("강화 실패… 재료만 날아갔다")
        res["after"] = g.get("plus", 0)
        self.enh_anim = (res, self.now())
        self.stats()
        self.mark()
        return res

    def recipe_list(self):
        out = []
        mats = self.s["inv"]["mats"]
        for rid, r in D.RECIPES.items():
            ok = (self.p["lvl"] >= r["lvl"] and self.s["gold"] >= r["gold"]
                  and all(mats.get(k, 0) >= v for k, v in r["need"].items()))
            out.append(dict(id=rid, r=r, ok=ok, locked=self.p["lvl"] < r["lvl"]))
        return out

    def craft(self, rid):
        r = D.RECIPES.get(rid)
        if not r:
            return False
        mats = self.s["inv"]["mats"]
        if self.p["lvl"] < r["lvl"]:
            return self._nope(f"Lv.{r['lvl']}부터 만들 수 있어요")
        if self.s["gold"] < r["gold"] or any(mats.get(k, 0) < v for k, v in r["need"].items()):
            return self._nope("재료가 부족해요")
        self.s["gold"] -= r["gold"]
        for k, v in r["need"].items():
            mats[k] -= v
            if mats[k] <= 0:
                del mats[k]
        self.add_item(r["out"], r["qty"])
        self.inc("crafts")
        self.flash(f"제작 완료! {item_name(r['out'])} x{r['qty']}", "#95D85A", 3)
        self.note(f"제작: {item_name(r['out'])} x{r['qty']}")
        self.mark()
        return True

    # ------------------------------------------------------------ 원정
    def zones_info(self):
        out = []
        cleared = self.s["prog"]["cleared"]
        rel = self.story_released_n()
        for i, z in enumerate(D.ZONES):
            prev_ok = i == 0 or D.ZONES[i - 1]["id"] in cleared
            released = i < rel          # 지역 n 은 스토리 챕터 n 이 열려야 공개된다
            out.append(dict(idx=i, z=z, unlocked=prev_ok and released and self.p["lvl"] >= z["lvl"], prev_ok=prev_ok,
                            released=released, best=self.s["prog"]["floor"].get(z["id"], 0), cleared=z["id"] in cleared))
        return out

    def best_zone(self):
        """자동 원정 지역: 열린 지역 중 '1층 몬스터 레벨 ≤ 내 레벨-1' 인 가장 높은 곳"""
        info = self.zones_info()
        ok = [zi["idx"] for zi in info if zi["unlocked"]]
        if not ok:
            return 0
        fit = [i for i in ok if D.ZONES[i]["base"] <= self.p["lvl"] - 1] or ok[:1]
        return fit[-1]

    def can_depart(self):
        p = self.p
        if p["form"] == "egg":
            return False, "알은 모험을 못 가요"
        if self.expd:
            return False, "이미 원정 중이에요"
        if self.battle:
            return False, "챕터 보스전 중이에요" if self.battle.get("story") is not None else "레이드 중이에요"
        if p["sleeping"]:
            return False, "자고 있어요… zZ"
        if p["sick"] in ("burnout", "cold"):
            return False, "아파서 못 가요… [M]"
        if self.mg:
            return False, "미니게임 중이에요"
        if p["energy"] < 20:
            return False, "너무 피곤해요… (체력 20 필요)"
        if p["full"] < 15:
            return False, "배고파서 못 가요… [F]"
        S = self.stats()
        if p["hp"] < S["maxhp"] * 0.4:
            return False, "HP가 부족해요 (40% 필요)"
        return True, ""

    def start_expedition(self, zidx=None, auto=False, from_start=False):
        ok, why = self.can_depart()
        if not ok:
            if not auto:
                self._nope(why)
            else:
                self.note(f"자동 원정 취소: {why}")
            return False
        zi = self.zones_info()
        if zidx is None:
            zidx = self.best_zone()
        if not zi[zidx]["unlocked"]:
            return self._nope("아직 갈 수 없는 지역이에요")
        z = D.ZONES[zidx]
        best = self.s["prog"]["floor"].get(z["id"], 0)
        floor = 1 if from_start or best < 5 else 6
        if auto and z["base"] + floor - 1 > self.p["lvl"] + 2:
            floor = 1          # 체크포인트가 버거우면 1층부터 차근차근
        now = self.now()
        self.expd = dict(zone=zidx, floor=floor, enc=0, enc_total=2, state="walk", t=now, auto=auto, ret=False,
                         carry=dict(gold=0, items={}, mats={}, gear=[], kills=0, floors=0), start=now, status=None)
        self.battle = self.event = None
        if self.s["call"]:
            self.s["call"] = None
        self.say("depart")
        self.note(f"원정 출발 → {z['name']} B{floor}F" + (" (자동: AI 작업 중)" if auto else ""))
        self.mark()
        return True

    def recall(self):
        """사용자 귀환 요청"""
        e = self.expd
        if not e:
            return False
        if self.battle and not self.battle.get("over"):
            if self.battle["mon"]["rank"] == "boss":
                return self._nope("보스전 중에는 도망칠 수 없어요!")
            e["ret"] = True
            self.battle_action("flee")
            return True
        self.end_expedition("귀환 명령")
        return True

    def _should_return(self):
        e, p = self.expd, self.p
        S = self.stats()
        if e["ret"]:
            return "응답 도착 → 귀환" if e["auto"] else "귀환 명령"
        if p["sick"] in ("cold", "burnout"):
            return "몸이 안 좋아 귀환"
        if p["energy"] < 6:
            return "지쳐서 귀환"
        if p["full"] < 6:
            return "배고파서 귀환"
        guardian = e["enc"] >= e["enc_total"] - 1 and e["floor"] in (D.MINI_FLOOR, D.BOSS_FLOOR)
        boss_auto = guardian and e["floor"] == D.BOSS_FLOOR and e["auto"]
        if guardian and e["floor"] == D.BOSS_FLOOR and not e["auto"]:
            z = D.ZONES[e["zone"]]
            boss_lv = z["base"] + D.BOSS_FLOOR - 1 + 2
            if p["lvl"] < boss_lv - 6 and z["id"] not in self.s["prog"]["cleared"]:
                return f"보스(Lv.{boss_lv})가 너무 강해요… Lv.{boss_lv - 6}부터 도전할 수 있어요"
        if boss_auto:
            # 자동 원정은 무리하지 않는다: 보스 레벨보다 너무 낮으면, 또는 진 적이 있으면 두 레벨 더 크고 나서
            z = D.ZONES[e["zone"]]
            boss_lv = z["base"] + D.BOSS_FLOOR - 1 + 2
            failed_at = self.s["prog"].get("boss_fail", {}).get(z["id"], 0)
            need_lv = max(boss_lv - 4, failed_at + 2 if failed_at else 0)
            if p["lvl"] < need_lv and z["id"] not in self.s["prog"]["cleared"]:
                return f"보스는 더 강해진 뒤에 (자동 도전은 Lv.{need_lv}부터)"
        need = 0.75 if boss_auto else 0.6 if guardian else 0.3
        if p["hp"] < S["maxhp"] * need:
            if self.s["settings"]["auto_items"] and self._auto_heal_item() and p["hp"] >= S["maxhp"] * need:
                return None
            return "보스 앞에서 후퇴 (HP 부족)" if guardian else "HP 부족으로 귀환"
        return None

    def _auto_heal_item(self):
        for iid in ("hotfixpatch", "coffee"):
            if self.s["inv"]["items"].get(iid, 0) > 0:
                S = self.stats()
                self._take(iid)
                heal = int(S["maxhp"] * D.ITEMS[iid]["eff"]["hp_pct"])
                self.p["hp"] = min(S["maxhp"], self.p["hp"] + heal)
                self.note(f"{item_name(iid)}으로(로) 숨을 돌렸다 (+{heal} HP)")
                return True
        return False

    def end_expedition(self, reason, fainted=False):
        e = self.expd
        if not e:
            return
        c = e["carry"]
        if fainted:
            c["gold"] //= 2
            c["mats"] = {k: v // 2 for k, v in c["mats"].items() if v // 2 > 0}
        self.s["gold"] += c["gold"]
        for iid, n in c["items"].items():
            self.add_item(iid, n)
        for iid, n in c["mats"].items():
            self.add_item(iid, n)
        for iid in c["gear"]:
            self.add_item(iid)
        self.expd = None
        self.battle = None
        self.event = None
        z = D.ZONES[e["zone"]]
        loot = [f"{item_name(k)} x{v}" for k, v in list(c["items"].items()) + list(c["mats"].items())]
        loot += [item_name(g) for g in c["gear"]]
        self.last_summary = (dict(zone=z["name"], floor=e["floor"], floors=c["floors"], kills=c["kills"], gold=c["gold"],
                                  loot=loot, reason=reason, fainted=fainted, mins=(self.now() - e["start"]) / 60),
                             self.now() + 9)
        self.note(f"원정 종료 ({reason}): 층 {c['floors']}개 돌파, 몬스터 {c['kills']}, +{c['gold']}G"
                  + (f", {', '.join(loot[:4])}" if loot else ""))
        if not fainted:
            self.say("return")
        self.mark()

    def faint(self, why="기절"):
        p = self.p
        S = self.stats()
        p["hp"] = max(1, int(S["maxhp"] * 0.05))
        p["mood"] = clamp(p["mood"] - 15, 0, 100)
        self.inc("faints")
        self.say("faint")
        self.notify("기절…", f"{p['name']}이(가) 쓰러져 귀환했어요", "warning")
        self.end_expedition(why, fainted=True)

    def _tick_expedition(self, now):
        e = self.expd
        if not e:
            return
        if self.battle:
            self._tick_battle(now)
            return
        if self.event:
            self._tick_event(now)
            return
        if e["state"] == "walk":
            if now - e["t"] >= T["walk_time"]:
                why = self._should_return()
                if why:
                    self.end_expedition(why)
                    return
                self._next_encounter(now)
        elif e["state"] == "pause":
            if now - e["t"] >= T["pause_time"]:
                self._encounter_done(now)

    def _zone_level(self):
        e = self.expd
        z = D.ZONES[e["zone"]]
        return z["base"] + e["floor"] - 1

    def _next_encounter(self, now):
        e = self.expd
        z = D.ZONES[e["zone"]]
        last = e["enc"] >= e["enc_total"] - 1
        lvl = self._zone_level()
        if e["floor"] == D.MINI_FLOOR and last:
            self.start_battle(z["mini"], "mini", lvl + 1)
            return
        if e["floor"] >= D.BOSS_FLOOR and last:
            self.start_battle(z["boss"], "boss", lvl + 2)
            return
        flag = self.s.get("boss_flag")
        if flag and self.rng.random() < 0.5:
            self.s["boss_flag"] = None
            self.start_battle(flag, "boss", max(lvl, self.p["lvl"]))
            return
        r = self.rng.random()
        if r < 0.62:
            mid = self.rng.choice(z["normals"])
            self.start_battle(mid, "normal", lvl + self.rng.choice([0, 0, 1]))
        elif r < 0.74:
            g = int((5 + 2.4 * lvl) * self.rng.uniform(0.8, 1.6) * self.gold_mult())
            e["carry"]["gold"] += g
            drop = ""
            if self.rng.random() < 0.35:
                pool = [d for mid in z["normals"] for d, _ in D.MONSTERS[mid]["drops"]]
                iid = self.rng.choice(pool)
                self._carry_add(iid)
                drop = f" + {item_name(iid)}"
            self.note(f"보물상자 발견! +{g}G{drop}")
            self.pop(f"+{g}G", "pet", "#D4D6D8")
            e["state"], e["t"] = "pause", now
        elif r < 0.84:
            cands = [ev for ev in D.EVENTS if ev["zone"] <= e["zone"] + 1]
            ev = self.rng.choice(cands)
            manual = (now - self.last_input) < 90
            self.event = dict(ev=ev, deadline=now + (T["event_manual"] if manual else T["event_auto"]),
                              result=None, until=0)
            self.note(f"이벤트! {ev['text']}")
        elif r < 0.92:
            S = self.stats()
            p = self.p
            hh, mm = int(S["maxhp"] * 0.3), int(S["maxmp"] * 0.3)
            p["hp"] = min(S["maxhp"], p["hp"] + hh)
            p["mp"] = min(S["maxmp"], p["mp"] + mm)
            p["energy"] = clamp(p["energy"] + 4, 0, 100)
            self.note(f"휴게실 발견. 잠깐 쉬었다 (+{hh} HP, +{mm} MP)")
            e["state"], e["t"] = "pause", now
        else:
            st = self.story()
            c = D.CHAPTERS[st["ch"]] if st and st["phase"] in ("play", "boss") else None
            if c and c["zone"] == z["id"] and c.get("notes") and self.rng.random() < 0.6:
                self.note("◈ " + self.rng.choice(c["notes"]))      # 지금 챕터의 지역에서만 보이는 이야기 조각
            else:
                self.note(self.rng.choice(NOTHING_LINES))
            e["state"], e["t"] = "pause", now

    def _carry_add(self, iid, n=1):
        c = self.expd["carry"]
        kind = D.ITEMS[iid]["kind"]
        if kind in ("weapon", "armor", "acc"):
            c["gear"].extend([iid] * n)
        elif kind == "mat":
            c["mats"][iid] = c["mats"].get(iid, 0) + n
        else:
            c["items"][iid] = c["items"].get(iid, 0) + n

    def _encounter_done(self, now):
        e = self.expd
        if not e:
            return
        e["enc"] += 1
        if e["enc"] >= e["enc_total"]:
            p = self.p
            S = self.stats()
            e["carry"]["floors"] += 1
            self.inc("floors")
            self.quest("floor")
            p["energy"] = clamp(p["energy"] - T["floor_energy"], 0, 100)
            p["full"] = clamp(p["full"] - T["floor_full"], 0, 120)
            p["kb"] = max(0.3, p["kb"] - 0.03)
            p["hp"] = min(S["maxhp"], p["hp"] + S["maxhp"] * 0.05)
            zid = D.ZONES[e["zone"]]["id"]
            fl = self.s["prog"]["floor"]
            fl[zid] = max(fl.get(zid, 0), e["floor"])
            self.note(f"B{e['floor']}F 돌파!")
            e["floor"] = min(D.BOSS_FLOOR, e["floor"] + 1)
            e["enc"] = 0
            e["enc_total"] = 2 if e["floor"] in (D.MINI_FLOOR, D.BOSS_FLOOR) else self.rng.choice([2, 2, 3])
            self.mark()
        e["state"], e["t"] = "walk", now

    # ------------------------------------------------------------ 이벤트
    def _tick_event(self, now):
        ev = self.event
        if ev["result"]:
            if now >= ev["until"]:
                self.event = None
                if self.expd and not self.battle:
                    self._encounter_done(now)
            return
        if now >= ev["deadline"]:
            self.event_choose(self._auto_choice(ev["ev"]), auto=True)

    def _auto_choice(self, ev):
        S = self.stats()
        low = self.p["hp"] < S["maxhp"] * 0.5
        best, best_v = 0, -1e9
        for i, (label, outs) in enumerate(ev["options"]):
            v = 0.0
            for prob, eff, _ in outs:
                x = (eff.get("gold", 0) / 8 + eff.get("exp", 0) / 6 + eff.get("hp_pct", 0) * (80 if low else 30)
                     + eff.get("mood", 0) / 2 + eff.get("energy", 0) / 3 + eff.get("full", 0) / 4
                     + 8 * eff.get("items", 0) + (10 if eff.get("item") else 0) + (12 if eff.get("mat") else 0)
                     + 15 * eff.get("int", 0) + (8 if eff.get("buff") else 0)
                     - 6 * eff.get("bugs", 0) - (10 if eff.get("status") else 0)
                     - ((30 if (low or self.p["lvl"] < 6) else 4) if eff.get("fight") else 0))
                v += prob * x
            if v > best_v:
                best, best_v = i, v
        return best

    def event_choose(self, idx, auto=False):
        ev = self.event
        if not ev or ev["result"]:
            return False
        opts = ev["ev"]["options"]
        if not (0 <= idx < len(opts)):
            return False
        label, outs = opts[idx]
        r, acc = self.rng.random(), 0.0
        pick = outs[-1]
        for o in outs:
            acc += o[0]
            if r < acc:
                pick = o
                break
        _, eff, msg = pick
        ev["result"] = (label, msg, auto)
        ev["until"] = self.now() + 3.2
        self.note(f"{'(자동) ' if auto else ''}[{label}] → {msg}")
        self._apply_effects(eff)
        if self.battle:          # 선택 결과로 전투가 시작되면 이벤트 창은 닫고 전투로
            self.event = None
        self.inc("events")
        self.mark()
        return True

    def _apply_effects(self, eff):
        p, e = self.p, self.expd
        S = self.stats()
        if "gold" in eff:
            g = int(eff["gold"] * self.gold_mult())
            if e:
                e["carry"]["gold"] += g
            else:
                self.s["gold"] += g
        if "exp" in eff:
            self.gain_exp(eff["exp"])
        if "hp_pct" in eff:
            p["hp"] = min(S["maxhp"], p["hp"] + int(S["maxhp"] * eff["hp_pct"]))
        if "mp_pct" in eff:
            p["mp"] = min(S["maxmp"], p["mp"] + int(S["maxmp"] * eff["mp_pct"]))
        for k in ("energy", "mood", "full", "health"):
            if k in eff:
                p[k] = clamp(p[k] + eff[k], 0, 120 if k == "full" else 100)
        if "bugs" in eff:
            p["bugs"] = min(T["bug_max"], p["bugs"] + eff["bugs"])
        if "item" in eff:
            (self._carry_add if e else self.add_item)(eff["item"])
        if "items" in eff:
            pool = ["coffee", "energydrink", "hotfixpatch", "cacheflush", "tokenjelly", "vitamin", "kimbap", "rmrf"]
            for _ in range(eff["items"]):
                iid = self.rng.choice(pool)
                (self._carry_add if e else self.add_item)(iid)
        if "mat" in eff:
            iid, n = eff["mat"]
            if e:
                self._carry_add(iid, n)
            else:
                self.add_item(iid, n)
        if "buff" in eff:
            self.s["buffs"][eff["buff"]] = self.now() + 240
        if "status" in eff and e:
            e["status"] = eff["status"]
        if "int" in eff:
            p["int_bonus"] = p.get("int_bonus", 0) + eff["int"]
        if eff.get("cure"):
            if e:
                e["status"] = None
        if "ach" in eff:
            self.unlock(eff["ach"])
        if "fight" in eff and e:
            mid = eff["fight"]
            rank = "boss" if mid in ("friday", "errdragon", "dragon429") else "normal"
            self.start_battle(mid, rank, max(self._zone_level(), self.p["lvl"] if rank == "boss" else 0))

    # ------------------------------------------------------------ 전투
    def start_battle(self, mid, rank, level):
        now = self.now()
        ms = monster_stats(mid, level, rank)
        pst = {}
        e = self.expd
        if e and e.get("status"):
            pst[e["status"]] = 3
            e["status"] = None
        self.battle = dict(mid=mid, mon=ms, pst=pst, round=0, next=now + 1.2, over=None, end_at=0.0,
                           last_dmg=0, cd={}, pair=0, wait_since=now, last_round_at=0.0, defend=False, enrage=0)
        self.s["seen"][mid] = self.s["seen"].get(mid, 0) + 1
        if rank == "boss":
            self.flash(f"!! 보스 출현 !! {ms['name']}", "#F2F2F3", 3.5)
            self.notify("보스 출현", f"{self.p['name']} vs {ms['name']}", "warning")
        elif rank == "mini":
            self.flash(f"! 중간 보스 ! {ms['name']}", "#B8CEE0", 3)
        self.note(f"야생의 {ms['name']}이(가) 나타났다! (Lv.{ms['level']})")

    def _tick_battle(self, now):
        b = self.battle
        if b["over"]:
            if now >= b["end_at"]:
                self._battle_resolve(now)
            return
        auto = self.s["settings"]["auto_battle"] and now >= self.manual_until
        if auto:
            if now >= b["next"]:
                self.battle_round(None)
        elif now - b["wait_since"] > 25:
            self.battle_round(None)

    def available_skills(self):
        p, out = self.p, []
        for sid in D.BASIC_SKILLS:
            sk = D.SKILLS[sid]
            if p["lvl"] >= sk["lvl"]:
                out.append(sid)
        ults = []
        f = D.FORMS[p["form"]]
        if f["stage"] >= 4 and f["ult"]:
            ults.append(f["ult"])
        if f["stage"] == 5 and p.get("prev_form") and D.FORMS[p["prev_form"]]["ult"]:
            ults.append(D.FORMS[p["prev_form"]]["ult"])
        return out + ults

    def battle_items(self):
        return [(iid, n) for iid, n in self.items_of(("battle", "drink", "med"))
                if any(k in D.ITEMS[iid]["eff"] for k in ("hp_pct", "mp_pct", "bomb", "buff")) or iid == "vitamin"]

    def battle_action(self, kind, arg=None):
        b, now = self.battle, self.now()
        if not b or b["over"] or now - b["last_round_at"] < 0.3:
            return False
        self.manual_until = now + 15
        disc = self.p.get("discipline", 50)
        if disc < 30 and kind in ("skill", "item", "defend") and self.rng.random() < 0.12:
            # 훈육이 부족하면 가끔 명령을 안 듣는다
            self.note(f"{self.p['name']}은(는) 말을 안 듣고 제멋대로 공격했다! (훈육 부족)")
            return self.battle_round(("attack", None))
        return self.battle_round((kind, arg))

    def _pet_eff(self, S, b):
        pst = b["pst"]
        atk = S["atk"] * (0.75 if pst.get("curse") else 1)
        if b["mon"]["rank"] != "normal":
            atk *= 1 + self.pers("boss_atk", 0.0)
        df = S["df"] * (1.6 if pst.get("def_up") else 1) * (2.0 if b["defend"] else 1)
        spd = S["spd"] * (1.4 if pst.get("spd_up") else 1)
        now = self.now()
        crit = 0.04 + S["luk"] * 0.004 + (0.15 if pst.get("focus") or self.s["buffs"].get("focus", 0) > now else 0)
        return atk, df, spd, crit

    def _dmg(self, atk, df, power=1.0, pierce=0.0, crit=0.0):
        base = atk * power * self.rng.uniform(0.9, 1.1)
        d = base - df * 0.55 * (1 - pierce)
        d = max(base * 0.12, d)
        is_crit = self.rng.random() < crit
        if is_crit:
            d *= 1.75
        return max(1, int(round(d))), is_crit

    def battle_round(self, action):
        b, now = self.battle, self.now()
        if not b or b["over"]:
            return False
        b["round"] += 1
        S = self.stats()
        p, m = self.p, b["mon"]
        act = action or self._auto_action(b, S)
        b["defend"] = act[0] == "defend"
        _, _, pspd, _ = self._pet_eff(S, b)
        pet_first = pspd >= m["spd"] * 0.9
        seq = ["pet", "ally", "mon"] if pet_first else ["mon", "pet", "ally"]
        for who in seq:
            if b["over"]:
                break
            if who == "pet":
                self._pet_act(act, S, b)
            elif who == "ally":
                self._allies_act(S, b)
            else:
                self._enemy_act(S, b)
            self._check_end(b)
        if not b["over"]:
            # 라운드 종료 처리
            pst = b["pst"]
            if pst.get("poison"):
                d = max(1, int(S["maxhp"] * 0.05))
                p["hp"] -= d
                self.note(f"버그 감염으로 -{d}")
                self.pop(f"-{d}", "pet", "#B8CEE0")
            for k in list(pst):
                if k in ("poison", "curse", "def_up", "spd_up", "focus", "confuse"):
                    pst[k] -= 1
                    if pst[k] <= 0:
                        del pst[k]
            for k in list(m["st"]):
                if k != "stun":
                    m["st"][k] -= 1
                    if m["st"][k] <= 0:
                        del m["st"][k]
            for k in list(b["cd"]):
                b["cd"][k] -= 1
                if b["cd"][k] <= 0:
                    del b["cd"][k]
            p["mp"] = min(S["maxmp"], p["mp"] + 2 + S["int"] * 0.02)
            if b["pair"] > 0:
                b["pair"] -= 1
            self._check_end(b)
            if b.get("raid") and not b["over"] and b["round"] >= b["rounds_max"]:
                b["over"], b["end_at"] = "timeup", now + T["result_time"]
                self.note("레이드 제한 시간 종료! 공대 대기실로 돌아간다")
        b["next"] = now + T["round_time"]
        b["last_round_at"] = now
        b["wait_since"] = now
        b["defend"] = False
        return True

    def _auto_action(self, b, S):
        p, m = self.p, b["mon"]
        skills = self.available_skills()
        boss = m["rank"] != "normal"
        use_items = self.s["settings"]["auto_items"]
        items = dict(self.battle_items())
        hp_ratio = p["hp"] / S["maxhp"]
        if hp_ratio < 0.3:
            if use_items and items.get("hotfixpatch"):
                return ("item", "hotfixpatch")
            if use_items and items.get("coffee"):
                return ("item", "coffee")
            if "duck" in skills and p["mp"] >= D.SKILLS["duck"]["mp"]:
                return ("skill", "duck")
            if "revert" in skills and p["mp"] >= D.SKILLS["revert"]["mp"] and b["last_dmg"] > S["maxhp"] * 0.1:
                return ("skill", "revert")
            if "meditate" in skills and "meditate" not in b["cd"]:
                return ("skill", "meditate")
        if b["pst"].get("poison") and use_items and items.get("vitamin") and hp_ratio < 0.6:
            return ("item", "vitamin")
        if boss and p["mp"] < S["maxmp"] * 0.2 and use_items:
            for iid in ("cacheflush", "energydrink"):
                if items.get(iid):
                    return ("item", iid)
        if "meditate" in skills and "meditate" not in b["cd"] and p["mp"] < S["maxmp"] * 0.3:
            return ("skill", "meditate")
        ult = [s for s in skills if D.SKILLS[s]["lvl"] == 0 and s != "meditate"]
        if ult and p["mp"] >= D.SKILLS[ult[0]]["mp"] and (boss or m["hp"] > m["maxhp"] * 0.5) and self.rng.random() < 0.6:
            return ("skill", ult[0])
        if boss and "tdd" in skills and not b["pst"].get("def_up") and hp_ratio < 0.7 and p["mp"] >= 14:
            return ("skill", "tdd")
        dmg_sk = [s for s in ("rust", "hotfix", "slash") if s in skills and p["mp"] >= D.SKILLS[s]["mp"]]
        if dmg_sk and self.rng.random() < (0.55 if boss else 0.3):
            return ("skill", dmg_sk[0])
        return ("attack", None)

    def _hit_mon(self, dmg, crit, label=None, color="#6ABA23"):
        b = self.battle
        m = b["mon"]
        m["hp"] -= dmg
        now = self.now()
        self.fx["mon_hit"] = now + 0.35
        self.pop(("☼" if crit else "") + f"-{dmg}", "mon", "#6ABA23" if crit else color)
        return dmg

    def _pet_act(self, act, S, b):
        p, m, now = self.p, b["mon"], self.now()
        pst = b["pst"]
        name = p["name"]
        atk, _, _, crit = self._pet_eff(S, b)
        for st in ("stun", "sleep"):
            if pst.get(st):
                pst[st] -= 1
                if pst[st] <= 0:
                    del pst[st]
                self.note(f"{name}은(는) {'쿨다운 중…' if st == 'stun' else '회의 중에 졸았다… zZ'} (행동 불가)")
                return
        if pst.get("confuse") and self.rng.random() < 0.35:
            d = max(1, int(S["maxhp"] * 0.04))
            p["hp"] -= d
            self.note(f"{name}은(는) 혼란에 빠져 자기 발을 밟았다! -{d}")
            self.pop(f"-{d}", "pet", "#B8CEE0")
            return
        kind, arg = act
        if kind == "attack":
            if self.rng.random() < self._dodge(m["spd"], S["spd"]) * 0.6:
                self.note(f"{name}의 공격이 빗나갔다!")
                self.pop("MISS", "mon", "#81888D")
                return
            dmg, is_crit = self._dmg(atk, m["df"], 1.0, 0.0, crit)
            self._hit_mon(dmg, is_crit)
            self.note(self.rng.choice(ATTACK_LINES).format(p=name) + (" CRITICAL☼" if is_crit else "") + f" -{dmg}")
            w = self.s["equip"].get("weapon")
            if w and D.ITEMS[w["id"]]["eff"].get("stun") and self.rng.random() < D.ITEMS[w["id"]]["eff"]["stun"]:
                m["st"]["stun"] = 1
                self.note(f"{item_name(w['id'])}의 굉음에 {m['name']}이(가) 기절했다!")
        elif kind == "defend":
            p["mp"] = min(S["maxmp"], p["mp"] + S["maxmp"] * 0.05)
            self.note(f"{name}은(는) 방어 태세! (받는 피해 감소)")
        elif kind == "item":
            self._battle_item(arg, S, b)
        elif kind == "flee":
            if m["rank"] == "boss":
                self.note("보스에게서는 도망칠 수 없다! (rate limit 은 피할 수 없다)")
                return
            chance = clamp(0.45 + (S["spd"] - m["spd"]) / 60, 0.2, 0.9)
            if self.rng.random() < chance:
                b["over"], b["end_at"] = "fled", now + 0.8
                self.note(f"{name}은(는) 슬쩍 git stash 하고 도망쳤다!")
            else:
                self.note("도망 실패! 퇴근은 아직이다.")
        elif kind == "skill":
            self._skill(arg, S, b)

    def _skill(self, sid, S, b):
        p, m, now = self.p, b["mon"], self.now()
        sk = D.SKILLS.get(sid)
        if not sk or sid not in self.available_skills():
            return self._pet_act(("attack", None), S, b)
        if sid in b["cd"]:
            self.note(f"{sk['name']}은(는) 아직 재사용 대기 중!")
            return self._pet_act(("attack", None), S, b)
        if p["mp"] < sk["mp"]:
            self.note("MP 부족! (opencode가 일하면 MP가 차요)")
            return self._pet_act(("attack", None), S, b)
        p["mp"] -= sk["mp"]
        atk, _, _, crit = self._pet_eff(S, b)
        power_atk = atk * 0.55 + S["int"] * 0.75
        name = p["name"]
        self.fx["skill"] = (sk["name"], now + 1.1)
        k = sk["kind"]
        if k == "dmg":
            dmg, is_crit = self._dmg(power_atk, m["df"], sk["power"], 1.0 if sk.get("pierce") else 0.0, crit)
            self._hit_mon(dmg, is_crit, color="#95D85A")
            self.note(f"{name}의 {sk['name']}!! -{dmg}" + (" CRITICAL☼" if is_crit else ""))
            if sk.get("stun"):
                m["st"]["stun"] = sk["stun"]
                self.note(f"{m['name']}이(가) 멈췄다! ({sk['stun']}턴)")
            if sk.get("recoil") and self.rng.random() < sk["recoil"]:
                d = int(S["maxhp"] * 0.1)
                p["hp"] -= d
                self.note(f"핫픽스가 다른 곳을 터뜨렸다! 역풍 -{d}")
        elif k == "multi":
            total = 0
            for _ in range(sk["hits"]):
                dmg, is_crit = self._dmg(power_atk, m["df"], sk["power"], 0.5 if sk.get("half_pierce") else 0.0, crit)
                m["hp"] -= dmg
                total += dmg
            self.fx["mon_hit"] = now + 0.5
            self.pop(f"x{sk['hits']} -{total}", "mon", "#95D85A")
            self.note(f"{name}의 {sk['name']}!! {sk['hits']}연타 -{total}")
        elif k == "heal":
            heal = int(S["maxhp"] * sk["power"] + S["int"] * 0.3)
            p["hp"] = min(S["maxhp"], p["hp"] + heal)
            for st in ("poison", "curse", "confuse"):
                b["pst"].pop(st, None)
            self.pop(f"+{heal}", "pet", "#95D85A")
            self.note(f"{name}의 {sk['name']}! 오리에게 설명하다 보니 나았다 +{heal}")
        elif k == "buff":
            b["pst"][sk["buff"]] = sk["turns"] + 1
            if sk.get("extra"):
                b["pst"][sk["extra"]] = sk["turns"] + 1
            self.note(f"{name}의 {sk['name']}! ({sk['desc']})")
        else:
            self._special_skill(sid, sk, S, b, power_atk, crit)

    def _special_skill(self, sid, sk, S, b, power_atk, crit):
        p, m = self.p, b["mon"]
        name = p["name"]
        if sid == "revert":
            heal = int(b["last_dmg"] * 1.5 + S["maxhp"] * 0.1)
            p["hp"] = min(S["maxhp"], p["hp"] + heal)
            self.pop(f"+{heal}", "pet", "#95D85A")
            self.note(f"{name}의 git revert! 방금 받은 피해를 되돌렸다 +{heal}")
        elif sid == "so":
            r = self.rng.random()
            if r < 0.35:
                dmg, c = self._dmg(power_atk, m["df"], 3.0, 0, crit)
                self._hit_mon(dmg, c, color="#95D85A")
                self.note(f"스택오버플로우 검색: '채택된 답변' 발견!! -{dmg}")
            elif r < 0.6:
                heal = int(S["maxhp"] * 0.25)
                p["hp"] = min(S["maxhp"], p["hp"] + heal)
                self.note(f"스택오버플로우 검색: 비슷한 질문에서 힌트를 얻었다 +{heal}")
            elif r < 0.8:
                self.note("스택오버플로우 검색: 'closed as duplicate'… 아무 일도 없었다")
            else:
                m["st"]["stun"] = 1
                self.note(f"스택오버플로우 검색: 복붙 성공! {m['name']}이(가) 당황했다 (1턴 멈춤)")
        elif sid == "pair":
            b["pair"] = 3
            self.note(f"{name}의 페어 프로그래밍! 짝꿍이 합류했다 (3턴)")
        elif sid == "allnighter":
            ratio = clamp(p["hp"] / S["maxhp"], 0, 1)
            power = 1.2 + 4.8 * (1 - ratio)
            dmg, c = self._dmg(power_atk, m["df"], power, 0.2, crit)
            self._hit_mon(dmg, c, color="#F2F2F3")
            self.note(f"{name}의 밤샘 러시!! (x{power:.1f}) -{dmg}")
        elif sid == "meditate":
            mp, hp = int(S["maxmp"] * 0.6), int(S["maxhp"] * 0.2)
            p["mp"] = min(S["maxmp"], p["mp"] + mp)
            p["hp"] = min(S["maxhp"], p["hp"] + hp)
            b["cd"]["meditate"] = 4
            self.note(f"{name}은(는) 명상에 잠겼다… 옴… (+{mp} MP, +{hp} HP)")
        elif sid == "fullstack":
            dmg, c = self._dmg(power_atk, m["df"], 2.5, 0, crit)
            self._hit_mon(dmg, c, color="#95D85A")
            heal = int(S["maxhp"] * 0.2)
            p["hp"] = min(S["maxhp"], p["hp"] + heal)
            b["pst"]["def_up"] = 4
            self.note(f"{name}의 풀스택 오버드라이브!! -{dmg}, +{heal} HP, 방어↑")
        elif sid == "singularity":
            dmg, c = self._dmg(power_atk, m["df"], 7.0, 0.5, crit)
            self._hit_mon(dmg, c, color="#6ABA23")
            for st in ("def_up", "spd_up", "focus"):
                b["pst"][st] = 4
            self.note(f"{name}의 특이점!!! 세상이 잠깐 멈췄다… -{dmg}")
        elif sid == "lgtm":
            for st in ("poison", "curse", "confuse", "stun", "sleep"):
                b["pst"].pop(st, None)
            heal = int(S["maxhp"] * 0.35)
            p["hp"] = min(S["maxhp"], p["hp"] + heal)
            dmg, c = self._dmg(power_atk, m["df"], 4.5, 0.3, crit)
            self._hit_mon(dmg, c, color="#95D85A")
            m["st"]["stun"] = 2
            self.pop(f"+{heal}", "pet", "#95D85A")
            self.note(f"{name}의 LGTM 승인!! 모든 게 머지됐다 -{dmg}, +{heal} HP, {m['name']} 2턴 멈춤")

    def _battle_item(self, iid, S, b):
        p = self.p
        if not iid or not self._take(iid):
            self.note("그 아이템이 없다!")
            return
        e = D.ITEMS[iid]["eff"]
        if "hp_pct" in e:
            heal = int(S["maxhp"] * e["hp_pct"])
            p["hp"] = min(S["maxhp"], p["hp"] + heal)
            self.pop(f"+{heal}", "pet", "#95D85A")
            self.note(f"{item_name(iid)} 사용! +{heal} HP")
        if "mp_pct" in e:
            mp = int(S["maxmp"] * e["mp_pct"])
            p["mp"] = min(S["maxmp"], p["mp"] + mp)
            self.note(f"{item_name(iid)} 사용! +{mp} MP")
        if "bomb" in e:
            dmg = int(40 + 9 * p["lvl"])
            self._hit_mon(dmg, False, color="#F2F2F3")
            self.note(f"rm -rf 폭탄 투척!! 흔적도 없이 -{dmg}")
        if "buff" in e:
            b["pst"][e["buff"]] = 4
            self.note(f"{item_name(iid)} 전개! 방어력 상승")
        if iid == "vitamin":
            b["pst"].pop("poison", None)
            self.note("비타민으로 버그 감염을 떨쳐냈다")
        if "energy" in e:
            p["energy"] = clamp(p["energy"] + e["energy"] * 0.5, 0, 100)

    def _dodge(self, att_spd, def_spd):
        return clamp(0.03 + (def_spd - att_spd) / max(1, att_spd + def_spd) * 0.3, 0.0, 0.25)

    def _allies_act(self, S, b):
        m = b["mon"]
        helpers = list(self.allies.values())
        if b["pair"] > 0:
            helpers.append(dict(name="짝꿍"))
        for a in helpers:
            if b["over"] or m["hp"] <= 0:
                break
            dmg = max(1, int((S["atk"] * 0.45 + self.p["lvl"]) * self.rng.uniform(0.8, 1.2) - m["df"] * 0.3))
            m["hp"] -= dmg
            self.pop(f"-{dmg}", "mon", "#75A1C7")
            self.note(f"{a['name']}의 지원 공격! -{dmg}")

    def _enemy_act(self, S, b):
        p, m = self.p, b["mon"]
        if m["hp"] <= 0:
            return
        if m["st"].get("stun"):
            m["st"]["stun"] -= 1
            if m["st"]["stun"] <= 0:
                del m["st"]["stun"]
            self.note(f"{m['name']}은(는) 멈춰 있다…")
            return
        _, pdf, pspd, _ = self._pet_eff(S, b)
        atk = m["atk"]
        if m["special"] == "enrage":
            b["enrage"] += 1
            atk *= 1 + 0.08 * b["enrage"]
        sp = m["special"] if (m["special"] and m["special"] != "reboot" and self.rng.random() < m["chance"]) else None
        mult, hits, extra = 1.0, 1, None
        if sp:
            name, desc = D.SPECIALS[sp]
            self.note(f"{m['name']}의 {name}! ({desc})")
            if sp == "stacktrace":
                b["pst"]["poison"] = 3
            elif sp == "scope":
                for st in ("def_up", "spd_up", "focus"):
                    b["pst"].pop(st, None)
                mult = 0.6
            elif sp == "meeting":
                b["pst"]["sleep"] = 1
                mult = 0.5
            elif sp == "ratelimit":
                b["pst"]["stun"] = 1
                mult = 1.4
            elif sp == "leak":
                d = int(S["maxmp"] * 0.15)
                p["mp"] = max(0, p["mp"] - d)
                self.pop(f"MP-{d}", "pet", "#B8CEE0")
                mult = 0.5
            elif sp == "curse":
                b["pst"]["curse"] = 3
                mult = 0.7
            elif sp == "double":
                hits, mult = 2, 0.75
            elif sp == "heal":
                h = int(m["maxhp"] * 0.2)
                m["hp"] = min(m["maxhp"], m["hp"] + h)
                self.pop(f"+{h}", "mon", "#95D85A")
                return
            elif sp == "race":
                if self.rng.random() < 0.5:
                    hits, mult = 2, 0.8
                else:
                    self.note("…레이스에서 졌다. 헛손질!")
                    return
            elif sp == "billing":
                e = self.expd
                pool = e["carry"]["gold"] if e else 0
                steal = min(pool, max(5, int(pool * 0.1)))
                if e and steal:
                    e["carry"]["gold"] -= steal
                    extra = f"전리품 골드 -{steal}G"
                mult = 0.8
            elif sp == "oom":
                mult = 1.8
            elif sp == "confuse":
                b["pst"]["confuse"] = 2
                mult = 0.6
            if extra:
                self.note(extra)
        total = 0
        for _ in range(hits):
            if self.rng.random() < self._dodge(m["spd"], pspd):
                self.note(f"{p['name']}은(는) 공격을 피했다! (로컬에선 잘 되는데?)")
                self.pop("MISS", "pet", "#81888D")
                continue
            dmg, is_crit = self._dmg(atk, pdf, mult, 0.0, 0.05)
            p["hp"] -= dmg
            total += dmg
            self.pop(("☼" if is_crit else "") + f"-{dmg}", "pet", "#F2F2F3")
        if total:
            b["last_dmg"] = total
            self.fx["hurt"] = self.now() + 0.4
            if not sp:
                self.note(self.rng.choice(ENEMY_LINES).format(m=m["name"]) + f" -{total}")

    def _check_end(self, b):
        if b["over"]:
            return
        p, m, now = self.p, b["mon"], self.now()
        if b.get("raid"):
            if m["hp"] <= 0:
                m["hp"] = 0
                b["over"], b["end_at"] = "win", now + T["result_time"] + 0.8
                self.note(f"막타!! {m['name']}이(가) 쓰러졌다! 주간 레이드 격파!")
            elif p["hp"] <= 0:
                p["hp"] = 0
                b["over"], b["end_at"] = "lose", now + T["result_time"]
                self.note(f"{p['name']}은(는) 쓰러졌다… (레이드는 기절 페널티 없음)")
            return
        if b.get("story") is not None:
            self._story_check_end(b, now)
            return
        if m["hp"] <= 0:
            if m["special"] == "reboot" and not m["revived"] and self.rng.random() < 0.3:
                m["revived"] = True
                m["hp"] = int(m["maxhp"] * 0.3)
                self.note(f"{m['name']}이(가) 재부팅했다!! (HP 30% 부활)")
                return
            b["over"], b["end_at"] = "win", now + T["result_time"]
            self._battle_rewards(b)
        elif p["hp"] <= 0:
            p["hp"] = 0
            b["over"], b["end_at"] = "lose", now + T["result_time"]
            self.note(f"{p['name']}은(는) 쓰러졌다…")

    def _battle_rewards(self, b):
        m, e = b["mon"], self.expd
        S = self.stats()
        mid = b["mid"]
        gold = int(m["gold"] * self.gold_mult() * self.rng.uniform(0.9, 1.15))
        self.gain_exp(m["exp"])
        if e:
            e["carry"]["gold"] += gold
            e["carry"]["kills"] += 1
        else:
            self.s["gold"] += gold
        drops = []
        for iid, ch in D.MONSTERS[mid]["drops"]:
            if self.rng.random() < ch * (1 + S["luk"] * 0.01):
                (self._carry_add if e else self.add_item)(iid)
                drops.append(item_name(iid))
        self.inc("kills")
        if e:
            self.inc(f"kz_{D.ZONES[e['zone']]['id']}")      # 지역별 처치 수 (스토리 미션)
        self.s["dex"][mid] = self.s["dex"].get(mid, 0) + 1
        rank = m["rank"]
        self.s["traits"]["battle"] += 5 if rank in ("boss", "story") else 2 if rank == "mini" else 1
        self.quest("kill")
        self.note(f"{m['name']} 처치! +{m['exp']}EXP +{gold}G" + (f" [{', '.join(drops)}]" if drops else ""))
        self.pop("WIN!", "mon", "#95D85A", 1.3)
        if rank in ("boss", "story"):
            self.inc("bosses")
            if mid == "dragon429":
                self.unlock("boss429")
            if mid == "friday":
                self.unlock("friday")
        self.mark()

    def _battle_resolve(self, now):
        b = self.battle
        self.battle = None
        if b.get("raid"):
            self._raid_finish(b)
            return
        if b.get("story") is not None:
            self._story_battle_end(b, now)
            return
        e = self.expd
        if b["over"] == "lose":
            if e and b["mon"]["rank"] == "boss" and b["mid"] == D.ZONES[e["zone"]]["boss"]:
                zid = D.ZONES[e["zone"]]["id"]
                self.s["prog"].setdefault("boss_fail", {})[zid] = self.p["lvl"]
                self.note(f"{b['mon']['name']}에게 패배… 레벨을 올려 다시 도전하자 (Lv.{self.p['lvl'] + 1}↑)")
            self.faint("전투에서 기절")
            return
        if not e:
            return
        z = D.ZONES[e["zone"]]
        if b["over"] == "win" and b["mid"] == z["boss"] and e["floor"] >= D.BOSS_FLOOR:
            fl = self.s["prog"]["floor"]
            fl[z["id"]] = D.BOSS_FLOOR
            e["carry"]["floors"] += 1
            if z["id"] not in self.s["prog"]["cleared"]:
                self.s["prog"]["cleared"].append(z["id"])
                self.unlock(f"zone_{z['id']}")
                nxt = D.ZONES[e["zone"] + 1]["name"] if e["zone"] + 1 < len(D.ZONES) else None
                self.flash(f"☼ 지역 정복! {z['name']} ☼" + (f"  다음: {nxt}" if nxt else ""), "#6ABA23", 6)
                self.notify("지역 정복", f"{self.p['name']}이(가) {z['name']}을(를) 정복했어요!", "success")
            self.end_expedition("지역 보스 격파!")
            return
        self._encounter_done(now)

    # ------------------------------------------------------------ 미니게임
    def start_minigame(self, kind):
        p, now = self.p, self.now()
        if self.is_egg():
            return self._nope("알은 아직 못 놀아요")
        if p["sleeping"]:
            return self._nope("자고 있어요… zZ")
        if self.expd or self.battle:
            return self._nope("모험 중이에요")
        if p["sick"] == "burnout":
            return self._nope("…놀 기운이 없어요 (번아웃)")
        if p["energy"] < 8:
            return self._nope("너무 피곤해요…")
        if kind == "dir":
            self.mg = dict(kind="dir", round=0, rounds=5, score=0, phase="wait", choice=None, look=None, t=now)
        elif kind == "whack":
            self.mg = dict(kind="whack", t0=now + 1.5, dur=20.0, cells={}, next=now + 2.0, hits=0, miss=0, esc=0,
                           flash={}, phase="ready")
        elif kind == "type":
            self.mg = dict(kind="type", phrases=self.rng.sample(D.TYPING_PHRASES, 3), idx=0, buf="", t=None,
                           res=[], phase="typing")
        elif kind == "quiz":
            self.mg = dict(kind="quiz", qs=self.rng.sample(range(len(D.QUIZ)), 5), idx=0, score=0, phase="ask",
                           t=now, ans=None, hist=[])
        else:
            return False
        self.mg["last_key"] = now
        self.note(f"미니게임 시작: {dict((k, n) for k, n, _ in D.MINIGAMES)[kind]}")
        return True

    def minigame_key(self, k):
        mg, now = self.mg, self.now()
        if not mg or mg.get("phase") == "result":
            if mg and mg.get("phase") == "result" and k in ("ENTER", "ESC", " "):
                self.mg = None
            return
        mg["last_key"] = now
        if k == "ESC" and mg["kind"] != "type":
            self.mg = None
            self.note("미니게임을 그만뒀다")
            return
        if mg["kind"] == "quiz":
            if mg["phase"] == "ask":
                ans = {"o": True, "1": True, "LEFT": True, "x": False, "2": False, "RIGHT": False}.get(k)
                if ans is None:
                    return
                self._quiz_answer(ans, now)
            elif mg["phase"] == "show" and k in ("ENTER", " "):
                self._quiz_next(now)
            return
        if mg["kind"] == "dir":
            if mg["phase"] != "wait":
                return
            ch = {"LEFT": "L", "a": "L", "RIGHT": "R", "d": "R"}.get(k if len(k) > 1 else k.lower())
            if not ch:
                return
            mg["choice"], mg["look"] = ch, self.rng.choice("LR")
            if ch == mg["look"]:
                mg["score"] += 1
            mg["phase"], mg["t"] = "show", now
        elif mg["kind"] == "whack":
            if mg["phase"] != "play" or k not in "123456789" or len(k) != 1:
                return
            if k in mg["cells"]:
                del mg["cells"][k]
                mg["hits"] += 1
                mg["flash"][k] = (now + 0.35, True)
            else:
                mg["miss"] += 1
                mg["flash"][k] = (now + 0.25, False)
        elif mg["kind"] == "type":
            if k == "ESC":
                self.mg = None
                self.note("타자 연습을 그만뒀다")
                return
            if k == "BS":
                mg["buf"] = mg["buf"][:-1]
            elif k == "ENTER":
                if not mg["buf"]:
                    return
                target = mg["phrases"][mg["idx"]]
                el = max(0.5, now - (mg["t"] or now))
                acc = difflib.SequenceMatcher(None, target, mg["buf"]).ratio()
                cpm = len(mg["buf"]) / el * 60
                mg["res"].append((acc, cpm))
                mg["idx"] += 1
                mg["buf"], mg["t"] = "", None
                if mg["idx"] >= len(mg["phrases"]):
                    self._finish_minigame()
            elif k == "TEXT" or (len(k) == 1 and k >= " "):
                if mg["t"] is None:
                    mg["t"] = now
                if len(mg["buf"]) < 60:
                    mg["buf"] += k

    def _quiz_answer(self, ans, now):
        mg = self.mg
        q = D.QUIZ[mg["qs"][mg["idx"]]]
        ok = ans is not None and ans == q[1]
        mg["ans"], mg["ok"] = ans, ok
        if ok:
            mg["score"] += 1
            self.quest("quiz")
        mg["hist"].append(ok)
        mg["phase"], mg["t"] = "show", now

    def _quiz_next(self, now):
        mg = self.mg
        mg["idx"] += 1
        if mg["idx"] >= len(mg["qs"]):
            self._finish_minigame()
        else:
            mg["phase"], mg["t"], mg["ans"], mg["ok"] = "ask", now, None, None

    def _tick_minigame(self, now):
        mg = self.mg
        if not mg:
            return
        if mg.get("phase") == "result":
            if now >= mg["until"]:
                self.mg = None
            return
        if mg["kind"] in ("dir", "type") and now - mg.get("last_key", now) > 60:
            self.mg = None          # 한참 손을 안 대면 흐지부지 끝 (원정/잠/호출이 막히지 않게)
            self.note("미니게임을 한동안 안 해서 흐지부지 끝났다")
            return
        if mg["kind"] == "quiz":
            if mg["phase"] == "ask" and now - mg["t"] >= D.QUIZ_TIME:
                self._quiz_answer(None, now)          # 시간 초과 = 오답
            elif mg["phase"] == "show" and now - mg["t"] >= 3.2:
                self._quiz_next(now)
            return
        if mg["kind"] == "dir" and mg["phase"] == "show" and now - mg["t"] >= 1.3:
            mg["round"] += 1
            if mg["round"] >= mg["rounds"]:
                self._finish_minigame()
            else:
                mg["phase"], mg["choice"], mg["look"] = "wait", None, None
        elif mg["kind"] == "whack":
            if mg["phase"] == "ready":
                if now >= mg["t0"]:
                    mg["phase"] = "play"
                return
            for c, exp in list(mg["cells"].items()):
                if exp <= now:
                    del mg["cells"][c]
                    mg["esc"] += 1
            for c, (u, _) in list(mg["flash"].items()):
                if u <= now:
                    del mg["flash"][c]
            if now - mg["t0"] >= mg["dur"]:
                self._finish_minigame()
                return
            if now >= mg["next"] and len(mg["cells"]) < 3:
                free = [c for c in "123456789" if c not in mg["cells"]]
                c = self.rng.choice(free)
                life = max(0.6, 1.25 - 0.02 * mg["hits"])
                mg["cells"][c] = now + life
                mg["next"] = now + self.rng.uniform(0.4, 0.85)

    def _finish_minigame(self):
        mg, p, now = self.mg, self.p, self.now()
        kind = mg["kind"]
        if kind == "dir":
            sc = mg["score"]
            win = sc >= 3
            mood, exp, gold = 4 * sc + (6 if win else 0), 4 * sc, 5 * sc
            summary = f"{mg['rounds']}판 중 {sc}번 맞힘!" + (" 승리!" if win else "")
        elif kind == "whack":
            sc = max(0, mg["hits"] - mg["miss"] // 2)
            win = sc >= 10
            mood, exp, gold = min(25, sc + 3), 2 * sc, 3 * sc
            summary = f"버그 {mg['hits']}마리 잡음 · 헛손질 {mg['miss']} · 놓침 {mg['esc']}"
            if mg["hits"] >= 20:
                self.unlock("whack20")
            if sc >= 5 and p["bugs"]:
                p["bugs"] = max(0, p["bugs"] - 1)
                summary += " · 연습하다 방 버그도 1마리 잡았다!"
        elif kind == "quiz":
            sc = mg["score"]
            win = sc >= 4
            mood, exp, gold = 3 * sc + (6 if sc == 5 else 0), 6 * sc, 6 * sc
            summary = f"5문제 중 {sc}개 정답!"
            if sc == 5:
                self.unlock("quiz_perfect")
                cap = 5 + p["lvl"] // 2
                d = self.s["daily"]
                if p.get("int_bonus", 0) < cap and not d.get("quiz_int"):
                    d["quiz_int"] = True          # INT 보너스는 하루 한 번
                    p["int_bonus"] = p.get("int_bonus", 0) + 1
                    summary += " 만점! INT 영구 +1"
        else:
            accs = [a for a, _ in mg["res"]] or [0]
            cpms = [c for _, c in mg["res"]] or [0]
            acc, cpm = sum(accs) / len(accs), sum(cpms) / len(cpms)
            score = acc * min(cpm, 400) / 4
            win = acc >= 0.9
            mood, exp, gold = int(min(20, score / 5)), int(score / 2), int(score / 2)
            summary = f"정확도 {acc * 100:.0f}% · 분당 {cpm:.0f}타"
            if acc >= 0.999 and cpm >= 200:
                self.unlock("perfect_type")
        bonus = 1 + self.pers("play", 0.0)       # 장난꾸러기 +30%
        mood, exp, gold = int(mood * bonus), int(exp * bonus), int(gold * bonus)
        d = self.s["daily"]
        d["games_n"] = d.get("games_n", 0) + 1
        if d["games_n"] > 8:                      # 하루 8판이 넘으면 보상은 ¼ (기분은 그대로)
            exp, gold = exp // 4, gold // 4
        p["mood"] = clamp(p["mood"] + mood, 0, 100)
        p["energy"] = clamp(p["energy"] - 6, 0, 100)
        p["kb"] = max(0.3, p["kb"] - 0.1)
        self.s["gold"] += int(gold)
        self.gain_exp(exp)
        self.s["traits"]["play"] += 1
        self.inc("games")
        self.quest("game")
        self.satisfy("play")
        self.say(("quiz_win" if kind == "quiz" else "play_win") if win else "play_lose")
        mg["phase"], mg["until"] = "result", now + 4.5
        mg["summary"] = f"{summary}  → 기분+{mood} EXP+{exp} +{int(gold)}G"
        self.note(f"미니게임 결과: {mg['summary']}")
        self.mark()

    # ------------------------------------------------------------ opencode 신호
    def signal(self, kind, **d):
        if self.readonly:
            return
        fn = getattr(self, "_on_" + kind, None)
        if fn:
            fn(**d)
            self.mark()

    def _on_tokens(self, tin=0, tout=0):
        tot = int(tin) + int(tout)
        if tot <= 0:
            return
        now = self.now()
        self.inc("tokens", tot)
        td = self.s["tok_day"]
        if td["date"] != day_key(now):
            td["date"], td["n"] = day_key(now), 0
        weight = token_weight(td["n"], tot)       # 경험치로 치는 양 (하루 체감)
        td["n"] += tot
        self.quest("tokens", tot)
        self.s["traits"]["tokens"] += tot
        p, c = self.p, self.s["carry"]
        if p["form"] == "egg":
            self.s["timers"]["egg_bonus"] = self.s["timers"].get("egg_bonus", 0) + tot / 2000
            return
        c["full"] += tot
        add, c["full"] = divmod(c["full"], T["tok_full"])
        if add and p["full"] < T["tok_full_cap"]:
            p["full"] = min(T["tok_full_cap"], p["full"] + add)
        c["exp"] += weight
        e, c["exp"] = divmod(c["exp"], T["tok_exp"])
        if e:
            self.gain_exp(int(e), quiet=True)
        c["int"] += int(tin)
        i, c["int"] = divmod(c["int"], T["tok_int"])
        if i:
            cap = 5 + p["lvl"] // 2
            if p.get("int_bonus", 0) < cap:   # 이벤트로 얻은 영구 INT 는 빼앗지 않는다
                p["int_bonus"] = min(p.get("int_bonus", 0) + i, cap)
        c["mp"] += int(tout)
        mp, c["mp"] = divmod(c["mp"], T["tok_mp"])
        if mp:
            S = self.stats()
            p["mp"] = min(S["maxmp"], p["mp"] + mp)
        if tot >= 200:
            self.fx["munch"] = now + 1.0

    def _on_busy(self, sid="", title="", agent=None):
        now = self.now()
        self.last_activity = now
        first = not self.busy_roots
        self.busy_roots[sid] = now
        if agent:
            self.stance = agent
        if 2 <= local_hour(now) < 5:
            self.unlock("night")
        se = current_season(now)
        if se and se["id"] in ("chuseok", "seollal", "xmas"):
            self.unlock("holiday")
        if self.is_egg():
            return
        if first:
            self.say("busy")
            if self.s["settings"]["auto_exp"] and not self.expd:
                self.start_expedition(auto=True)

    def _on_idle(self, sid="", title="", dur=None, tok=0):
        now = self.now()
        self.last_activity = now
        start = self.busy_roots.pop(sid, None)
        for wid in [w for w, v in self.waits.items() if v.get("sid") == sid]:
            self.waits.pop(wid, None)
        if dur is None:
            dur = (now - start) if start else 0
        self.inc("quests")
        self.quest("resp")
        p = self.p
        gold = int((10 + p["lvl"] * 1.5 + min(dur / 20, 25) + min(tok / 4000, 25)) * self.gold_mult())
        exp = int(8 + p["lvl"] + min(dur / 20, 30))
        self.s["gold"] += gold
        self.gain_exp(exp, quiet=True)
        if not self.is_egg():
            p["mood"] = clamp(p["mood"] + 5, 0, 100)
            self.say("response")
            self.fx["joy"] = now + 2.5
        t = (title or "응답")[:24]
        # 가장 보고 싶은 알림이라 줄 맨 앞으로 (보던 배너는 바로 뒤로 미룬다)
        cur = self.banner
        self.banners.appendleft((fix_josa(f"☼ 응답 도착! {t} ☼ +{gold}G"), "#6ABA23", 6))
        if cur and "응답 도착" not in cur[0]:
            self.banner = None
            if len(self.banners) < (self.banners.maxlen or 99):
                self.banners.insert(1, (cur[0], cur[1], max(1.0, cur[2] - now)))
        self.note(f"응답 도착: {t} (+{gold}G, +{exp}EXP, {int(dur)}초)")
        self.notify("응답 도착", f"{p['name']}: 응답 보상 +{gold}G")
        if self.s["settings"]["bell"]:
            self.ring = True
        if self.expd and self.expd["auto"] and not self.busy_roots:
            self.expd["ret"] = True

    def _on_sub_start(self, sid="", agent="general"):
        a = D.ALLIES.get(agent) or D.ALLIES["_"]
        name = a["name"].format(agent=agent)
        self.allies[sid] = dict(name=name, color=a["color"], art=a["art"], agent=agent, since=self.now())
        self.inc("allies")
        if not self.is_egg():
            self.say("ally", ally=name)
        self.note(f"동료 합류: {name} (서브에이전트 {agent})")

    def _on_gone(self, sid=""):
        """세션이 삭제됐거나 서버가 사라짐 → 보상 없이 정리 (자동 원정은 귀환)"""
        self.busy_roots.pop(sid, None)
        self.allies.pop(sid, None)
        for wid in [w for w, v in self.waits.items() if v.get("sid") == sid]:
            self.waits.pop(wid, None)
        if self.expd and self.expd["auto"] and not self.busy_roots:
            self.expd["ret"] = True

    def _on_sub_end(self, sid="", agent=None):
        self.busy_roots.pop(sid, None)     # 혹시 루트로 잘못 분류됐던 세션이면 여기서 정리
        for wid in [w for w, v in self.waits.items() if v.get("sid") == sid]:
            self.waits.pop(wid, None)
        a = self.allies.pop(sid, None)
        if not a:
            return
        if self.rng.random() < 0.6:
            self.add_item("shard_team")
            self.note(f"{a['name']}이(가) 협업의 파편을 두고 떠났다")
        else:
            g = 10 + self.p["lvl"]
            self.s["gold"] += g
            self.note(f"{a['name']}이(가) {g}G를 두고 떠났다")

    def _on_tool(self, tool="", ok=True):
        self.inc("tools")
        if ok:
            if self.rng.random() < 0.2:
                shard = D.TOOL_SHARDS.get((tool or "").lower()) or self.rng.choice(["shard_scan", "shard_edit"])
                self.add_item(shard)
                self.quest("shard")
                if self.rng.random() < 0.25:
                    self.note(f"'{tool}' 도구가 {item_name(shard)}을(를) 남겼다")
        elif not self.is_egg() and self.rng.random() < 0.4:
            self.p["bugs"] = min(T["bug_max"], self.p["bugs"] + 1)
            self.note(f"도구 '{tool}' 실패… 방에 버그가 생겼다")

    def _on_error(self, msg=""):
        self.inc("errors")
        low = (msg or "").lower()
        rate = "429" in low or "rate" in low or "too many" in low
        self.s["boss_flag"] = "dragon429" if rate else "errdragon"
        self.anxious_until = self.now() + 20
        if not self.is_egg():
            p = self.p
            p["bugs"] = min(T["bug_max"], p["bugs"] + self.rng.randint(1, 2))
            p["mood"] = clamp(p["mood"] - 5, 0, 100)
            self.say("ratelimit" if rate else "error")
        self.flash("에러 감지! 불길한 기운… (다음 원정에 보스 출현)", "#F2F2F3", 4)
        self.note(f"에러: {msg[:60]}")

    def _on_retry(self, msg=""):
        self.anxious_until = self.now() + 30
        if not self.is_egg():
            self.say("retry")

    def _on_agent(self, agent=None):
        if agent:
            self.stance = agent

    def _on_compose(self, chars=0, text="", submitted=True, ctx=None):
        """ctx: compose 창이 미리 고른 반응 종류 (글 원문은 넘겨받지 않음). text 는 예전 버스 줄 호환용"""
        self.last_activity = self.now()
        self.inc("compose")
        self.quest("compose")
        now = self.now()
        self.s["buffs"]["inspired"] = now + 600
        if chars >= 2000:
            self.unlock("longprompt")
        if not self.is_egg():
            self.p["mood"] = clamp(self.p["mood"] + 3, 0, 100)
            self.say(ctx if ctx in D.LINES else reaction_context(text, chars))
        self.note(f"주인님의 지시 수신 ({chars}자) → 영감 버프 (경험치 +10%, 10분)")

    # --- opencode 할 일(todo) = 메인 퀘스트
    def quest_progress(self):
        """(완료, 전체, 지금 하는 일) — 최근 6시간 안에 갱신된 목록만"""
        ql = self.s.get("quest_log")
        if not ql or not ql.get("items") or self.now() - ql.get("updated", 0) > 6 * 3600:
            return None
        items = [it for it in ql["items"] if it["st"] != "cancelled"]
        if not items:
            return None
        done = sum(1 for it in items if it["st"] == "completed")
        cur = next((it["c"] for it in items if it["st"] == "in_progress"), None)
        if cur is None:
            cur = next((it["c"] for it in items if it["st"] != "completed"), "")
        return done, len(items), cur

    @staticmethod
    def _todo_sig(sid, items):
        """할 일 목록의 지문 (같은 목록이 다시 와도 완주 보너스를 두 번 주지 않게)"""
        return f"{sid}|" + "|".join(sorted(it["c"] for it in items if it["st"] != "cancelled"))[:600]

    def _on_todos(self, sid="", title="", todos=None, root=True):
        now = self.now()
        items = [{"c": " ".join(str(t.get("content", "")).split())[:120], "st": str(t.get("status", "pending"))}
                 for t in (todos or []) if isinstance(t, dict)]
        ql = self.s.get("quest_log")
        same = bool(ql) and ql.get("sid") == sid
        if not root and ql and not same and now - ql.get("updated", 0) < 1800 and not ql.get("cleared"):
            return      # 서브에이전트의 할 일은 진행 중인 메인 퀘스트 목록을 덮지 않는다
        if not items:
            if same:
                ql["items"], ql["updated"] = [], now
            return
        active = [it for it in items if it["st"] != "cancelled"]
        all_done = bool(active) and all(it["st"] == "completed" for it in active)
        sig = self._todo_sig(sid, items)
        done_sigs = self.s.setdefault("todo_sigs", [])
        prev_items = ql.get("items", []) if same else []
        # 같은 세션이라도 내용이 전혀 겹치지 않으면 '새 목록' (완주 판정도 새로)
        overlap = bool({it["c"] for it in prev_items} & {it["c"] for it in items})
        fresh_list = not same or (prev_items and not overlap)
        prev = {it["c"]: it["st"] for it in prev_items} if (same and overlap) else {}
        self.last_activity = now
        if fresh_list:
            # 이미 다 끝난 목록을 (다른 세션으로 갔다가 돌아오며) 다시 받으면 기록으로만 둔다
            ql = dict(sid=sid, title=(title or "")[:40], items=items, updated=now, started=now,
                      cleared=all_done, sig=sig)
            self.s["quest_log"] = ql
            if all_done:
                if sig not in done_sigs:
                    done_sigs.append(sig)
                    del done_sigs[:-40]
                return
            if not self.is_egg():
                self.say("todo_new", n=len(items))
            self.note(f"새 할 일 목록 ({len(items)}개)" + (f": {title[:30]}" if title else ""))
        else:
            ql["items"], ql["updated"], ql["sig"] = items, now, sig
            if title:
                ql["title"] = title[:40]
        done_now = [it for it in items if it["st"] == "completed" and prev.get(it["c"]) not in (None, "completed")]
        d, p = self.s["daily"], self.p
        got = 0
        for it in done_now:
            if d.get("todo_n", 0) >= T["todo_daily_cap"]:
                break
            d["todo_n"] = d.get("todo_n", 0) + 1
            exp = max(3, exp_to_next(p["lvl"]) // 250)
            gold = int((3 + p["lvl"] // 2) * self.gold_mult())
            self.s["gold"] += gold
            self.gain_exp(exp, quiet=True)
            self.inc("todos_done")
            self.quest("todo")
            got += 1
            self.note(f"할 일 완료 ⊠ {it['c'][:40]} (+{gold}G +{exp}EXP)")
        if got:
            self.pop(f"⊠x{got}" if got > 1 else "⊠", "pet", "#6ABA23", 1.4)
            if not self.is_egg():
                self.say("todo_done")
                self.fx["joy"] = now + 1.5
        if len(active) >= 2 and all_done and not ql.get("cleared"):
            ql["cleared"] = True
            if sig in done_sigs:
                return          # 이 목록은 이미 완주 보너스를 받았다
            done_sigs.append(sig)
            del done_sigs[:-40]
            n = len(active)
            d["lists_n"] = d.get("lists_n", 0) + 1
            big = d["lists_n"] <= 10           # 목록 완주 보너스는 하루 10번까지
            gold = int((10 + 4 * n) * self.gold_mult()) if big else 0
            exp = exp_to_next(p["lvl"]) // 40 if big else 0
            self.s["gold"] += gold
            self.gain_exp(exp, quiet=True)
            self.inc("todo_lists")
            if big and self.rng.random() < 0.3:
                self.add_item(self.rng.choice(["tokenjelly", "hotfixpatch", "cacheflush", "cake"]))
            self.flash(f"☼ 할 일 {n}개 전부 완료! 목록 완주 보너스 +{gold}G ☼", "#6ABA23", 6)
            self.note(f"할 일 목록 완주: {ql.get('title') or '할 일 목록'} ({n}개, +{gold}G +{exp}EXP)")
            self.notify("할 일 완주", f"{p['name']}: 할 일 {n}개 완료! +{gold}G")
            if not self.is_egg():
                self.say("todo_all")

    # --- opencode가 사용자 응답(허락/질문)을 기다림
    def _on_wait(self, id="", sid="", wkind="perm", label=""):
        now = self.now()
        if not id or id in self.waits:
            return
        self.waits[id] = dict(sid=sid, kind=wkind, label=label or "", since=now)
        self.last_activity = now
        if not self.is_egg():
            self.say("perm" if wkind == "perm" else "ask", dur=10)
        head = "‼ opencode가 허락을 기다려요" if wkind == "perm" else "? opencode가 질문했어요"
        self.flash(f"{head}: {label[:40]}", "#F2F2F3", 6)
        self.note(f"{head}: {label[:60]}")
        if self.s["settings"].get("perm_bell", True):
            self.ring = True

    def _on_wait_done(self, id="", reply=""):
        w = self.waits.pop(id, None)
        if not w:
            return
        took = self.now() - w["since"]
        if w["kind"] == "perm":
            if took <= 15:
                self.unlock("fastperm")
            if took <= 60:
                self.inc("perm_fast")
            if took <= 60 and not self.is_egg():
                self.p["mood"] = clamp(self.p["mood"] + 3, 0, 100)
                self._care_good(0.5)
                self.say("perm_fast")
        self.note(f"응답 완료{f' ({reply})' if reply else ''} · {int(took)}초")

    def _on_compacted(self, sid=""):
        self.inc("compactions")
        if self.is_egg():
            return
        p = self.p
        p["full"] = clamp(p["full"] + 4, 0, 120)
        p["mood"] = clamp(p["mood"] + 2, 0, 100)
        self.fx["burp"] = self.now() + 2.2
        self.say("compacted")
        self.note("컨텍스트 압축! 꺼억~ 대화를 소화했다 (포만 +4)")

    def _on_abort(self, sid=""):
        self.inc("aborts")
        if not self.is_egg():
            self.say("abort")
        self.note("작업 중단 (사용자 중단은 에러가 아니에요)")

    def _on_command(self, name=""):
        self.inc("commands")
        self.gain_exp(3, quiet=True)
        if not self.is_egg() and name:
            self.say("command", cmd=name)
        self.note(f"슬래시 명령 /{name} 실행 (+3EXP)")

    # ------------------------------------------------------------ 메인 스토리 (주간 챕터)
    def story(self):
        st = self.s.get("story")
        return st if isinstance(st, dict) else None

    def _sanitize_story(self):
        """옛/깨진 저장의 스토리 값 정리 (없는 챕터 번호, 이상한 타입)"""
        st = self.s.get("story")
        if st is None:
            return
        if not isinstance(st, dict):
            self.s["story"] = None
            return
        fresh = new_story(self.s.get("created") or time.time())
        kinds = {"start": str, "phase": str, "base": dict, "mdone": list, "seen": list, "cleared": list, "log": list,
                 "bonus": bool}
        for k, v in fresh.items():
            cur = st.get(k)
            if k == "pending":
                if cur is not None and (isinstance(cur, bool) or not isinstance(cur, int)):
                    st[k] = None
            elif k in kinds:
                if not isinstance(cur, kinds[k]):
                    st[k] = v
            elif isinstance(cur, bool) or not isinstance(cur, (int, float)):
                st[k] = v
        for k in ("fast", "rel", "ch", "fails", "fail_lvl", "bonus_n"):
            st[k] = int(st[k])
        n = len(D.CHAPTERS)
        st["fast"] = int(max(1, min(n, st["fast"])))
        st["ch"] = int(max(0, min(n - 1, st["ch"])))
        st["rel"] = int(max(st["fast"], min(n, st["rel"])))
        if st["phase"] not in ("play", "boss", "wait", "end"):
            st["phase"] = "play"
        try:
            datetime.date.fromisoformat(st["start"])
        except (TypeError, ValueError):
            st["start"] = day_key(time.time())
        st["mdone"] = [i for i in st["mdone"] if isinstance(i, int)]
        ids = {c["id"] for c in D.CHAPTERS}
        st["cleared"] = [c for c in st["cleared"] if c in ids]
        st["log"] = [x for x in st["log"] if isinstance(x, list) and len(x) == 2][-30:]
        if st["pending"] is not None and not (isinstance(st["pending"], int) and 0 <= st["pending"] < n):
            st["pending"] = None

    def _story_init(self, now, fast=None):
        self.s["story"] = new_story(now, fast)
        self._story_begin(0, now, quiet=True)
        return self.s["story"]

    def _story_log(self, text):
        st = self.story()
        if st is not None:
            st["log"].append([self.now(), fix_josa(text)])
            st["log"] = st["log"][-30:]

    def _story_days(self, now=None):
        st = self.story()
        if not st:
            return 0
        try:
            d0 = datetime.date.fromisoformat(st["start"])
        except (TypeError, ValueError):
            return 0
        return max(0, (datetime.date.fromtimestamp(now or self.now()) - d0).days)

    def story_released_n(self, now=None):
        """지금까지 공개된 챕터 수 = 들어갈 수 있는 지역 수 (한 번 열린 건 시계가 뒤로 가도 닫히지 않는다)"""
        st = self.story()
        if not st:
            return D.STORY["fast"]
        n = min(len(D.CHAPTERS), st["fast"] + self._story_days(now) // D.STORY["every"])
        if n > st.get("rel", 0):
            st["rel"] = n
        return st["rel"]

    def story_release_date(self, i):
        """챕터 i(0부터)가 공개되는 날 (datetime.date). 처음부터 열려 있는 챕터는 None"""
        st = self.story()
        if not st or i < st["fast"]:
            return None
        try:
            d0 = datetime.date.fromisoformat(st["start"])
        except (TypeError, ValueError):
            return None
        return d0 + datetime.timedelta(days=D.STORY["every"] * (i - st["fast"] + 1))

    def _story_begin(self, i, now, quiet=False):
        st = self.story()
        c = D.CHAPTERS[i]
        st.update(ch=i, phase="play", since=now, mdone=[], bonus=False, fails=0, fail_lvl=0,
                  base=dict(self.s["stats"]))
        self._story_log(f"CH{i + 1:02d} 「{c['title']}」 시작")
        if not quiet:
            self.flash(f"◈ 새 챕터! CH{i + 1:02d} 「{c['title']}」 ◈ [7] 스토리", "#6ABA23", 7)
            self.note(f"스토리 CH{i + 1:02d} 「{c['title']}」이(가) 열렸다 — {c['teaser']}")
            self.notify("새 챕터", f"CH{i + 1:02d} {c['title']}", "success")
            if not self.is_egg():
                self.say("story_new", dur=9)
        self.mark()

    def _mission_eval(self, m, base):
        """미션 하나 → (문구, 진행, 목표)"""
        k, n = m["k"], m.get("n") or 0
        zone = next((z for z in D.ZONES if z["id"] == m.get("z")), None)
        zname = zone["name"] if zone else ""
        if k == "floor":
            return f"{zname} B{n}F 도달", min(n, self.s["prog"]["floor"].get(m["z"], 0)), n
        if k == "clear":
            return f"{zname} 보스 격파", 1 if m["z"] in self.s["prog"]["cleared"] else 0, 1
        if k == "kills":
            key = f"kz_{m['z']}"
            return f"{zname} 몬스터 {n}마리 처치", max(0, self.stat(key) - base.get(key, 0)), n
        if k == "care":
            return f"돌봄 점수 {n} 이상", int(self.p["care"]), n
        if k == "enh":
            best = max([g.get("plus", 0) for g in self.s["equip"].values() if g] + [0])
            return f"장착 장비 +{n} 강화", best, n
        s = m.get("s") or "quests"
        text = D.STORY_STAT_TEXT.get(s, s + " {n}").format(n=fmt_num(n) if n >= 10000 else n)
        return text, max(0, self.stat(s) - base.get(s, 0)), n

    def story_missions(self, i=None):
        """챕터 i 의 미션 목록: [dict(text, prog, target, done, opt)]. 지난 챕터는 전부 완료, 다음 챕터는 0"""
        st = self.story()
        if not st:
            return []
        cur = st["ch"]
        i = cur if i is None else i
        c = D.CHAPTERS[i]
        past = c["id"] in st["cleared"]
        out = []
        for idx, m in enumerate(c["missions"]):
            text, prog, target = self._mission_eval(m, st["base"] if i == cur else {})
            if past or (i == cur and idx in st["mdone"]):
                done, prog = True, max(prog, target) if m["k"] not in ("care", "enh") else prog
            elif i != cur:
                done, prog = False, 0
            else:
                done = prog >= target
            out.append(dict(text=text, prog=prog, target=target, done=done, opt=bool(m.get("opt"))))
        return out

    def story_brief(self):
        """다른 창/목장용 한 줄 요약"""
        st = self.story()
        if not st:
            return None
        c = D.CHAPTERS[st["ch"]]
        ms = self.story_missions()
        req = [m for m in ms if not m["opt"]]
        return dict(ch=st["ch"] + 1, title=c["title"], phase=st["phase"], done=sum(m["done"] for m in req), total=len(req),
                    shards=len(st["cleared"]))

    def _tick_story(self, now):
        st = self.story()
        if st is None:
            if self.s.get("hatched"):
                st = self._story_init(now)      # 부화했는데 스토리가 없는 저장 (옛 버전 등)
            else:
                return
        if now - getattr(self, "_story_t", 0.0) < 1.0 and now >= getattr(self, "_story_t", 0.0):
            return
        self._story_t = now
        rel = self.story_released_n(now)
        i = st["ch"]
        if st["phase"] == "wait":
            if i + 1 < len(D.CHAPTERS) and i + 1 < rel:
                self._story_begin(i + 1, now)
            return
        if st["phase"] not in ("play", "boss"):
            return
        c = D.CHAPTERS[i]
        ms = self.story_missions()
        for idx, m in enumerate(ms):
            if m["done"] and idx not in st["mdone"]:
                st["mdone"].append(idx)
                if m["opt"]:
                    self._story_bonus(i)
                else:
                    self.note(f"스토리 미션 완료: {m['text']}")
                    self._story_log(f"미션 완료 · {m['text']}")
                    self.flash(f"√ 스토리 미션 완료: {m['text']}", "#95D85A", 4)
                self.mark()
        if st["phase"] == "play" and all(m["done"] for m in ms if not m["opt"]):
            st["phase"] = "boss"
            name = D.MONSTERS[c["boss"]["mid"]]["name"]
            self.flash(f"◆ 챕터 보스 신호! {name} ◆ [7] 스토리 → [B] 도전", "#F2F2F3", 7)
            self.note(f"CH{i + 1:02d} 미션을 모두 끝냈다! 챕터 보스 {name}의 신호가 잡혔다")
            self._story_log(f"보스 신호 포착 · {name}")
            self.notify("챕터 보스", f"{self.p['name']}: {name}에게 도전할 수 있어요", "warning")
            if not self.is_egg():
                self.say("story_boss", dur=9)
            self.mark()

    def _story_bonus(self, i):
        st, c = self.story(), D.CHAPTERS[i]
        if st["bonus"]:
            return
        st["bonus"] = True
        st["bonus_n"] = st.get("bonus_n", 0) + 1
        r = c.get("bonus") or {}
        gold = int(r.get("gold", 0) * self.gold_mult())
        self.s["gold"] += gold
        loot = []
        for iid, n in list((r.get("items") or {}).items()) + list((r.get("mats") or {}).items()):
            self.add_item(iid, n)
            loot.append(f"{item_name(iid)} x{n}")
        for iid in r.get("gear") or []:
            self.add_item(iid)
            loot.append(item_name(iid))
        self.flash(f"☼ 보너스 미션 달성! +{gold}G" + (f" · {', '.join(loot)}" if loot else ""), "#6ABA23", 6)
        self.note(f"CH{i + 1:02d} 보너스 미션 달성 (+{gold}G{', ' + ', '.join(loot) if loot else ''})")
        self._story_log("보너스 미션 달성")
        if st["bonus_n"] >= 6:
            self.unlock("story_bonus")

    def story_seen(self, i, part):
        st = self.story()
        return bool(st) and f"{D.CHAPTERS[i]['id']}:{part}" in st["seen"]

    def story_mark_seen(self, i, part):
        """대화를 다 봤다 (intro / boss / outro)"""
        st = self.story()
        if not st:
            return
        key = f"{D.CHAPTERS[i]['id']}:{part}"
        if key not in st["seen"]:
            st["seen"].append(key)
            self.mark()
        if part == "outro" and st.get("pending") == i:
            st["pending"] = None

    def can_story_boss(self):
        st, p = self.story(), self.p
        if self.is_egg() or not st:
            return False, "알이 깨면 스토리가 시작돼요"
        if st["phase"] == "end":
            return False, "시즌 1 완결! 다음 시즌을 기다려 주세요"
        if st["phase"] == "wait":
            return False, "다음 챕터가 열리길 기다리는 중이에요"
        if st["phase"] != "boss":
            return False, "필수 미션을 먼저 끝내야 보스 신호가 잡혀요"
        if self.expd:
            return False, "원정 중이에요 (돌아오면 도전) · [2] 모험에서 R 귀환"
        if self.battle:
            return False, "이미 싸우는 중이에요"
        if self.mg:
            return False, "미니게임 중이에요"
        if p["sleeping"]:
            return False, "자고 있어요… zZ"
        if p["sick"] in ("cold", "burnout"):
            return False, "아파서 못 가요… [M]"
        need = D.STORY["boss_energy"] + 5
        if p["energy"] < need:
            return False, f"체력이 부족해요 (체력 {need} 필요)"
        if p["full"] < 10:
            return False, "배고파서 못 가요… [F]"
        S = self.stats()
        if p["hp"] < S["maxhp"] * 0.5:
            return False, "HP가 부족해요 (50% 필요) — 집에서 쉬거나 커피 한 잔"
        return True, ""

    def start_story_boss(self):
        ok, why = self.can_story_boss()
        if not ok:
            return self._nope(why)
        st, now, p = self.story(), self.now(), self.p
        i = st["ch"]
        bd = D.CHAPTERS[i]["boss"]
        p["energy"] = clamp(p["energy"] - D.STORY["boss_energy"], 0, 100)
        p["full"] = clamp(p["full"] - D.STORY["boss_full"], 0, 120)
        ms = monster_stats(bd["mid"], bd["lvl"], "story")
        self.battle = dict(mid=bd["mid"], mon=ms, pst={}, round=0, next=now + 1.5, over=None, end_at=0.0, last_dmg=0,
                           cd={}, pair=0, wait_since=now, last_round_at=0.0, defend=False, enrage=0,
                           story=i, phase2=bd.get("phase2"), p2_done=False, mid_said=False)
        self.s["seen"][bd["mid"]] = self.s["seen"].get(bd["mid"], 0) + 1
        if self.s["call"]:
            self.s["call"] = None
        self.inc("story_fights")
        self.flash(f"◆ 챕터 보스! vs {ms['name']} (LV{ms['level']})", "#F2F2F3", 4)
        self.note(f"CH{i + 1:02d} 챕터 보스전: {ms['name']} (Lv.{ms['level']}) — 지면 HP만 줄어요 (기절 페널티 없음)")
        self.mark()
        return True

    def story_retreat(self):
        b = self.battle
        if not (b and b.get("story") is not None) or b.get("over"):
            return False
        b["over"], b["end_at"] = "retreat", self.now() + 0.8
        self.note("챕터 보스전에서 물러났다 (페널티 없음)")
        return True

    def _story_check_end(self, b, now):
        p, m = self.p, b["mon"]
        bd = D.CHAPTERS[b["story"]]["boss"]
        if m["hp"] <= 0:
            if b.get("phase2") and not b.get("p2_done"):
                b["p2_done"] = True
                m["hp"] = int(m["maxhp"] * b["phase2"])
                m["st"] = {}
                self.fx["phase2"] = now + 2.5
                for spk, t in bd.get("phase2_lines") or []:
                    who = m["name"] if spk == "boss" else p["name"] if spk == "pet" else D.NPCS.get(spk, {}).get("name", "")
                    self.note(f"{who}: {t.format(name=p['name'])}")
                first = (bd.get("phase2_lines") or [("boss", "…")])[0][1].format(name=p["name"])
                self.flash(f"!! {m['name']}: {first} !!", "#F2F2F3", 4)
                return
            if m["special"] == "reboot" and not m["revived"] and self.rng.random() < 0.3:
                m["revived"] = True
                m["hp"] = int(m["maxhp"] * 0.3)
                self.note(f"{m['name']}이(가) 재부팅했다!! (HP 30% 부활)")
                return
            m["hp"] = 0
            b["over"], b["end_at"] = "win", now + T["result_time"] + 0.6
            self._battle_rewards(b)
        elif p["hp"] <= 0:
            p["hp"] = 0
            b["over"], b["end_at"] = "lose", now + T["result_time"]
            self.note(f"{p['name']}은(는) 쓰러졌다… (챕터 보스전은 기절 페널티 없음)")
        elif not b.get("mid_said") and m["hp"] <= m["maxhp"] * 0.5:
            b["mid_said"] = True
            line = bd.get("mid_line")
            if line:
                self.note(f"{m['name']}: {line}")
                self.flash(f"{m['name']}: {line}", "#D4D6D8", 3.5)

    def _story_battle_end(self, b, now):
        st, i, p = self.story(), b["story"], self.p
        if b["over"] == "win" and st and st["ch"] == i and st["phase"] == "boss":
            self._story_clear(i, now)
            return
        S = self.stats()
        if b["over"] == "lose":
            p["hp"] = max(1, int(S["maxhp"] * 0.1))
            p["mood"] = clamp(p["mood"] - 5, 0, 100)
            if st:
                st["fails"] = st.get("fails", 0) + 1
                st["fail_lvl"] = p["lvl"]
            msg = f"{b['mon']['name']}에게 패배… 레벨을 올리거나 장비를 강화해서 다시 도전!"
        else:
            msg = f"{b['mon']['name']}과(와)의 싸움에서 물러났다"
        m = b["mon"]
        self.note(msg)
        self._story_log(msg)
        self.last_summary = (dict(story=True, win=False, ch=i, boss=m["name"], lvl=m["level"], reason=msg,
                                  left=max(0, int(m["hp"])), maxhp=m["maxhp"], fainted=b["over"] == "lose"), now + 9)
        self.mark()

    def _story_clear(self, i, now):
        st, c, p = self.story(), D.CHAPTERS[i], self.p
        r = c.get("reward") or {}
        gold = int(r.get("gold", 0) * self.gold_mult())
        self.s["gold"] += gold
        loot = []
        for iid, n in list((r.get("items") or {}).items()) + list((r.get("mats") or {}).items()):
            self.add_item(iid, n)
            loot.append(f"{item_name(iid)} x{n}")
        for iid in list(r.get("gear") or []) + list(r.get("decos") or []):
            self.add_item(iid)
            loot.append(item_name(iid))
        exp = int(exp_to_next(p["lvl"]) * r.get("exp", 0))
        self.gain_exp(exp)
        if c["id"] not in st["cleared"]:
            st["cleared"].append(c["id"])
        st["pending"] = i
        if r.get("ach"):
            self.unlock(r["ach"])
        n_sh = len(st["cleared"])
        self.flash(f"☼ CH{i + 1:02d} CLEAR! 커밋 조각 #{i + 1} 확보 ({n_sh}/{len(D.CHAPTERS)}) ☼ +{gold}G", "#6ABA23", 7)
        self.note(f"CH{i + 1:02d} 「{c['title']}」 클리어! 커밋 조각 #{i + 1} ({c['hash']}) · +{gold}G +{exp}EXP"
                  + (f" · {', '.join(loot)}" if loot else ""))
        self.notify("챕터 클리어", f"{p['name']}: CH{i + 1:02d} {c['title']} — 커밋 조각 #{i + 1}", "success")
        self._story_log(f"CH{i + 1:02d} 클리어 · 커밋 조각 #{i + 1} {c['hash']}")
        if not self.is_egg():
            self.say("story_clear", dur=8)
        self.last_summary = (dict(story=True, win=True, ch=i, title=c["title"], boss=D.MONSTERS[c["boss"]["mid"]]["name"],
                                  gold=gold, exp=exp, loot=loot, hash=c["hash"], shards=n_sh), now + 9)
        if i + 1 >= len(D.CHAPTERS):
            st["phase"] = "end"
            self._story_log(f"시즌 {D.STORY['season']} 「{D.STORY['title']}」 완결")
        elif i + 1 < self.story_released_n(now):
            self._story_begin(i + 1, now)
        else:
            st["phase"] = "wait"
        self.mark()

    # ------------------------------------------------------------ 세대: 은퇴 → 명예의 전당 → 새 알
    def can_retire(self):
        p = self.p
        f = D.FORMS[p["form"]]
        if self.expd or self.battle or self.mg:
            return False, "모험/놀이 중에는 은퇴식을 할 수 없어요"
        if f["stage"] >= 5:
            return True, ""
        rr = D.RETIRE_RULE
        if f["stage"] < rr["stage"]:
            return False, "성체가 되면 은퇴식을 할 수 있어요"
        if p["lvl"] < rr["lvl"]:
            return False, f"Lv.{rr['lvl']}부터 은퇴식을 할 수 있어요 (지금 Lv.{p['lvl']})"
        if self.age() < rr["days"] * 86400:
            return False, f"부화 {rr['days']}일 뒤부터 은퇴식을 할 수 있어요 (지금 {fmt_age(self.age())})"
        return True, ""

    def retire(self, new_name=None):
        ok, why = self.can_retire()
        if not ok:
            return self._nope(why)
        p, now, fam = self.p, self.now(), self.s["family"]
        base, st = fam.get("base") or {}, self.s["stats"]

        def mine(k):
            return max(0, st.get(k, 0) - base.get(k, 0))
        rec = dict(gen=fam.get("gen", 1), name=p["name"], form=p["form"], lvl=p["lvl"], title=p.get("title"),
                   personality=p.get("personality"), days=round(self.age() / 86400, 1), care=int(p["care"]),
                   discipline=int(p.get("discipline", 50)), kills=mine("kills"), bosses=mine("bosses"),
                   tokens=mine("tokens"), quests=mine("quests"), todos=mine("todos_done"), retired=now,
                   zones=len(self.s["prog"]["cleared"]), epitaph=D.EPITAPHS.get(p["form"], D.EPITAPHS["_"]))
        fam.setdefault("hall", []).append(rec)
        fam["hall"] = fam["hall"][-30:]
        fam["gen"] = fam.get("gen", 1) + 1
        # 끼던 장비는 가방으로 (새 아이가 자라면 다시 쓸 수 있게)
        for slot in ("weapon", "armor", "acc"):
            g = self.s["equip"].get(slot)
            if g and g.get("id") not in ("kb_laptop", "hood_holed"):
                self.s["inv"]["gear"].append(g)
        self.s["equip"] = {"weapon": {"id": "kb_laptop", "plus": 0}, "armor": {"id": "hood_holed", "plus": 0}, "acc": None}
        old_form, old_name = p["form"], p["name"]
        self.s["pet"] = new_pet(new_name or heir_name(old_name, fam["gen"]))
        self.s["hatched"] = None
        self.s["created"] = now
        self.s["traits"] = {k: 0.0 for k in self.s["traits"]}
        self.s["prog"] = {"floor": {}, "cleared": [], "boss_fail": {}}
        self.s["carry"] = {"full": 0, "exp": 0, "int": 0, "mp": 0}
        self.s["call"] = None
        self.s["boss_flag"] = None
        self.s["legacy_exp"] = 0
        self.s["anniv_w"] = 0
        self.s["timers"]["egg_bonus"] = 30.0 * min(fam["gen"] - 1, 4)   # 가문이 클수록 알이 조금 빨리 깬다
        self.stance, self.allies = None, {}
        self.unlock("retire")
        if fam["gen"] >= 3:
            self.unlock("gen3")
        self.fx["retire"] = (old_form, old_name, now + 6.0)
        self.flash(f"◈ {old_name} 은퇴! 명예의 전당에 올랐어요 ◈ {fam['gen']}대 알 도착", "#6ABA23", 7)
        self.note(f"은퇴식: {old_name} ({D.FORMS[old_form]['name']} Lv.{rec['lvl']}) → 명예의 전당. "
                  f"{fam['gen']}대 {self.p['name']}의 알이 도착했다")
        self.notify("은퇴식", f"{old_name}이(가) 명예의 전당에 올랐어요")
        self.welcome = [f"{old_name}은(는) 명예의 전당에서 지켜볼 거예요.",
                        f"「{rec['epitaph']}」",
                        f"가문 보너스: 경험치 +{int(self.family_bonus('exp') * 100)}% · 골드 +{int(self.family_bonus('gold') * 100)}%",
                        "방·가방·골드·업적·도감은 그대로! 새 아이는 새 성격으로 태어나요."]
        self.mark()
        self.save(force=True)
        return True

    # ------------------------------------------------------------ 주간 레이드 (모든 인스턴스 펫 공동)
    def _raid_state(self):
        r = self.s["raid"]
        now = self.now()
        wk = week_key(now)
        # 날짜가 '앞으로' 갈 때만 초기화 (시계를 되돌려 출격 횟수/기록을 리셋하는 걸 막음)
        if not r.get("week") or wk > r["week"]:
            r.update(week=wk, dmg=0, best=0, claimed=False, cleared=False)
        td = day_key(now)
        tries = r.get("tries") if isinstance(r.get("tries"), dict) else {}
        if not tries.get("date") or td > tries["date"]:
            r["tries"] = {"date": td, "n": 0}
        return r

    def raid_info(self, fresh=False):
        r = self._raid_state()
        now = self.now()
        me = dict(scope=safe_scope(self.scope), name=self.p["name"], lvl=self.p["lvl"], dmg=r["dmg"], cleared=r.get("cleared", False))
        if fresh:
            raid_board(r["week"], now, fresh=True)
        info = raid_summary(r["week"], now, extra=me)
        info["mine"] = r["dmg"]
        info["tries_left"] = max(0, D.RAID["per_day"] - r["tries"]["n"])
        info["rank"] = next((i + 1 for i, row in enumerate(info["rows"]) if row["scope"] == me["scope"]), None)
        info["claimed"] = r.get("claimed", False)
        return info

    def can_raid(self):
        p = self.p
        if self.is_egg():
            return False, "알은 레이드에 못 가요"
        if self.expd:
            return False, "원정 중이에요 (돌아오면 출격)"
        if self.battle:
            return False, "이미 싸우는 중이에요"
        if self.mg:
            return False, "미니게임 중이에요"
        if p["sleeping"]:
            return False, "자고 있어요… zZ"
        if p["sick"] in ("cold", "burnout"):
            return False, "아파서 못 가요… [M]"
        if p["energy"] < D.RAID["energy"] + 3:
            return False, f"체력이 부족해요 (체력 {D.RAID['energy'] + 3} 필요)"
        if p["full"] < 10:
            return False, "배고파서 못 가요… [F]"
        info = self.raid_info()
        if info["cleared"]:
            return False, "이번 주 레이드 보스는 이미 쓰러졌어요! (월요일에 새 보스)"
        if info["tries_left"] <= 0:
            return False, f"오늘 레이드 출격은 {D.RAID['per_day']}번까지예요 (내일 다시)"
        return True, ""

    def start_raid(self):
        ok, why = self.can_raid()
        if not ok:
            return self._nope(why)
        now, p = self.now(), self.p
        info = self.raid_info(fresh=True)
        if info["cleared"]:
            return self._nope("방금 다른 펫이 레이드 보스를 쓰러뜨렸어요! (보상은 자동으로 받아요)")
        r = self._raid_state()
        r["tries"]["n"] += 1
        p["energy"] = clamp(p["energy"] - D.RAID["energy"], 0, 100)
        p["full"] = clamp(p["full"] - D.RAID["full"], 0, 120)
        mid = info["boss"]
        ms = monster_stats(mid, p["lvl"] + 2, "raid")
        ms["maxhp"] = int(info["hp"])
        ms["hp"] = max(1, int(info["remaining"]))
        S = self.stats()
        p["hp"] = max(p["hp"], S["maxhp"] * 0.8)       # 공대 대기실에서 정비하고 출발
        self.battle = dict(mid=mid, mon=ms, pst={}, round=0, next=now + 1.5, over=None, end_at=0.0, last_dmg=0,
                           cd={}, pair=0, wait_since=now, last_round_at=0.0, defend=False, enrage=0,
                           raid=True, rounds_max=D.RAID["rounds"], start_hp=ms["hp"], week=r["week"])
        self.s["seen"][mid] = self.s["seen"].get(mid, 0) + 1
        if self.s["call"]:
            self.s["call"] = None
        self.inc("raids")
        self.quest("raid")
        self.say("raid")
        self.flash(f"† 주간 레이드 출격! vs {ms['name']} (남은 체력 {fmt_num(ms['hp'])})", "#6ABA23", 4)
        self.note(f"주간 레이드 출격: {ms['name']} · 오늘 남은 출격 {info['tries_left'] - 1}번")
        self.mark()
        return True

    def raid_retreat(self):
        b = self.battle
        if not (b and b.get("raid")) or b.get("over"):
            return False
        b["over"], b["end_at"] = "retreat", self.now() + 0.8
        self.note("레이드에서 먼저 빠졌다 (준 피해는 기록돼요)")
        return True

    def _raid_finish(self, b):
        p, now = self.p, self.now()
        dealt = int(max(0, b.get("start_hp", 0) - max(0, b["mon"]["hp"])))
        r = self._raid_state()
        same_week = b.get("week", r["week"]) == r["week"]
        if same_week:
            r["dmg"] = r.get("dmg", 0) + dealt
            r["best"] = max(r.get("best", 0), dealt)
            if b["over"] == "win":
                r["cleared"] = True
        else:
            self.note("레이드 도중 주가 바뀌었다! 지난주 보스라 기록은 남지 않고 골드/경험치만 받았다")
        gold = int(dealt / 8 * self.gold_mult())
        exp = int(dealt / 16)
        self.s["gold"] += gold
        self.gain_exp(exp, quiet=True)
        S = self.stats()
        if b["over"] == "lose":
            p["hp"] = max(1, int(S["maxhp"] * 0.1))
        self.s["traits"]["battle"] += 2
        self._write_raid_file()
        info = self.raid_info(fresh=True)
        pct = 100 * info["dealt"] / max(1, info["hp"])
        head = {"win": "☼ 레이드 보스 격파!! (막타)", "lose": "쓰러졌지만 피해는 남았다", "timeup": "제한 시간 종료",
                "retreat": "먼저 빠짐"}.get(b["over"], "레이드 종료")
        self.last_summary = (dict(raid=True, boss=b["mon"]["name"], reason=head, dealt=dealt, gold=gold, exp=exp,
                                  pct=pct, rank=info.get("rank"), total=info["dealt"], hp=info["hp"],
                                  fainted=b["over"] == "lose", cleared=info["cleared"]), now + 9)
        self.flash(f"레이드 결과: 피해 {fmt_num(dealt)} · +{gold}G · 공동 진행 {pct:.0f}%", "#6ABA23" if b["over"] == "win" else "#95D85A", 5)
        self.note(f"레이드 종료 ({head}): 피해 {fmt_num(dealt)}, +{gold}G +{exp}EXP · 이번 주 누적 {fmt_num(r['dmg'])}")
        self.last_raid_check = 0.0
        self._raid_claim_check(now)
        self.mark()

    def _write_raid_file(self):
        if not self.persist:
            return
        r = self.s["raid"]
        write_json(raid_path(self.scope), dict(week=r["week"], scope=safe_scope(self.scope), name=self.p["name"],
                                              lvl=self.p["lvl"], dmg=r["dmg"], cleared=r.get("cleared", False),
                                              ts=self.now()))

    def _raid_claim_check(self, now=None):
        r = self._raid_state()
        if r.get("claimed") or r.get("dmg", 0) <= 0:
            return
        info = self.raid_info(fresh=True)
        if not info["cleared"]:
            return
        r["claimed"] = True
        if not r.get("cleared"):
            r["cleared"] = True
            self._write_raid_file()
        gold = int(300 * self.gold_mult())
        self.s["gold"] += gold
        self.add_item("boss_core", 2)
        self.add_item("legacy_scroll", 1)
        self.unlock("raid_clear")
        mvp = info.get("rank") == 1 and len(info["rows"]) >= 2
        if mvp:
            self.add_item("duck_charm")
            self.unlock("raid_mvp")
        self.flash(f"☼ 주간 레이드 격파 보상! +{gold}G · 보스 코어 x2 · 레거시 두루마리" + (" · MVP 러버덕!" if mvp else ""),
                   "#6ABA23", 7)
        self.note(f"주간 레이드 보상 수령 (+{gold}G, 보스 코어 2, 두루마리 1{', MVP 부적' if mvp else ''})")
        self.notify("주간 레이드", f"{self.p['name']}: 레이드 보스 격파 보상!")
        self.mark()


# ============================================================== 다른 창용 유틸
def reaction_context(text, chars=None):
    t = (text or "").lower()
    chars = len(text or "") if chars is None else chars
    if any(k in t for k in ("급해", "asap", "urgent", "빨리", "긴급")):
        return "compose_urgent"
    if any(k in t for k in ("배포", "deploy", "release", "릴리스")):
        return "compose_deploy"
    if any(k in t for k in ("버그", "bug", "fix", "고쳐", "에러", "error")):
        return "compose_bug"
    if any(k in t for k in ("테스트", "test", "pytest", "jest")):
        return "compose_test"
    if any(k in t for k in ("리팩터", "리팩토", "refactor", "정리")):
        return "compose_refactor"
    if any(k in t for k in ("고마", "감사", "thanks", "thank", "굿", "좋아")):
        return "compose_thanks"
    if chars >= 800:
        return "compose_long"
    return "compose"


def pet_summary(scope, now=None):
    """status/overview/compose 창에서 쓰는 가벼운 요약 (게임 창이 안 떠 있으면 저장 파일로 추정)"""
    now = now or time.time()
    live = read_json(live_path(scope))
    if isinstance(live, dict) and now - live.get("ts", 0) < 12:
        live["stale"] = False
        return live
    s = read_json(pet_path(scope))
    if not isinstance(s, dict) or "pet" not in s:
        return None
    p = s["pet"]
    f = D.FORMS.get(p.get("form"), D.FORMS["egg"])
    hrs = max(0.0, now - s.get("last_seen", now)) / 3600
    fac = T["offline_factor"]
    full = max(5.0, p.get("full", 50) - T["full_decay"] * min(hrs, 18) * fac)
    mood = max(15.0, p.get("mood", 50) - T["mood_decay"] * min(hrs, 18) * fac)
    face = "._." if full < 15 else "T_T" if mood < 25 else "u_u" if hrs > 0.5 else "o_o"
    return dict(ts=s.get("last_seen", 0), name=p.get("name", DEFAULT_NAME), form=p.get("form"), form_name=f["name"],
                stage=f["stage"], color=f["color"], lvl=p.get("lvl", 1), face=face if p.get("form") != "egg" else "egg",
                full=int(full), mood=int(mood), energy=int(p.get("energy", 50)), health=int(p.get("health", 100)),
                bugs=p.get("bugs", 0), sick=p.get("sick"), sleeping=False, where="away", zone=None, floor=None,
                battle=None, call=None, gold=s.get("gold", 0), title=p.get("title"), speech="",
                tok_today=s.get("tok_day", {}).get("n", 0) if s.get("tok_day", {}).get("date") == day_key(now) else 0,
                kills=s.get("stats", {}).get("kills", 0), gen=(s.get("family") or {}).get("gen", 1), stale=True)


def compose_reaction(scope, text):
    sm = pet_summary(scope)
    if not sm or sm.get("form") == "egg":
        return ""
    from t1_term import rgb, RST
    line = random.choice(D.LINES[reaction_context(text)])
    return f"{rgb(sm.get('color') or '#6ABA23')}{sm['name']}{RST}: {line}"


def pet_badge(scope, width=60):
    """한 줄 펫 상태 배지 (ANSI 포함). 펫이 없으면 빈 문자열"""
    sm = pet_summary(scope)
    if not sm:
        return ""
    from t1_term import rgb, RST, B, P3, chip
    lime, g1, g4, wh = rgb(P3["lime"]), rgb(P3["gray1"]), rgb(P3["gray4"]), rgb(P3["white"])
    col = rgb(sm.get("color") or P3["lime"])
    blink = int(time.time() * 2) % 2
    if sm.get("form") == "egg":
        return f"{col}({sm['name']}의 알){RST} {g1}부화 대기 중… 응답이 오면 깨어나요{RST}"
    parts = [f"{col}{B}{sm['name']}{RST} {chip(sm['form_name'], 'gray4', 'navy1', False)} {g1}LV{RST}{lime}{B}{sm['lvl']}{RST} "
             f"{col}({sm['face']}){RST}"]

    def mini(v):
        c = P3["lime"] if v >= 50 else P3["lime1"] if v >= 25 else P3["white"]
        return f"{rgb(c)}{B}{v}{RST}"
    parts.append(f"{g1}포만{RST} {mini(sm['full'])} {g1}기분{RST} {mini(sm['mood'])} {g1}체력{RST} {mini(sm['energy'])}")
    if sm.get("wait"):
        tag = "PERM" if sm.get("wait_kind") == "perm" else "ASK"
        parts.append((chip(tag, "black", "lime") if blink else chip(tag, "lime", "navy2"))
                     + f" {wh}{'허락 대기' if tag == 'PERM' else '질문 대기'}{RST}")
    q = sm.get("quest")
    if q and q.get("total"):
        parts.append(f"{g1}QUEST{RST} {lime}{q['done']}/{q['total']}{RST}")
    if sm.get("where") == "exp":
        parts.append(f"{chip('EXP', 'black', 'navy4')} {g4}{sm.get('zone')} B{sm.get('floor')}F{RST}"
                     + (f" {g1}vs {sm['battle']}{RST}" if sm.get("battle") else ""))
    elif sm.get("where") == "raid":
        parts.append(f"{chip('RAID', 'black', 'white')}" + (f" {g1}vs {sm['battle']}{RST}" if sm.get("battle") else ""))
    elif sm.get("sleeping"):
        parts.append(chip("zZ", "navy4", "navy1"))
    if sm.get("bugs", 0) >= 3:
        parts.append(f"{wh}{B}ж{sm['bugs']}{RST}")
    if sm.get("sick"):
        sick = {"cold": "감기", "overfed": "배탈", "burnout": "번아웃"}.get(sm["sick"], "아픔")
        parts.append(chip(sick, "black", "white"))
    if sm.get("call"):
        parts.append((chip("CALL", "black", "lime") if blink else chip("CALL", "lime", "navy2")) + f" {g4}{sm['call']}{RST}")
    if sm.get("stale"):
        parts.append(f"{g1}(펫 창 꺼짐){RST}")
    return "  ".join(parts)
