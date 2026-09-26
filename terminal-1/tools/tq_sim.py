"""
tools/tq_sim.py - TOKEN QUEST 시뮬레이터 (개발용, 배포하지 않음)

평일 10시간 opencode 를 쓰는 사람을 흉내 내어 며칠을 돌리고, 메인 스토리 진행을 숫자로 뽑는다.
밸런스(경험치 · 보스 · 챕터 공개)를 고칠 때마다 돌려서 전후를 비교한다.

  python tools/tq_sim.py                          # 세 프로필 × 84일, 표로
  python tools/tq_sim.py --profile normal --days 70 --seed 3
  python tools/tq_sim.py --json > before.json     # 비교용
  python tools/tq_sim.py --watch never            # 보스 예고에 한 번도 대응하지 않는 사람 (자동 대응만)

프로필 = 하루 토큰 · 응답 수 · 펫을 들여다보는 간격(분). 주말은 창을 끈다 (챕터 공개는 달력대로 흐른다).
게임 틱은 실제 엔진(t1_pet.PetGame)을 그대로 쓴다 — 가짜 시계만 넣는다.
"""
import argparse
import datetime
import json
import os
import random
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="tq-sim-")   # 진짜 저장 폴더는 건드리지 않는다

import t1_pet as P  # noqa: E402
import t1_pet_data as D  # noqa: E402

PROFILES = {
    # tokens: 하루 토큰 · resp: 하루 응답 수 · watch: 펫을 들여다보는 간격(분) · engage: 들여다볼 때 손으로 원정 보낼 확률
    # sub: 응답마다 서브에이전트가 붙을 확률
    "light": dict(tokens=250_000, resp=25, watch=20, engage=0.25, sub=0.05),
    "normal": dict(tokens=2_000_000, resp=60, watch=10, engage=0.4, sub=0.15),
    "heavy": dict(tokens=25_000_000, resp=120, watch=6, engage=0.5, sub=0.35),
}
TOOLS = [("read", 5), ("grep", 3), ("glob", 1), ("edit", 4), ("write", 1), ("bash", 4), ("todowrite", 1), ("webfetch", 0.3)]
DAY_START, DAY_HOURS = 9, 10


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def wchoice(rng, pairs):
    tot = sum(w for _, w in pairs)
    r = rng.random() * tot
    for v, w in pairs:
        r -= w
        if r <= 0:
            return v
    return pairs[-1][0]


class Player:
    """펫 주인 흉내: watch 분마다 들여다보고 돌봄 · 장비 · 스토리 보스 · 레이드를 챙긴다"""

    def __init__(self, g, clk, prof, rng, react=None):
        self.g, self.clk, self.prof, self.rng = g, clk, prof, rng
        self.react = react              # 보스 예고에 대응할 확률 (None = 엔진 기본값)
        self.next_look = 0.0
        self.games_today = 0
        self.last_boss_try = 0.0
        self.last_boss_lvl = 0
        self.raided_today = 0
        self.ch_log = {}                # 챕터 번호 → 기록
        self.attempts = []              # (챕터, 레벨, 결과)
        self._seen_tele = None

    # --- 보스 예고: 화면을 보고 있으면 (watch 간격이 짧을수록 자주) 맞게 받아친다
    def watch_battle(self):
        g = self.g
        tl = g.battle.get("tele") if g.battle else None
        if not tl or tl is self._seen_tele:
            return
        self._seen_tele = tl
        if self.prof["watch"] is None or not self.prof.get("answer", True):
            return
        look_p = min(0.9, 6.0 / self.prof["watch"])     # 6분마다 보는 사람 90%, 20분마다 보는 사람 30%
        if self.rng.random() < look_p:
            g.input_seen()
            ans = tl["ans"] if self.rng.random() < 0.9 else self.rng.choice([k for k, _ in tl["opts"]])
            g.gim_answer(ans)

    # --- 하루 시작
    def new_day(self):
        self.games_today = 0
        self.raided_today = 0

    def look(self, now):
        if self.prof["watch"] is None:
            return
        if now < self.next_look:
            return
        self.next_look = now + self.prof["watch"] * 60 * self.rng.uniform(0.6, 1.4)
        g = self.g
        g.input_seen()
        if g.is_egg():
            g.pat()
            return
        self.care()
        if g.battle or g.mg:
            return
        self.gear()
        self.missions()
        self.story()
        if not g.expd and not g.battle:
            self.play()
            self.raid()
            self.push()

    # --- 돌봄
    def _food(self):
        g = self.g
        foods = [iid for iid, n in g.items_of(("food",)) if n > 0]
        if not foods:
            for iid in ("chicken", "kimbap", "samgak"):
                if D.ITEMS[iid]["lvl"] <= g.p["lvl"] and g.s["gold"] >= g.price(iid) * 2:
                    g.buy(iid)
                    return iid
            return None
        return max(foods, key=lambda i: D.ITEMS[i]["eff"].get("full", 0))

    def _med(self, sick):
        g = self.g
        for iid, n in g.items_of(("med",)):
            if n > 0 and sick in D.ITEMS[iid]["eff"].get("cure", []):
                return iid
        for iid, it in D.ITEMS.items():
            if it["shop"] and it["kind"] == "med" and sick in it["eff"].get("cure", []) and g.s["gold"] >= g.price(iid):
                if g.buy(iid):
                    return iid
        return None

    def care(self):
        g, p = self.g, self.g.p
        if p["sleeping"]:
            return
        call = g.s.get("call")
        kind = call["kind"] if call else None
        if kind == "tantrum":
            g.scold()
        elif kind == "pat":
            g.pat()
        elif kind == "play" and not (g.expd or g.battle or g.mg):
            self.play(force=True)
        if p["sick"] and not g.battle:
            iid = self._med(p["sick"])
            if iid:
                g.use_item(iid)
        if p["full"] < 45 and not g.battle:
            iid = self._food()
            if iid:
                g.use_item(iid)
        if p["bugs"] >= 3:
            g.clean()
        if kind == "sleepy" or (p["energy"] < 18 and not (g.expd or g.battle or g.mg)):
            g.toggle_sleep()

    # --- 장비: 가방의 더 좋은 장비를 끼고, 돈이 넉넉하면 상점 장비를 사고, 안전 구간(+5)까지 강화
    @staticmethod
    def _score(iid, plus=0):
        e = D.ITEMS[iid]["eff"]
        base = e.get("atk", 0) * 1.3 + e.get("df", 0) * 1.1 + e.get("int", 0) + e.get("spd", 0) + e.get("hp", 0) / 6
        return base * (1 + 0.12 * plus) + plus * 2

    def gear(self):
        g = self.g
        inv, eq = g.s["inv"], g.s["equip"]
        for slot in ("weapon", "armor", "acc"):
            cur = eq.get(slot)
            cur_sc = self._score(cur["id"], cur.get("plus", 0)) if cur else -1
            best, best_sc = None, cur_sc
            for idx, gg in enumerate(inv["gear"]):
                it = D.ITEMS[gg["id"]]
                if it["kind"] == slot and it["lvl"] <= g.p["lvl"]:
                    sc = self._score(gg["id"], gg.get("plus", 0))
                    if sc > best_sc + 0.5:
                        best, best_sc = idx, sc
            if best is not None:
                g.equip(best)
                continue
            shop = [(iid, it) for iid, it in D.ITEMS.items()
                    if it["kind"] == slot and it["shop"] and it["price"] > 0 and it["lvl"] <= g.p["lvl"]]
            shop.sort(key=lambda x: -self._score(x[0]))
            for iid, it in shop[:1]:
                if self._score(iid) > cur_sc + 2 and g.s["gold"] >= g.price(iid) * 1.6:
                    if g.buy(iid):
                        idx = len(inv["gear"]) - 1
                        g.equip(idx)
        for slot in ("weapon", "armor"):
            gg = eq.get(slot)
            if not gg or gg.get("plus", 0) >= 5:
                continue
            info = g.enhance_info(gg)
            if info and info["have"] >= info["need"] and g.s["gold"] >= info["gold"] * 2.5:
                g.enhance("equip", slot)

    # --- 스토리 미션 중 손으로 채울 수 있는 것 (화면에 보이니 사람도 이렇게 한다)
    def missions(self):
        g = self.g
        st = g.story()
        if not st or st["phase"] != "play":
            return
        c = D.CHAPTERS[st["ch"]]
        for m, ms in zip(c["missions"], g.story_missions()):
            if ms["done"]:
                continue
            s = m.get("s")
            if m["k"] == "stat" and s == "pats":
                g.pat()
            elif m["k"] == "stat" and s == "meals" and g.p["full"] < 85:
                iid = self._food()
                if iid:
                    g.use_item(iid)
            elif m["k"] == "stat" and s == "games" and self.games_today < 5:
                self.play(force=True)
            elif m["k"] == "stat" and s == "crafts":
                for r in g.recipe_list():
                    if r["ok"] and r["r"]["gold"] <= g.s["gold"] // 3:
                        g.craft(r["id"])
                        break
            elif m["k"] == "stat" and s == "raids" and not ms["opt"]:
                self.raided_today = 0
                self.raid(force=True)
            elif m["k"] == "enh":
                self.enhance_to(m["n"])

    def enhance_to(self, n):
        g = self.g
        gg = g.s["equip"].get("weapon")
        if not gg or gg.get("plus", 0) >= n:
            return
        info = g.enhance_info(gg)
        if info and info["have"] >= info["need"] and g.s["gold"] >= info["gold"] * 1.5:
            g.enhance("equip", "weapon")

    # --- 스토리 보스
    def story(self):
        g = self.g
        st = g.story()
        if not st:
            return
        for part in ("intro", "boss", "outro"):
            if 0 <= st["ch"] < len(D.CHAPTERS) and not g.story_seen(st["ch"], part):
                if part == "intro" or (part == "outro" and D.CHAPTERS[st["ch"]]["id"] in st["cleared"]):
                    g.story_mark_seen(st["ch"], part)
        if st.get("pending") is not None:
            g.story_mark_seen(st["pending"], "outro")
        si = g.side_info()
        if si and si["phase"] in ("new", "done"):
            g.side_seen()                           # 사이드 에피소드: 도입 → 목표 → 마무리
        elif si and si["ep"]["goal"]["s"] == "pats":
            g.pat()
        if st["phase"] != "boss" or g.expd:
            return
        now = g.now()
        if self.last_boss_try and now - self.last_boss_try < 2 * 3600 and g.p["lvl"] <= self.last_boss_lvl:
            return      # 졌으면 레벨을 올리거나 두 시간 뒤에 다시
        ok, _ = g.can_story_boss()
        if not ok:
            if g.p["hp"] < g.stats()["maxhp"] * 0.5 and not g.p["sleeping"]:
                for iid in ("coffee", "hotfixpatch"):
                    if g.s["inv"]["items"].get(iid):
                        g.use_item(iid) if D.ITEMS[iid]["kind"] != "battle" else None
                        break
            return
        self.last_boss_try, self.last_boss_lvl = now, g.p["lvl"]
        i = st["ch"]
        if g.start_story_boss():
            self.attempts.append(dict(ch=i + 1, lvl=g.p["lvl"], day=None, result=None))

    # --- 미니게임 · 레이드 · 손으로 보내는 원정
    def play(self, force=False):
        g = self.g
        if g.mg or g.expd or g.battle or g.p["sleeping"]:
            return
        if not force and (self.games_today >= 2 or self.rng.random() > 0.35):
            return
        kind = self.rng.choice(["dir", "quiz", "whack"])
        if g.start_minigame(kind):
            self.games_today += 1
            mg = g.mg
            if kind == "dir":
                mg["score"] = self.rng.choice([2, 3, 3, 4, 5])
            elif kind == "quiz":
                mg["score"] = self.rng.choice([2, 3, 4, 4, 5])
            else:
                mg["hits"], mg["miss"] = self.rng.randint(8, 18), self.rng.randint(0, 4)
            g._finish_minigame()
            g.mg = None

    def raid(self, force=False):
        g = self.g
        if self.raided_today >= 1 or (not force and self.rng.random() > 0.3):
            return
        ok, _ = g.can_raid()
        if ok and g.start_raid():
            self.raided_today += 1

    def push(self):
        g = self.g
        if g.busy_roots or self.rng.random() > self.prof["engage"]:
            return
        if g.p["energy"] >= 55 and g.p["full"] >= 35:
            ok, _ = g.can_depart()
            if ok:
                g.start_expedition(self.target_zone(), auto=False)

    def target_zone(self):
        """지금 챕터 미션이 그 지역에서 채워져야 하면 그 지역, 아니면 엔진이 고르는 곳"""
        g = self.g
        st = g.story()
        if st and st["phase"] == "play":
            c = D.CHAPTERS[st["ch"]]
            for m, ms in zip(c["missions"], g.story_missions()):
                if not ms["done"] and m["k"] in ("floor", "clear", "kills") and m.get("z"):
                    idx = next(i for i, z in enumerate(D.ZONES) if z["id"] == m["z"])
                    info = g.zones_info()[idx]
                    if info["unlocked"]:
                        return idx
        return None


class Work:
    """opencode 흉내: 하루치 응답 일정을 만들고, 시각에 맞춰 신호를 쏜다"""

    def __init__(self, g, prof, rng):
        self.g, self.prof, self.rng = g, prof, rng
        self.plan = []
        self.todo = None
        self.n = 0

    def schedule(self, day0):
        """day0 = 그날 09:00. [(시작, 끝)] 응답 창"""
        R = self.prof["resp"]
        span = DAY_HOURS * 3600
        busy = [self.rng.uniform(60, 360) for _ in range(R)]
        gap_total = max(60.0 * R, span - sum(busy))
        gaps = [self.rng.random() + 0.2 for _ in range(R)]
        k = gap_total / sum(gaps)
        t, out = day0 + 120, []
        for b, gp in zip(busy, gaps):
            t += gp * k * 0.95
            out.append([t, t + b])
            t += b
        self.plan = [w for w in out if w[1] < day0 + span]
        self.per_resp = self.prof["tokens"] / max(1, len(self.plan))

    def step(self, now, dt):
        g, rng = self.g, self.rng
        for w in self.plan:
            s, e = w[0], w[1]
            if len(w) == 2 and now >= s:
                self.n += 1
                sid = f"s{self.n}"
                w.append(sid)
                if rng.random() < 0.2:
                    g.signal("compose", chars=rng.randint(20, 400), ctx=None)
                g.signal("busy", sid=sid, title="작업", agent=rng.choice(["build", "build", "build", "plan"]))
                if rng.random() < self.prof["sub"]:
                    g.signal("sub_start", sid=sid + "x", agent=rng.choice(["explore", "general"]))
                    w.append("sub")
                if self.todo is None and rng.random() < 0.3:
                    self.todo = dict(sid=sid, items=[f"할 일 {self.n}-{j}" for j in range(rng.randint(3, 6))], done=0)
                    self._todos()
                if rng.random() < 0.15:
                    w.append(("wait", s + rng.uniform(5, max(6, (e - s) / 2))))
            if len(w) >= 3 and s <= now < e and "_" not in w:
                # 응답 창 안: 토큰 · 도구
                frac = dt / max(1.0, e - s)
                tok = self.per_resp * frac
                if tok >= 1:
                    g.signal("tokens", tin=int(tok * 0.85), tout=int(tok * 0.15))
                if rng.random() < dt / 25:
                    g.signal("tool", tool=wchoice(rng, TOOLS), ok=rng.random() < 0.95)
                for x in w[3:]:
                    if isinstance(x, tuple) and x[0] == "wait" and now >= x[1] and ("w", x[1]) not in w:
                        w.append(("w", x[1]))
                        g.signal("wait", id=f"{w[2]}w", sid=w[2], wkind="perm", label="bash")
                        watching = self.prof["watch"] is not None and rng.random() < 0.6
                        w.append(("reply", now + (rng.uniform(10, 50) if watching else rng.uniform(90, 300))))
                    if isinstance(x, tuple) and x[0] == "reply" and now >= x[1] and ("r", x[1]) not in w:
                        w.append(("r", x[1]))
                        g.signal("wait_done", id=f"{w[2]}w", reply="once")
            if len(w) >= 3 and now >= e and "_" not in w:
                w.append("_")
                if rng.random() < 0.03:
                    g.signal("error", msg=rng.choice(["rate limit 429", "Internal error", "timeout"]))
                g.signal("idle", sid=w[2], title="작업")
                if "sub" in w:
                    g.signal("sub_end", sid=w[2] + "x")
                if self.todo:
                    self.todo["done"] += rng.choice([0, 1, 1, 2])
                    self._todos()
                    if self.todo["done"] >= len(self.todo["items"]):
                        self.todo = None

    def _todos(self):
        t = self.todo
        todos = [dict(content=c, status="completed" if j < t["done"] else "pending") for j, c in enumerate(t["items"])]
        self.g.signal("todos", sid=t["sid"], title="목록", todos=todos)

    def busy_now(self, now):
        return any(len(w) >= 3 and w[0] <= now < w[1] for w in self.plan)


def simulate(profile, days=84, seed=1, start=None, react=None, verbose=False, snap=None):
    prof = dict(PROFILES[profile])
    if react == "never":
        prof["answer"] = False          # 돌봄 · 보스 도전은 하지만 예고에는 한 번도 대응하지 않는 사람
    rng = random.Random(seed * 7919 + len(profile))
    start = start or datetime.datetime(2026, 9, 7, DAY_START)      # 월요일
    clk = Clock(start.timestamp())
    g = P.PetGame(f"sim-{profile}-{seed}", "토큰이", clock=clk, seed=seed, persist=False)
    pl, wk = Player(g, clk, prof, rng, react), Work(g, prof, rng)
    daily = []
    ch_done = {}
    snapped = set()
    if snap:
        os.makedirs(snap, exist_ok=True)
    t0 = time.time()
    for d in range(days):
        day = start + datetime.timedelta(days=d)
        if day.weekday() >= 5:
            continue
        day0 = day.timestamp()
        if clk.t < day0:
            clk.t = day0
            g._offline(day0)
            g.last_tick = day0
        g.input_seen()
        pl.new_day()
        wk.schedule(day0)
        end = day0 + DAY_HOURS * 3600
        while clk.t < end or (g.battle and clk.t < end + 1800):
            active = g.expd or g.battle or g.mg or wk.busy_now(clk.t)
            dt = 1.1 if active else 5.0
            clk.t += dt
            if clk.t < end:
                wk.step(clk.t, dt)
            pl.look(clk.t)
            g.tick()
            pl.watch_battle()
            st = g.story()
            if snap and st and st["phase"] == "boss" and st["ch"] not in snapped:
                snapped.add(st["ch"])       # 보스 신호가 잡힌 순간의 저장 → duel 로 보스전만 반복
                with open(os.path.join(snap, f"{profile}-ch{st['ch'] + 1:02d}.json"), "w", encoding="utf-8") as f:
                    json.dump(g.s, f, ensure_ascii=False)
            if st:
                for c in st["cleared"]:
                    if c not in ch_done:
                        ch_done[c] = dict(day=d + 1, lvl=g.p["lvl"])
            if pl.attempts and pl.attempts[-1]["result"] is None and not g.battle:
                a = pl.attempts[-1]
                a["day"] = d + 1
                cid = D.CHAPTERS[a["ch"] - 1]["id"]
                a["result"] = "win" if cid in (st or {}).get("cleared", []) else "lose"
        if g.expd:
            g.end_expedition("퇴근")
        if g.battle and not g.battle.get("over"):
            g.battle = None
        st = g.story() or {}
        daily.append(dict(day=d + 1, lvl=g.p["lvl"], gold=g.s["gold"], ch=st.get("ch", 0) + 1, phase=st.get("phase"),
                          rel=st.get("rel", 0), form=g.p["form"], cleared=len(st.get("cleared", [])),
                          side=len(st.get("side_done", []))))
        if verbose:
            x = daily[-1]
            print(f"  D{x['day']:>3} Lv{x['lvl']:>3} CH{x['ch']:02d} {x['phase']:<4} rel{x['rel']:>2} "
                  f"{x['form']:<10} {x['gold']:>7}G", file=sys.stderr)
        if st.get("phase") == "end":
            break
    return dict(profile=profile, seed=seed, days=len(daily), last_day=daily[-1]["day"] if daily else 0,
                chapters=_chapters(daily, ch_done, pl.attempts), attempts=pl.attempts, final=daily[-1] if daily else {},
                daily=daily, secs=round(time.time() - t0, 1))


def duel_one(state, seed, policy="auto", fails=0, acc=0.9):
    """저장 하나(보스 신호가 잡힌 순간)에서 챕터 보스전 한 판. policy: auto(예고를 안 봄) / watch(보고 고름, acc 확률로 정답)
    반환: (이겼나, 라운드 수, 예고 수, 맞힌 수)"""
    import copy
    rng = random.Random(seed)
    clk = Clock(state.get("last_seen") or time.time())
    g = P.PetGame(f"duel-{seed}", "토큰이", clock=clk, seed=seed, persist=False)
    g.s = copy.deepcopy(state)
    g._sanitize(quiet=True)         # 예전 엔진이 만든 저장도 지금 엔진 기본값으로
    g.s["call"] = None
    p = g.p
    p.update(sleeping=False, sick=None, energy=100.0, full=90.0)
    S = g.stats()
    p["hp"], p["mp"] = S["maxhp"], S["maxmp"]
    st = g.story()
    st["phase"], st["fails"] = "boss", fails
    g.last_input = clk.t - (0 if policy == "watch" else 3600)
    if not g.start_story_boss():
        return None
    b = g.battle
    seen, t_start = None, clk.t
    while g.battle and clk.t - t_start < 3600:
        clk.t += 0.5
        if policy == "watch":
            g.last_input = clk.t
        g.tick()
        tl = g.battle.get("tele") if g.battle else None
        if tl and tl is not seen:
            seen = tl
            if policy == "watch":
                ans = tl["ans"] if rng.random() < acc else rng.choice([k for k, _ in tl["opts"] if k != tl["ans"]] or [tl["ans"]])
                g.gim_answer(ans)
    gim = b.get("gim") or {}
    return b.get("over") == "win", b["round"], gim.get("n", 0), gim.get("ok", 0)


def duel(snapdir, n=60, fails=0, profiles=None):
    """--snap 으로 모은 저장마다 auto / watch 로 n판씩 → 챕터별 승률"""
    rows = []
    for fn in sorted(os.listdir(snapdir)):
        if not fn.endswith(".json"):
            continue
        prof, ch = fn[:-5].split("-ch")
        if profiles and prof not in profiles:
            continue
        with open(os.path.join(snapdir, fn), encoding="utf-8") as f:
            state = json.load(f)
        row = dict(profile=prof, ch=int(ch), lvl=state["pet"]["lvl"], form=state["pet"]["form"])
        for pol in ("auto", "watch"):
            res = [r for r in (duel_one(state, s, pol, fails) for s in range(n)) if r]
            row[pol] = round(sum(r[0] for r in res) / max(1, len(res)), 2)
            row[pol + "_rounds"] = round(sum(r[1] for r in res) / max(1, len(res)), 1)
        rows.append(row)
    return rows


def _chapters(daily, ch_done, attempts):
    out = []
    for i, c in enumerate(D.CHAPTERS):
        began = next((x["day"] for x in daily if x["ch"] >= i + 1), None)
        boss_ready = next((x["day"] for x in daily if x["ch"] > i + 1 or (x["ch"] == i + 1 and x["phase"] in ("boss", "wait", "end"))), None)
        done = ch_done.get(c["id"])
        tries = [a for a in attempts if a["ch"] == i + 1]
        out.append(dict(ch=i + 1, boss_lvl=c["boss"]["lvl"], began=began, ready=boss_ready,
                        cleared=done["day"] if done else None, clear_lvl=done["lvl"] if done else None,
                        tries=len(tries), first_lvl=tries[0]["lvl"] if tries else None,
                        losses=sum(1 for a in tries if a["result"] == "lose")))
    # 대기일: 클리어한 날부터 다음 챕터가 시작된 날까지
    for a, b in zip(out, out[1:]):
        a["wait"] = (b["began"] - a["cleared"]) if (a["cleared"] and b["began"]) else None
    out[-1]["wait"] = None
    return out


def table(res):
    lines = [f"■ {res['profile']} (seed {res['seed']}) · {res['last_day']}일째까지 · {res['secs']}초",
             " CH  보스Lv  시작  보스준비  클리어  클리어Lv  첫도전Lv  도전/패배  대기일"]
    for c in res["chapters"]:
        def f(v, w=5):
            return f"{'—' if v is None else v:>{w}}"
        lines.append(f" {c['ch']:02d}  {c['boss_lvl']:>5}  {f(c['began'])}  {f(c['ready'], 8)}  {f(c['cleared'], 6)}"
                     f"  {f(c['clear_lvl'], 8)}  {f(c['first_lvl'], 8)}  {c['tries']:>4}/{c['losses']:<4}  {f(c.get('wait'), 6)}")
    fin = res["final"]
    side_days = [next((x["day"] for x in res.get("daily", []) if x.get("side", 0) >= k), None) for k in range(1, 7)]
    lines.append(f" 마지막: Lv{fin.get('lvl')} · {fin.get('form')} · {fin.get('gold')}G · 조각 {fin.get('cleared')}/12"
                 f" · 사이드 {fin.get('side', 0)}/6 (끝낸 날 {', '.join(str(x) for x in side_days if x)})")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="TOKEN QUEST 시뮬레이터")
    ap.add_argument("--profile", default="all", choices=["all"] + list(PROFILES))
    ap.add_argument("--days", type=int, default=84)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--watch", default=None, choices=[None, "never"], help="never: 보스 예고에 한 번도 대응하지 않는 사람")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--snap", default=None, help="보스 신호가 잡힌 순간의 저장을 이 폴더에 모은다 (duel 용)")
    ap.add_argument("--duel", default=None, help="이 폴더의 저장으로 챕터 보스전만 반복해서 승률을 잰다")
    ap.add_argument("--n", type=int, default=60, help="duel: 저장 하나당 판 수")
    ap.add_argument("--fails", type=int, default=0, help="duel: 이미 진 횟수 (회고 보정 확인용)")
    a = ap.parse_args(argv)
    profs = list(PROFILES) if a.profile == "all" else [a.profile]
    if a.duel:
        rows = duel(a.duel, a.n, a.fails, None if a.profile == "all" else profs)
        if a.json:
            print(json.dumps(rows, ensure_ascii=False, indent=1))
            return
        print(f" 프로필  CH  Lv  형태          자동승률(라운드)  지켜봄승률(라운드)   · 패배 {a.fails}번 회고")
        for r in rows:
            print(f" {r['profile']:<6} {r['ch']:02d} {r['lvl']:>3}  {r['form']:<12}  {r['auto']:>5.0%} ({r['auto_rounds']:>4})"
                  f"     {r['watch']:>5.0%} ({r['watch_rounds']:>4})")
        return
    out = []
    for pr in profs:
        res = simulate(pr, a.days, a.seed, react=a.watch, verbose=a.verbose, snap=a.snap)
        out.append(res)
        if not a.json:
            print(table(res))
            print()
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
