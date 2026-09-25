"""
ocmux_pet_ui.py - TOKEN QUEST (TQ–1): 토큰펫 화면 (터미널 캔버스 렌더링 + 키 입력 처리)

화면(모드): 1 홈 / 2 모험 / 3 가방 / 4 상점 / 5 공방 / 6 도감 / 7 스토리  — 한 화면 = 한 모드
오버레이: 먹이·약·놀이 선택, 스킬·아이템 메뉴, 이벤트 선택지, 미니게임, 진화 연출, 귀환 결과, 환영 인사
디자인 규칙은 ocmux_term.py 맨 위 참고:
  - 색 = 조작: 포만①파랑 F · 기분②초록 P · 체력③흰색 Z · 건강④회색 M (페이더 색 = 키 색)
  - `?` = 가이드: 화면의 번호 구역마다 번호표 + 범례 (그리는 쪽이 self._anchor() 로 위치를 알려 준다)
  - 방금 누른 키는 아래 키캡에 불이 들어오고, 새 기록이 생기면 LOG 구역 LED 가 켜진다
"""
import collections
import datetime
import math
import random
import re
import time

import ocmux_pet as P
import ocmux_pet_data as D
from ocmux_term import (RST, B, rgb, bg, vlen, clip, pad, wrap, cw, norm_key, is_hangul, P3,
                        chip, keycap, module, meter, segbar, knob, spinner, seg_lines, seg_width, sect,
                        Canvas, guide_draw, boot_draw, title_end, ENC, enc_dot, page_dots, cells, sysline)

TABS = [("home", "홈"), ("adv", "모험"), ("bag", "가방"), ("shop", "상점"), ("forge", "공방"), ("dex", "도감"),
        ("story", "스토리")]
TAB_KEYS = "".join(str(i + 1) for i in range(len(TABS)))      # "1234567"
SCENE_CPS = 38.0          # 대화 타자 속도 (글자/초)
PART_NAMES = {"intro": "PROLOGUE", "boss": "BOSS", "outro": "EPILOGUE", "replay": "REPLAY"}
SUBTABS = {
    "bag": ["장비", "소모품", "재료", "꾸미기"],
    "shop": ["구매", "판매"],
    "forge": ["강화", "제작"],
    "dex": ["프로필", "퀘스트", "일기", "몬스터", "진화", "전당", "업적", "설정"],
}
DEX_PROFILE, DEX_QUEST, DEX_DIARY, DEX_MON, DEX_FORMS, DEX_HALL, DEX_ACH, DEX_SET = range(8)
# 팔레트: 네이비(구조·트랙) / 라임(강조·켜짐) / 그레이(글자). 위험·경고는 가장 밝은 흰색 블록
BLACK = rgb("#000000")
LIME, LIME1, LIME3, LIME4 = rgb(P3["lime"]), rgb(P3["lime1"]), rgb(P3["lime3"]), rgb(P3["lime4"])
NV1, NV2, NV3, NV4, NV5 = rgb(P3["navy1"]), rgb(P3["navy2"]), rgb(P3["navy3"]), rgb(P3["navy4"]), rgb(P3["navy5"])
G0, G1, G2, G, G4, WH = (rgb(P3["gray0"]), rgb(P3["gray1"]), rgb(P3["gray2"]), rgb(P3["gray"]), rgb(P3["gray4"]),
                         rgb(P3["white"]))
BG_NAVY, BG_NAVY1, BG_NAVY2, BG_LIME, BG_GRAY = (bg(P3["navy"]), bg(P3["navy1"]), bg(P3["navy2"]), bg(P3["lime"]),
                                                 bg(P3["gray"]))
BG_WHITE, BG_G0 = bg(P3["white"]), bg(P3["gray0"])
STATUS_NAMES = {"poison": "버그감염", "curse": "저주", "def_up": "방어↑", "spd_up": "속도↑", "focus": "집중",
                "stun": "멈춤", "sleep": "졸음", "confuse": "혼란"}
SICK_NAMES = {"cold": "감기", "overfed": "배탈", "burnout": "번아웃"}
_SGR = re.compile(r"\x1b\[[0-9;]*m")


# ============================================================== 작은 위젯
def _sgr_state(s, state=""):
    for m in _SGR.finditer(s):
        seq = m.group(0)
        state = "" if seq in ("\x1b[0m", "\x1b[m") else state + seq
    return state


def wrap_sep(text, width, sep=" · "):
    """' · ' 로 이어진 항목을 항목 단위로 줄바꿈 ('컴|포즈' 처럼 단어 중간에서 끊기지 않게).
    항목 하나가 줄보다 길면 그 항목만 글자 단위로 자른다. ANSI 색 상태는 다음 줄로 이어진다."""
    if vlen(text) <= width or sep not in text:
        return wrap(text, width)
    out, cur, state = [], None, ""
    for part in text.split(sep):
        start_state = state
        state = _sgr_state(part, state)
        if cur is None:
            cur = part
        elif vlen(cur) + vlen(sep) + vlen(part) <= width:
            cur += sep + part
        else:
            out.extend(wrap(cur, width))
            cur = start_state + part
    if cur is not None:
        out.extend(wrap(cur, width))
    return out


def wrap_words(text, width):
    """띄어쓰기 기준 줄바꿈 (한글도 단어째로 넘긴다). 색 없는 글자 전용.
    한 단어가 줄보다 길면 그 단어만 글자 단위로 자른다"""
    width = max(1, width)
    out, cur = [], ""
    for word in str(text).split(" "):
        cand = word if not cur else cur + " " + word
        if vlen(cand) <= width:
            cur = cand
            continue
        if cur:
            out.append(cur)
        while vlen(word) > width:
            w, k = 0, 0
            while k < len(word) and w + cw(word[k]) <= width:
                w += cw(word[k])
                k += 1
            out.append(word[:max(1, k)])
            word = word[max(1, k):]
        cur = word
    out.append(cur)
    return out


def need_hex(v):
    """넉넉함 → 라임, 보통 → 어두운 라임, 부족 → 밝은 회색, 위험 → 흰색"""
    return P3["lime"] if v >= 60 else P3["lime1"] if v >= 40 else P3["gray4"] if v >= 20 else P3["white"]


def need_color(v):
    return rgb(need_hex(v))


def hp_hex(v, mx):
    r = v / mx if mx else 0
    return P3["lime"] if r >= 0.5 else P3["lime3"] if r >= 0.25 else P3["white"]


def desc_lines(text, W, n=2):
    """아래쪽 설명 2줄: › 설명…"""
    out = wrap(f"{G}{text}{RST}", max(4, W - 2))[:n]
    return [(f"{NV4}›{RST} " if i == 0 else "  ") + ln for i, ln in enumerate(out)]


def rarity_color(iid):
    it = D.ITEMS.get(iid, {})
    return rgb(D.RARITY[it.get("rarity", 0)][1])


def item_label(iid, plus=0):
    it = D.ITEMS[iid]
    return f"{rarity_color(iid)}{it['name']}{RST}" + (f"{LIME}+{plus}{RST}" if plus else "")


def eff_text(iid):
    e = D.ITEMS[iid]["eff"]
    names = {"atk": "ATK", "df": "DEF", "int": "INT", "spd": "SPD", "luk": "LUK", "hp": "HP"}
    parts = [f"{names[k]}{'+' if v > 0 else ''}{v}" for k, v in e.items() if k in names]
    return " ".join(parts)


def face_sprite(g, now, form=None, face=None):
    """펫 스프라이트 4줄 (표정 치환) + 색"""
    p = g.p
    form = form or p["form"]
    f = D.FORMS[form]
    if form == "egg":
        left = 180 - (now - g.s["created"]) - g.s["timers"].get("egg_bonus", 0)
        if left < 40 and int(now * 3) % 2:
            art = f.get("crack", f["art"][0])
        else:
            art = f["art"][1 if g.fx.get("wobble", 0) > now or int(now * 1.5) % 4 == 0 else 0]
        return list(art), f["color"]
    frame = 0 if p["sleeping"] else int(now * 2) % 2
    fk = face or g.face_key(now) or "normal"
    art = [ln.replace("{f}", D.FACES.get(fk, "o_o")) for ln in f["art"][frame]]
    return art, f["color"]


# ============================================================== 가이드 (`?`) 문구
# 매뉴얼처럼 짧게: 이름(영문 대문자) + 한 줄 설명. 화면에 번호표로 붙는다.
GUIDE = {
    "tabs": ("MODES", "1~7 · Tab 으로 모드 전환. 7스토리 옆 LED = 새 챕터·보스·에필로그. 오른쪽 끝: ‼결재 · 작업 중 릴 · 전원 LED · 골드"),
    "keys": ("KEYS", "지금 누를 수 있는 키. 누르면 불이 켜짐. 색 있는 키 = 같은 색 값을 바꾸는 키"),
    "msg": ("MESSAGE", "펫의 말 · 알림 한 줄"),
    "room": ("ROOM", "펫이 사는 방. 오른쪽 위 미터 = AI 활동량, 아래 = 나이 · 무게. 원정 중엔 테이프 릴"),
    "level": ("LEVEL", "레벨(세그먼트) · EXP · HP/MP LED · 돌봄/훈육 노브 · 능력치 · GEN = 세대"),
    "hatch": ("HATCH", "부화 진행률. 3분이 지나고 첫 응답이 오면 깨어나요"),
    "needs": ("NEEDS", "포만 1 파랑 · 기분 2 초록 · 체력 3 흰색 · 건강 4 회색. 같은 색 키 F · P · Z · M 이 올려요"),
    "status": ("STATUS", "허락 대기 · 호출 · 버그 · 태세 · 버프가 이 줄에 떠요"),
    "quest": ("QUEST", "opencode 할 일(todo) 진행도 = 메인 퀘스트"),
    "log": ("LOG", "최근 기록. 제목 옆 LED 가 켜지면 방금 새 줄"),
    "guide": ("GUIDE", "첫 안내. 알이 깨면 사라져요"),
    "dungeon": ("DUNGEON", "지역 목록. ▮ 10칸 = 층 기록 · RD = 주간 레이드 · ↑↓ 고르고 Enter"),
    "info": ("INFO", "고른 지역 설명 · 보스 · 자동 원정이 보스에 도전하는 레벨"),
    "map": ("MAP", "층 지도. ◆ = 중보스(5층)·보스(10층), 라임 = 가 본 층"),
    "raid": ("RAID", "주간 레이드: 모든 탭의 펫이 한 보스를 함께 공격 (W)"),
    "auto": ("AUTO", "자동 원정 X · 자동 전투 T 스위치"),
    "floor": ("FLOOR", "층 시퀀서: 지난 층 라임 · 지금 층 깜빡 · ◆ 보스층"),
    "field": ("FIELD", "전투 무대. 가운데 위 = 스킬 이름 · 숫자가 떠오르면 피해"),
    "hp": ("HP", "펫 / 적 체력 LED 막대 (한 칸 = 한 단계)"),
    "event": ("EVENT", "선택지 이벤트. 1 · 2 로 고르거나 시간이 지나면 자동"),
    "round": ("ROUND", "레이드 라운드 (세그먼트 숫자). 12라운드면 끝"),
    "pages": ("PAGES", "←→ 페이지 전환. 오른쪽 점 = 지금 페이지"),
    "equip": ("EQUIP", "장착한 장비와 최종 능력치"),
    "list": ("LIST", "↑↓ 로 고르고 Enter"),
    "desc": ("DESC", "고른 항목 설명"),
    "gold": ("GOLD", "보유 골드. 바뀌면 숫자가 굴러가요"),
    "mats": ("MATS", "강화 재료 (opencode 도구가 일하면 생겨요)"),
    "enhance": ("ENHANCE", "+현재 › +다음 · 성공률 노브 · 비용 · 실패 시 하락"),
    "spec": ("SPEC", "능력치 표 (칸 하나 = 값 하나)"),
    "record": ("RECORD", "지금까지의 기록"),
    "sys": ("SYS", "저장 파일 · 마지막 저장 · 화면 fps · 토큰 경험치 효율 — 숨기지 않는 엔지니어링"),
    "chapter": ("CHAPTER", "지금 챕터와 줄거리. ←→ 로 지난 챕터 보기 · ↵ 대화 보기 (NEW = 아직 안 본 대화)"),
    "shards": ("SHARDS", "커밋 조각 12개 = 시즌 진행도. 챕터 보스를 쓰러뜨릴 때마다 하나씩 켜져요"),
    "missions": ("MISSIONS", "챕터 미션. √ 필수를 다 채우면 ◆ 챕터 보스에 도전 [B] · ☼ 보너스는 추가 보상"),
    "next": ("NEXT", "다음 챕터가 열리는 날. 챕터(=새 지역)는 일주일에 하나씩 열려요"),
    "slog": ("LOG", "스토리 기록: 챕터 시작 · 미션 완료 · 보스전 결과"),
    "talk": ("TALK", "대화. ↵ 다음 줄 (글자가 다 안 나왔으면 한 번에) · Esc 건너뛰기"),
}


# ============================================================== UI
class PetUI:
    def __init__(self, game):
        self.g = game
        self.tab = 0
        self.sub = {k: 0 for k in SUBTABS}
        self.cur = {}
        self.overlay = None      # dict(kind=..., ...)
        self.pet_x = None
        self.pet_dir = 1
        self.next_step = 0.0
        self.walk_phase = 0.0
        self.adv_zone = None
        self.protect = True
        self.enh_show = None
        self.last_render = 0.0
        self.msg = None          # (text, until)
        self.confirm_takeover = 0.0
        self.hangul_hint = 0.0
        self.boot_until = None     # 켜질 때 부팅 연출 (첫 render 에서 시작)
        self.wipe_t = 0.0          # 탭 전환 연출 시작 시각
        self._disp = {}            # 페이더 표시값 (부드럽게 따라가는 값)
        self.pressed = ("", 0.0)   # 방금 누른 키 (아래 키캡이 잠깐 라임으로 켜진다)
        self.guide = False         # `?` 가이드 (번호표 + 범례)
        self.guide_sel = 0         # 가이드에서 고른 번호 (0부터)
        self._tabs_end = 0
        self._anchors = []         # 이번 프레임에 그린 구역들의 위치 (가이드용)
        self._log_mark = (None, 0.0)   # 마지막 기록 줄과 그게 바뀐 시각 (LOG LED)
        self._frames = collections.deque(maxlen=20)   # 최근 프레임 시각 (fps)
        self.scene = None          # 스토리 대화 (dict: ch, part, lines, idx, t0, then)
        self.story_view = None     # 스토리 화면에서 보고 있는 챕터 (None = 지금 챕터)

    # ------------------------------------------------------------ 입력
    def text_entry(self):
        """글자를 그대로 받는 상태인가 (이름 입력)"""
        return bool(self.overlay and self.overlay.get("kind") == "rename")

    def keys(self, toks):
        """한 번에 들어온 키 묶음 처리. 붙여넣기처럼 몰려온 글자는 단축키로 해석하지 않는다
        (펫 칸에 실수로 붙여넣으면 판매/강화가 줄줄이 실행되는 사고 방지)"""
        if not toks:
            return
        chars = [t for t in toks if len(t) == 1 or t in ("ENTER", "TAB")]
        if len(chars) > 4 and not self.text_entry():
            self.g.input_seen()
            self._toast("붙여넣기로 보이는 입력은 무시했어요 (펫 칸에는 단축키만)")
            return
        for t in toks:
            self.key(t)

    def _welcome_visible(self):
        g = self.g
        ev = g.fx.get("evolve")
        rt = g.fx.get("retire")
        return bool(g.welcome) and not g.mg and not (ev and ev[2] > g.now()) and not (rt and rt[2] > g.now())

    def key(self, raw):
        g = self.g
        g.input_seen()
        if self.boot_until and time.time() < self.boot_until:
            self.boot_until = time.time()
            return
        k = norm_key(raw)
        self._mark_press(k)
        if self.guide:                       # 가이드: 숫자·←→ 로 항목 고르기, 다른 키는 닫기
            if len(k) == 1 and k in "123456789":
                self.guide_sel = int(k) - 1
            elif k in ("LEFT", "RIGHT"):
                self.guide_sel = max(0, self.guide_sel + (1 if k == "RIGHT" else -1))
            else:
                self.guide = False
            return
        if raw == "?" and not self.text_entry() and not (g.mg and g.mg["kind"] == "type"):
            self.guide, self.guide_sel = True, 0
            return
        now = g.now()
        if is_hangul(raw) and not self.text_entry() and not (g.mg and g.mg["kind"] == "type"):
            # 한글 입력 상태로 단축키를 누르면 입력기가 글자를 늦게/합쳐서 보낸다 → 안내 (키는 그대로 처리)
            if time.time() - self.hangul_hint > 20:
                self.hangul_hint = time.time()
                self._toast("한글 입력 상태예요 · 한/영 키로 영문 전환하면 단축키가 바로 먹어요", 4)
        ev = g.fx.get("evolve")
        if ev and ev[2] > now:
            if k in ("ESC", "ENTER", " "):
                g.fx["evolve"] = (ev[0], ev[1], now)
            return
        rt = g.fx.get("retire")
        if rt and rt[2] > now:
            if k in ("ESC", "ENTER", " "):
                g.fx["retire"] = (rt[0], rt[1], now)
            return
        # 팝업(환영/원정 결과)은 아무 키로 닫히고, 그 키가 Enter/Esc/Space 가 아니면 원래 동작도 한다
        closed = False
        if self._welcome_visible():
            g.welcome = None
            closed = True
        elif g.last_summary and g.last_summary[1] > now and not g.mg:
            g.last_summary = None
            closed = True
        if closed and k in ("ESC", "ENTER", " "):
            return
        if g.readonly:
            self.overlay = None
            if k == "o":
                res = g.take_over(force=time.time() < self.confirm_takeover)
                if res is None:
                    self.confirm_takeover = time.time() + 5
                    self._toast("다른 창이 아직 돌보는 중이에요 · 5초 안에 [O]를 한 번 더 누르면 이 창으로 가져와요", 5)
                elif res:
                    self.overlay = None
                    self._toast("이 창에서 돌보기 시작!")
                elif g.readonly_reason == "version":
                    self._toast("새 버전 ocmux가 만든 저장이라 이 창에선 읽기만 할 수 있어요", 4)
                else:
                    self._toast("지금은 가져올 수 없어요 (저장 파일을 읽는 중)", 3)
            elif k in ("TAB", "BTAB") or (len(k) == 1 and k in TAB_KEYS):
                self._switch_tab(k)
            elif k not in ("ESC",):
                self._toast("관전 모드예요 · [O] 이 창에서 돌보기", 2.5)
            return
        if self.scene:                       # 스토리 대화 중: ↵ 다음 · Esc 건너뛰기 (다른 키는 무시)
            self._scene_key(k)
            return
        if g.mg:
            kind = g.mg["kind"]
            if kind == "type" and raw not in ("ESC", "ENTER", "BS") and len(raw) == 1:
                g.minigame_key(raw)
            else:
                g.minigame_key(k if len(k) > 1 else raw if kind == "whack" else k)
            return
        if self.overlay:
            self._overlay_key(k, raw)
            return
        tab = TABS[self.tab][0]
        if tab == "adv" and g.event and not g.event.get("result") and k in ("1", "2", "3"):
            g.event_choose(int(k) - 1)
            return
        if k in ("TAB", "BTAB") or (len(k) == 1 and k in TAB_KEYS):
            self._switch_tab(k)
            return
        if tab in SUBTABS and k in ("LEFT", "RIGHT"):
            n = len(SUBTABS[tab])
            self.sub[tab] = (self.sub[tab] + (1 if k == "RIGHT" else -1)) % n
            return
        getattr(self, "_key_" + tab)(k, raw)

    PRESS = {"ENTER": "↵", "ESC": "Esc", "UP": "↑", "DOWN": "↓", "LEFT": "←", "RIGHT": "→", "TAB": "Tab",
             "BTAB": "Tab", "BS": "⌫"}

    def _mark_press(self, k):
        lab = self.PRESS.get(k) or (k.upper() if len(k) == 1 else "")
        if lab:
            self.pressed = (lab, time.time())

    def _is_pressed(self, cap):
        """아래 안내줄의 키캡이 방금 누른 키인가 (0.3초 동안 켜짐)"""
        lab, t = self.pressed
        if not lab or time.time() - t > 0.3:
            return False
        if cap == lab or (cap in ("←→", "↑↓") and lab in cap):    # '←→' 키캡은 ← 나 → 어느 쪽이든
            return True
        if len(cap) == 3 and cap[1] == "-" and lab.isdigit():      # '1-9', '7-9' 같은 범위
            return cap[0] <= lab <= cap[2]
        return False

    def _switch_tab(self, k):
        old = self.tab
        if k == "TAB":
            self.tab = (self.tab + 1) % len(TABS)
        elif k == "BTAB":
            self.tab = (self.tab - 1) % len(TABS)
        else:
            self.tab = int(k) - 1
        self.overlay = None
        if self.tab != old:
            self.wipe_t = time.time()
            if TABS[self.tab][0] == "story":
                self.story_view = None       # 스토리 화면은 늘 지금 챕터부터

    def _cursor(self, key, n, k):
        c = self.cur.get(key, 0)
        if n <= 0:
            self.cur[key] = 0
            return 0
        if k == "UP":
            c -= 1
        elif k == "DOWN":
            c += 1
        elif k == "PGUP":
            c -= 5
        elif k == "PGDN":
            c += 5
        elif k == "HOME":
            c = 0
        elif k == "END":
            c = n - 1
        c = max(0, min(n - 1, c))
        self.cur[key] = c
        return c

    def _toast(self, text, dur=2.5):
        self.msg = (text, time.time() + dur)

    # --- 홈
    def _key_home(self, k, raw):
        g = self.g
        if k == "f":
            foods = g.items_of(("food", "drink"))
            if not foods:
                g.speech = ("먹을 게 없어요… 상점에서 사 주세요! [4]", g.now() + 5)
            else:
                self.overlay = dict(kind="feed", items=foods)
        elif k == "m":
            meds = g.items_of(("med", "special"))
            if not meds:
                g.speech = ("약이 없어요… 상점 [4]에서 사 주세요", g.now() + 5)
            else:
                self.overlay = dict(kind="med", items=meds)
        elif k == "p":
            self.overlay = dict(kind="play")
        elif k == "c":
            g.clean()
        elif k == "z":
            g.toggle_sleep()
        elif k == "j":
            g.pat()
        elif k == "g":
            g.scold()
        elif k == "e":
            self.tab = 1

    # --- 모험
    def _key_adv(self, k, raw):
        g = self.g
        b = g.battle
        if b and b.get("story") is not None:
            self._story_battle_key(k)
            return
        if b and b.get("raid"):
            if not b.get("over"):
                if k == "a":
                    g.battle_action("attack")
                elif k == "s":
                    self.overlay = dict(kind="skill")
                elif k == "d":
                    g.battle_action("defend")
                elif k == "i":
                    self.overlay = dict(kind="bitem")
                elif k == "r":
                    g.raid_retreat()
            if k == "t":
                st = g.s["settings"]
                st["auto_battle"] = not st["auto_battle"]
                g.manual_until = 0
                self._toast(f"자동 전투 {'ON' if st['auto_battle'] else 'OFF (직접 조작)'}")
            return
        if g.expd:
            if g.battle and not g.battle.get("over"):
                if k == "a":
                    g.battle_action("attack")
                elif k == "s":
                    self.overlay = dict(kind="skill")
                elif k == "d":
                    g.battle_action("defend")
                elif k == "i":
                    self.overlay = dict(kind="bitem")
            if k == "r":
                g.recall()
            elif k == "t":
                st = g.s["settings"]
                st["auto_battle"] = not st["auto_battle"]
                g.manual_until = 0
                self._toast(f"자동 전투 {'ON' if st['auto_battle'] else 'OFF (직접 조작)'}")
            return
        zi = g.zones_info()
        c = self._cursor("zone", len(zi) + 1, k)      # 마지막 줄 = 주간 레이드
        if k == "w" or (k in ("ENTER", "e") and c == len(zi)):
            g.start_raid()
        elif k in ("ENTER", "e"):
            g.start_expedition(c)
        elif k == "b" and c < len(zi):
            g.start_expedition(c, from_start=True)
        elif k == "x":
            st = g.s["settings"]
            st["auto_exp"] = not st["auto_exp"]
            self._toast(f"자동 원정 {'ON' if st['auto_exp'] else 'OFF'}")
        elif k == "t":
            st = g.s["settings"]
            st["auto_battle"] = not st["auto_battle"]
            self._toast(f"자동 전투 {'ON' if st['auto_battle'] else 'OFF'}")

    # --- 가방
    def _bag_rows(self):
        g = self.g
        sub = self.sub["bag"]
        inv = g.s["inv"]
        if sub == 0:
            return [("gear", i, gg) for i, gg in enumerate(inv["gear"])]
        if sub == 1:
            return [("item", iid, n) for iid, n in sorted(inv["items"].items(), key=lambda x: (D.ITEMS[x[0]]["kind"], x[0])) if n > 0]
        if sub == 2:
            return [("mat", iid, n) for iid, n in sorted(inv["mats"].items()) if n > 0]
        return [("deco", iid, iid in inv["placed"]) for iid in inv["decos"]]

    def _key_bag(self, k, raw):
        g = self.g
        rows = self._bag_rows()
        c = self._cursor(f"bag{self.sub['bag']}", len(rows), k)
        if not rows:
            return
        kind, a, b_ = rows[c]
        if k == "ENTER":
            if kind == "gear":
                g.equip(a)
            elif kind == "item":
                g.use_item(a)
            elif kind == "deco":
                g.toggle_deco(a)
        elif k == "u" and self.sub["bag"] == 0:
            for slot in ("acc", "armor", "weapon"):
                if g.s["equip"].get(slot):
                    g.unequip(slot)
                    break

    # --- 상점
    def _key_shop(self, k, raw):
        g = self.g
        if self.sub["shop"] == 0:
            rows = g.shop_list()
            c = self._cursor("shop0", len(rows), k)
            if k == "ENTER" and rows:
                if g.buy(rows[c]["id"]):
                    self._toast(f"{D.ITEMS[rows[c]['id']]['name']} 구매!")
        else:
            rows = g.sell_list()
            c = self._cursor("shop1", len(rows), k)
            if k == "ENTER" and rows:
                if g.sell(rows[c]):
                    self._toast(f"판매 +{rows[c]['price']}G")

    # --- 공방
    def _key_forge(self, k, raw):
        g = self.g
        if self.sub["forge"] == 0:
            rows = g.enhance_targets()
            c = self._cursor("forge0", len(rows), k)
            if k == "p":
                self.protect = not self.protect
            elif k == "ENTER" and rows:
                where, key, _ = rows[c]
                res = g.enhance(where, key, self.protect)
                if res:
                    self.enh_show = (res, time.time())
        else:
            rows = g.recipe_list()
            c = self._cursor("forge1", len(rows), k)
            if k == "ENTER" and rows:
                g.craft(rows[c]["id"])

    # --- 도감
    SETTINGS = [("auto_exp", "자동 원정 (AI가 일하면 출발, 응답 오면 귀환)"), ("auto_battle", "자동 전투"),
                ("auto_items", "전투 중 자동 아이템 사용 (커피/핫픽스)"), ("toast", "opencode 화면에 토스트 알림 (레벨업/진화/보스)"),
                ("bell", "응답 도착 시 벨 소리"), ("perm_bell", "opencode가 허락/질문을 기다리면 벨 소리 (탭에 벨 표시)")]

    def _key_dex(self, k, raw):
        g = self.g
        sub = self.sub["dex"]
        if sub == DEX_PROFILE:
            if k == "r":
                ok, why = g.can_retire()
                if ok:
                    self.overlay = dict(kind="retire")
                else:
                    self._toast(why, 4)
        elif sub == DEX_QUEST:
            ql = g.s.get("quest_log") or {}
            self._cursor("dex_quest", len(ql.get("items") or []), k)
        elif sub == DEX_DIARY:
            self._cursor("dex_diary", len(g.s.get("diary", [])), k)
        elif sub == DEX_MON:
            self._cursor("dex_mon", len(D.MONSTERS), k)
        elif sub == DEX_FORMS:
            self._cursor("dex_forms", len(D.FORM_ORDER), k)
        elif sub == DEX_HALL:
            self._cursor("dex_hall", len(g.s["family"].get("hall") or []), k)
        elif sub == DEX_ACH:
            c = self._cursor("dex_ach", len(D.ACHIEVEMENTS), k)
            if k == "ENTER":
                aid, name, _, _, title = D.ACHIEVEMENTS[c]
                if aid in g.s["ach"] and title:
                    g.p["title"] = title
                    g.mark()
                    self._toast(f"칭호 변경: [{title}]")
        elif sub == DEX_SET:
            c = self._cursor("dex_set", len(self.SETTINGS) + 1, k)
            if k == "ENTER":
                if c < len(self.SETTINGS):
                    key = self.SETTINGS[c][0]
                    g.s["settings"][key] = not g.s["settings"].get(key, False)
                    g.mark()
                else:
                    if g.s["inv"]["items"].get("nametag", 0) <= 0:
                        self._toast("이름표가 필요해요 (상점 60G)")
                    else:
                        self.overlay = dict(kind="rename", buf="")

    # --- 스토리
    def _story_battle_key(self, k):
        g = self.g
        b = g.battle
        if not b.get("over"):
            if k == "a":
                g.battle_action("attack")
            elif k == "s":
                self.overlay = dict(kind="skill")
            elif k == "d":
                g.battle_action("defend")
            elif k == "i":
                self.overlay = dict(kind="bitem")
            elif k == "r":
                g.story_retreat()
        if k == "t":
            st = g.s["settings"]
            st["auto_battle"] = not st["auto_battle"]
            g.manual_until = 0
            self._toast(f"자동 전투 {'ON' if st['auto_battle'] else 'OFF (직접 조작)'}")

    def _story_idx(self):
        """스토리 화면에서 보고 있는 챕터 번호 (0부터). 지금 챕터 + 1(예고)까지만 볼 수 있다"""
        st = self.g.story()
        if not st:
            return 0
        top = min(len(D.CHAPTERS) - 1, st["ch"] + (0 if st["phase"] == "end" else 1))
        v = st["ch"] if self.story_view is None else self.story_view
        return max(0, min(top, v))

    def _key_story(self, k, raw):
        g = self.g
        st = g.story()
        if g.battle and g.battle.get("story") is not None:
            self._story_battle_key(k)
            return
        if not st:
            if k == "ENTER":
                self._toast("알이 깨면 이야기가 시작돼요")
            return
        i = self._story_idx()
        top = min(len(D.CHAPTERS) - 1, st["ch"] + (0 if st["phase"] == "end" else 1))
        if k in ("LEFT", "RIGHT"):
            self.story_view = max(0, min(top, i + (1 if k == "RIGHT" else -1)))
            if self.story_view == st["ch"]:
                self.story_view = None
        elif k == "ENTER":
            self._story_enter(i)
        elif k == "b":
            if i != st["ch"]:
                self._toast("지금 챕터에서만 보스에 도전할 수 있어요 (←→ 로 돌아가기)")
                return
            ok, why = g.can_story_boss()
            if not ok:
                self._toast(why, 4)
                return
            self._scene_start(st["ch"], "boss", then="boss")

    def _story_enter(self, i):
        """↵: 이 챕터에서 지금 볼 만한 대화 (에필로그 대기 > 안 본 프롤로그 > 다시 보기)"""
        g = self.g
        st = g.story()
        c = D.CHAPTERS[i]
        if i > st["ch"]:
            self._toast("아직 열리지 않은 챕터예요")
            return
        if c["id"] in st["cleared"]:
            if st.get("pending") == i or not g.story_seen(i, "outro"):
                self._scene_start(i, "outro")
            else:
                self._scene_start(i, "replay")
            return
        self._scene_start(i, "intro")

    def _scene_lines(self, i, part):
        c = D.CHAPTERS[i]
        if part == "intro":
            return list(c["intro"])
        if part == "boss":
            return list(c["boss"]["intro"])
        if part == "outro":
            return list(c["outro"])
        return list(c["intro"]) + [("narr", "· · ·")] + list(c["boss"]["intro"]) + [("narr", "· · ·")] + list(c["outro"])

    def _scene_start(self, i, part, then=None):
        self.scene = dict(ch=i, part=part, lines=self._scene_lines(i, part), idx=0, t0=time.time(), then=then)
        self.overlay = None

    def _scene_text(self, spk_text):
        spk, text = spk_text
        return P.fix_josa(text.replace("{name}", self.g.p["name"]))

    def _scene_key(self, k):
        sc = self.scene
        if k == "ESC":
            self._scene_end()
            return
        if k in ("ENTER", " ", "RIGHT"):
            full = len(self._scene_text(sc["lines"][sc["idx"]]))
            shown = int((time.time() - sc["t0"]) * SCENE_CPS)
            if shown < full:
                sc["t0"] = time.time() - full / SCENE_CPS - 0.01       # 글자가 다 안 나왔으면 한 번에
                return
            if sc["idx"] + 1 < len(sc["lines"]):
                sc["idx"] += 1
                sc["t0"] = time.time()
                return
            self._scene_end()

    def _scene_end(self):
        g, sc = self.g, self.scene
        self.scene = None
        if not sc:
            return
        if sc["part"] in ("intro", "boss", "outro"):
            g.story_mark_seen(sc["ch"], sc["part"])
        if sc["part"] == "replay":
            g.story_mark_seen(sc["ch"], "outro")
        if sc.get("then") == "boss":
            if not g.start_story_boss():
                self._toast("지금은 도전할 수 없어요", 3)

    # --- 오버레이
    def _overlay_key(self, k, raw):
        g, ov = self.g, self.overlay
        kind = ov["kind"]
        if k == "ESC":
            self.overlay = None
            return
        if kind == "rename":
            if raw == "ENTER":
                if g.rename(ov["buf"]):
                    self._toast("이름을 바꿨어요!")
                self.overlay = None
            elif raw == "BS":
                ov["buf"] = ov["buf"][:-1]
            elif len(raw) == 1 and len(ov["buf"]) < 12:
                ov["buf"] += raw
            return
        num = int(k) if len(k) == 1 and k in "123456789" else 0     # isdigit() 은 '²' '①' 도 참이라 안 씀
        if kind in ("feed", "med"):
            items = ov["items"]
            c = self._cursor("ov_" + kind, len(items), k)
            if items and (k == "ENTER" or 0 < num <= len(items)):
                idx = num - 1 if num else min(c, len(items) - 1)
                g.use_item(items[idx][0])
                self.overlay = None
            return
        if kind == "play":
            if 0 < num <= len(D.MINIGAMES):
                g.start_minigame(D.MINIGAMES[num - 1][0])
                self.overlay = None
            return
        if kind == "skill":
            skills = g.available_skills()
            if 0 < num <= len(skills):
                g.battle_action("skill", skills[num - 1])
                self.overlay = None
            return
        if kind == "bitem":
            items = g.battle_items()
            if 0 < num <= len(items):
                g.battle_action("item", items[num - 1][0])
                self.overlay = None
            return
        if kind == "retire":
            if k == "ENTER":
                self.overlay = None
                if g.retire():
                    self.tab = 0
            return

    # ============================================================ 렌더
    def render(self, W, H):
        g, now = self.g, time.time()
        gnow = g.now()
        if W < 40 or H < 14:
            return [clip(f"{LIME}TOKEN QUEST{RST} {G1}창을 조금 키워주세요 (최소 40x14, 지금 {W}x{H}){RST}", W)]
        cv = Canvas(W, H)
        self._frames.append(now)
        self._anchors = []
        if self.boot_until is None:
            self.boot_until = now + 1.6
        if now < self.boot_until:
            self._boot_scene(cv, W, H, 1.6 - (self.boot_until - now))
            return cv.lines()
        self._header(cv, W)
        self._anchor(self._tabs_end, 0, "tabs")
        top, bottom = 1, H - 2          # 내용: top..bottom-1, H-2: 메시지 줄, H-1: 키 안내
        ev = g.fx.get("evolve")
        rt = g.fx.get("retire")
        self._story_auto(gnow)
        if rt and rt[2] > gnow:
            self._retire_scene(cv, 0, top, W, bottom - top, rt, gnow)
        elif ev and ev[2] > gnow:
            self._evolve_scene(cv, 0, top, W, bottom - top, ev, gnow)
        elif self.scene:
            self._draw_scene(cv, 0, top, W, bottom - top, gnow)
        elif g.mg:
            self._minigame(cv, 0, top, W, bottom - top, gnow)
        else:
            getattr(self, "_draw_" + TABS[self.tab][0])(cv, 0, top, W, bottom - top, gnow)
            if self.overlay:
                self._draw_overlay(cv, W, H, gnow)
            if g.last_summary and g.last_summary[1] > gnow:
                self._summary_box(cv, W, H, g.last_summary[0])
            if g.welcome:
                self._welcome_box(cv, W, H, g.welcome)
            self._wipe(cv, W, top, bottom - top, now)
        self._message_line(cv, W, H - 2, gnow, now)
        self._hints(cv, W, H - 1)
        self._anchor(W - 1, H - 1, "keys")
        if self.guide:
            items = [(x, y) + GUIDE[key] for x, y, key in self._anchors if key in GUIDE]
            items = [it for it in items if it[1] < H - 3 or it[1] == H - 1]
            self.guide_sel = min(self.guide_sel, max(0, len(items) - 1))
            guide_draw(cv, W, H, items, self.guide_sel, strip_y=H - 3)
        self.last_render = now
        return cv.lines()

    def _story_auto(self, gnow):
        """스토리 화면에 들어오면: 기다리던 에필로그 → 안 본 프롤로그 순서로 대화를 자동으로 연다"""
        g = self.g
        if TABS[self.tab][0] != "story" or self.scene or g.battle or self.overlay or g.mg or g.readonly:
            return
        if g.welcome or (g.last_summary and g.last_summary[1] > gnow) or self.story_view is not None:
            return
        st = g.story()
        if not st:
            return
        if st.get("pending") is not None:
            self._scene_start(st["pending"], "outro")
        elif st["phase"] in ("play", "boss") and not g.story_seen(st["ch"], "intro"):
            self._scene_start(st["ch"], "intro")

    def _story_news(self):
        """스토리 탭에 불을 켤 일: 안 본 프롤로그 · 보스 도전 가능 · 에필로그 대기"""
        st = self.g.story()
        if not st or self.g.is_egg():
            return False
        return (st.get("pending") is not None or st["phase"] == "boss"
                or (st["phase"] in ("play", "boss") and not self.g.story_seen(st["ch"], "intro")))

    def _anchor(self, x, y, key):
        """가이드(`?`)가 번호표를 붙일 자리. 같은 이름은 한 번만"""
        if all(k != key for _, _, k in self._anchors):
            self._anchors.append((x, y, key))

    def _wipe(self, cv, W, y0, h, now):
        """탭 전환 연출: 라임 세로 막대가 왼쪽에서 오른쪽으로 지나가며 새 화면을 드러낸다 (0.24초)"""
        if not self.wipe_t:
            return
        t = (now - self.wipe_t) / 0.24
        if t >= 1:
            self.wipe_t = 0.0
            return
        x = int(t * W)
        for yy in range(y0, y0 + h):
            cv.text(x + 1, yy, " " * max(0, W - x - 1))
            cv.text(x, yy, "▌", LIME)

    def _boot_scene(self, cv, W, H, t):
        """켜질 때 1.6초: 점 격자 → 세그먼트 워드마크 → 라임 줄 (아무 키나 누르면 건너뜀)"""
        boot_draw(cv, W, H, t, "TOKEN QUEST", "TQ–1 · PET OS · opencode 토큰으로 자라는 펫", 1.6)

    # ------------------------------------------------------------ 공통 틀
    def _header(self, cv, W):
        """맨 윗줄 = 네이비 바. 번호 붙은 탭(선택은 라임) + 오른쪽 상태 LED"""
        g = self.g
        now = time.time()
        cv.panel(0, 0, W, 1, "navy")
        x = 0
        mode = 2 if W >= 50 else 1 if W >= 44 else 0
        news = self._story_news()
        for i, (tid, label) in enumerate(TABS):
            lab = f"{i + 1}{label}" if mode == 2 else label if mode == 1 else label[:1]
            if i == self.tab:
                x = cv.text(x, 0, f" {lab} ", BG_LIME + BLACK + B)
            elif tid == "story" and news:
                # 새 소식 LED: 안 본 챕터 대화 · 보스 도전 가능 · 에필로그 대기
                x = cv.text(x, 0, f" {lab}", BG_NAVY + G)
                x = cv.text(x, 0, "●", BG_NAVY + (LIME if int(now * 2) % 2 else NV3))
            else:
                x = cv.text(x, 0, f" {lab} ", BG_NAVY + G)
        self._tabs_end = x
        parts = []
        alert = spin = None
        if g.readonly:
            parts.append(f"{BG_NAVY}{NV4}관전{RST}")
        if g.waits:
            w = next(iter(g.waits.values()))
            label = "결재" if w["kind"] == "perm" else "질문"
            alert = (BG_LIME + BLACK + B if int(now * 2) % 2 else BG_NAVY + LIME + B) + f"‼{label}" + RST
            parts.append(alert)
        if g.s.get("call"):
            parts.append(f"{BG_NAVY}{LIME if int(now * 2) % 2 else NV2}{B}!{RST}")
        if g.busy_roots:
            spin = f"{BG_NAVY}{LIME}{spinner(now)}{spinner(now + 0.37)}{RST}"
            parts.append(spin)
        breath = (now % 2.4) < 2.0
        led = f"{BG_NAVY}{LIME if breath else NV2}●{RST}"
        parts.append(led)
        gold_v = self._ease("gold", float(g.s["gold"]), now, speed=6.0)
        gold = f"{BG_NAVY}{G4}{P.fmt_num(int(round(gold_v)))}G{RST}"
        # 좁으면 골드 → 스피너 순으로 빼고, 끝까지 남기는 건 결재 알림
        lite = " ".join(p for p in parts if p is not spin)
        for right in (" ".join(parts + [gold]), " ".join(parts), lite, alert or led, led):
            if right and W - vlen(right) - 1 >= x + 1:
                cv.ansi(W - vlen(right) - 1, 0, right, BG_NAVY)
                break

    def _message_line(self, cv, W, y, gnow, now):
        g = self.g
        if g.banner:
            text, color, until = g.banner
            urgent = color in (P3["white"],) or text.startswith(("‼", "!!", "?"))
            if urgent:
                on = int(now * 3) % 2 or (until - gnow) < 2.5
                cv.ansi_clip(0, y, (f"{BG_LIME}{BLACK}{B}" if on else f"{BG_NAVY}{WH}{B}") + f" {text} " + RST, W)
            else:
                cv.ansi_clip(0, y, f"{LIME}■{RST} {rgb(color)}{text}{RST}", W)
        elif self.msg and self.msg[1] > now:
            cv.ansi_clip(0, y, f"{NV4}›{RST} {G4}{self.msg[0]}{RST}", W)
        elif g.readonly:
            cv.ansi_clip(0, y, f"{NV4}›{RST} {G}다른 창에서 돌보는 중 · 관전 모드{RST}", W)
        else:
            sp = P.fix_josa(g.speech[0]) if g.speech[1] > gnow else ""
            if sp:
                col = rgb(D.FORMS[g.p["form"]]["color"])
                cv.ansi_clip(0, y, f"{col}{B}{g.p['name']}{RST} {G1}▸{RST} {G4}{sp}{RST}", W)

    HINTS_OVERLAY = {
        "feed": [("↑↓", "선택"), ("↵", "먹이기"), ("Esc", "닫기")], "med": [("↑↓", "선택"), ("↵", "사용"), ("Esc", "닫기")],
        "play": [("1", "방향"), ("2", "버그"), ("3", "타자"), ("4", "퀴즈"), ("Esc", "닫기")],
        "skill": [("1-9", "스킬"), ("Esc", "닫기")], "bitem": [("1-9", "아이템"), ("Esc", "닫기")],
        "rename": [("↵", "확인"), ("Esc", "취소")], "retire": [("↵", "은퇴식"), ("Esc", "취소")],
    }

    def _hint_pairs(self):
        g = self.g
        tab = TABS[self.tab][0]
        on = lambda b: "ON" if b else "OFF"  # noqa: E731
        st = g.s["settings"]
        if g.readonly:
            return [("O", "이 창에서 돌보기"), ("Tab", "화면")]
        if self.scene:
            last = self.scene["idx"] + 1 >= len(self.scene["lines"])
            return [("↵", "닫기" if last and self.scene.get("then") != "boss" else "보스전!" if last else "다음"),
                    ("Esc", "건너뛰기"), ("", f"{self.scene['idx'] + 1}/{len(self.scene['lines'])}")]
        if g.mg:
            if g.mg.get("phase") == "result":
                return [("↵", "닫기")]
            return {"dir": [("←", "왼쪽"), ("→", "오른쪽"), ("Esc", "그만")],
                    "whack": [("7-9", ""), ("4-6", ""), ("1-3", "버그 잡기"), ("Esc", "그만")],
                    "type": [("↵", "입력"), ("⌫", "지우기"), ("Esc", "그만")],
                    "quiz": [("O", "맞다", P3["lime"]), ("X", "아니다", P3["gray"]), ("↵", "다음"), ("Esc", "그만")]}[g.mg["kind"]]
        if self.overlay:
            return self.HINTS_OVERLAY[self.overlay["kind"]]
        if tab == "home":
            if g.is_egg():
                return [("J", "쓰담"), ("", "응답이 오면 부화해요")]
            # 색 = 조작: 페이더 색과 같은 키 (포만① F · 기분② P · 체력③ Z · 건강④ M)
            return [("F", "밥", ENC[0]), ("P", "놀기", ENC[1]), ("Z", "잠", ENC[2]), ("M", "약", ENC[3]),
                    ("C", "청소"), ("J", "쓰담"), ("G", "훈육")]
        if tab == "adv":
            if g.battle and g.battle.get("story") is not None:
                return [("A", "공격"), ("S", "스킬"), ("D", "방어"), ("I", "템"), ("R", "물러나기"), ("T", "자동 " + on(st["auto_battle"]))]
            if g.battle and g.battle.get("raid"):
                return [("A", "공격"), ("S", "스킬"), ("D", "방어"), ("I", "템"), ("R", "빠지기"), ("T", "자동 " + on(st["auto_battle"]))]
            if g.expd:
                if g.event and not g.event.get("result"):
                    return [("1", "선택"), ("2", "선택"), ("R", "귀환")]
                return [("A", "공격"), ("S", "스킬"), ("D", "방어"), ("I", "템"), ("R", "귀환"), ("T", "자동 " + on(st["auto_battle"]))]
            return [("↑↓", "지역"), ("↵", "출발"), ("B", "1층부터"), ("W", "레이드"), ("X", "자동원정 " + on(st["auto_exp"]))]
        if tab == "bag":
            return [[("←→", "분류"), ("↵", "장착"), ("U", "해제")], [("←→", "분류"), ("↵", "사용")],
                    [("←→", "분류"), ("", "재료는 공방에서")], [("←→", "분류"), ("↵", "배치/치우기")]][self.sub["bag"]]
        if tab == "shop":
            return [("←→", "구매/판매"), ("↑↓", "선택"), ("↵", "구매" if self.sub["shop"] == 0 else "판매")]
        if tab == "forge":
            if self.sub["forge"] == 0:
                return [("←→", "강화/제작"), ("↵", "강화"), ("P", "러버덕 보호 " + on(self.protect))]
            return [("←→", "강화/제작"), ("↵", "제작")]
        if tab == "story":
            b = g.battle
            if b and b.get("story") is not None:
                return [("A", "공격"), ("S", "스킬"), ("D", "방어"), ("I", "템"), ("R", "물러나기"), ("T", "자동 " + on(st["auto_battle"]))]
            s = g.story()
            if not s:
                return [("", "알이 깨면 이야기가 시작돼요")]
            pairs = [("←→", "챕터"), ("↵", "대화")]
            if self._story_idx() == s["ch"] and s["phase"] == "boss":
                pairs.append(("B", "보스 도전!", P3["lime"]))
            return pairs
        if self.sub["dex"] == DEX_PROFILE:
            return [("←→", "분류"), ("R", "은퇴식")]
        return [("←→", "분류"), ("↑↓", "이동"), ("↵", "선택")]

    def _hints(self, cv, W, y):
        pairs = list(self._hint_pairs())
        if not (self.g.mg or self.overlay or self.scene):
            pairs += [("?", "가이드"), ("Tab", "화면")]
        out, used = [], 0
        for pr in pairs:
            k, lab = pr[0], pr[1]
            color = pr[2] if len(pr) > 2 else None
            piece = (keycap(k, lab, on=self._is_pressed(k), color=color) if k else f"{G1}{lab}{RST}")
            wlen = vlen(piece) + (2 if out else 0)
            if used + wlen > W:
                break
            out.append(piece)
            used += wlen
        cv.ansi(0, y, "  ".join(out))

    def _list(self, cv, x, y, w, h, rows, cursor, empty="(비어 있음)", base="", sel="navy1"):
        """rows: ANSI 문자열 리스트. 선택 줄은 네이비 막대 + 라임 ▶. 스크롤 처리.
        base: 패널 위에 그릴 때 바탕색 유지 (예: BG_NAVY)"""
        if not rows:
            cv.ansi(x + 1, y, f"{G1}{empty}{RST}", base)
            return
        h = max(1, h)
        top = 0 if cursor < h else cursor - h + 1
        sbg = bg(P3.get(sel, sel))
        for i in range(top, min(len(rows), top + h)):
            yy = y + i - top
            if i == cursor:
                cv.panel(x, yy, w, 1, sel)
                cv.ansi(x, yy, f"{LIME}▶{RST}", sbg)
                cv.ansi_clip(x + 2, yy, rows[i], w - 3, sbg)
            else:
                cv.ansi_clip(x + 2, yy, rows[i], w - 3, base)
        if len(rows) > h:
            cv.ansi(x + w - 1, y, f"{G1}▴{RST}" if top > 0 else " ", base)
            cv.ansi(x + w - 1, y + h - 1, f"{G1}▾{RST}" if top + h < len(rows) else " ", base)

    def _subtabs(self, cv, x, y, tab, width=None):
        """세그먼트 스위치: 선택은 라임 블록, 나머지는 네이비 블록. 오른쪽 끝에 페이지 점 (○●○○)"""
        names = SUBTABS[tab]
        width = width or (cv.w - x)
        cur = self.sub[tab]
        ws = [vlen(n) + 3 for n in names]
        start = 0
        if sum(ws) > width:
            while start < cur and sum(ws[start:cur + 1]) + 2 > width:
                start += 1
        x0 = x
        fits = start == 0
        if start:
            x = cv.ansi(x, y, f"{G1}‹{RST}")
        for i in range(start, len(names)):
            if x - x0 + ws[i] > width:
                cv.ansi(min(x, x0 + width - 1), y, f"{G1}›{RST}")
                fits = False
                break
            if i == cur:
                x = cv.ansi(x, y, f"{BG_LIME}{BLACK}{B} {names[i]} {RST}")
            else:
                x = cv.ansi(x, y, f"{BG_NAVY1}{G} {names[i]} {RST}")
            x += 1
        if fits and x - x0 + len(names) <= width:
            x = cv.ansi(x, y, page_dots(cur, len(names))) + 1
        self._anchor(min(x, x0 + width - 1), y, "pages")
        return x

    # ------------------------------------------------------------ 홈
    def _draw_home(self, cv, x0, y0, W, H, gnow):
        """홈 = 01 ROOM(방) + 02 LEVEL(계기판) + 페이더 4개 + 상태줄 + 03 LOG"""
        g = self.g
        now = time.time()
        egg = g.is_egg()
        side = W >= 72 and H >= 12
        sw = 25 if side else 0
        self._home_id(cv, x0, y0, W, gnow, side)
        q = None if egg else g.quest_progress()
        if egg:
            room_h = max(6, min(9, H - 6))
        else:
            fixed = 1 + 2 + 1 + (1 if q else 0)
            room_h = max(6, min(12 if H >= 30 else 10, H - fixed - 5))
        ry = y0 + 1
        self._room(cv, x0, ry, W - sw, room_h, gnow)
        self._anchor(x0 + title_end(1, "ROOM", boxed=True), ry, "room")
        if side:
            self._level_panel(cv, x0 + W - sw + 1, ry, sw - 1, room_h, gnow, now)
            self._anchor(x0 + W - sw + 1 + title_end(2, "HATCH" if egg else "LEVEL", boxed=True), ry,
                         "hatch" if egg else "level")
        y = ry + room_h
        end = y0 + H
        if egg:
            self._egg_guide(cv, x0, y, W, end - y, gnow, side)
            return
        # 페이더 4개 (포만/기분/체력/건강) — 색 = 키 (F/P/Z/M)
        if y + 2 <= end:
            self._vitals(cv, x0, y, W, now)
            self._anchor(x0 + (W - 2) // 2, y, "needs")
            y += 2
        # 상태줄: 결재 대기 > 호출 > 떼쓰기 > (버그·태세·버프 / 좁으면 HP·MP)
        if y < end:
            self._status_row(cv, x0, y, W, gnow, now, side)
            self._anchor(x0 + W - 1, y, "status")
            y += 1
        # 메인 퀘스트 (opencode 할 일 목록)
        if q and y < end:
            done, total, cur = q
            n = max(4, min(12, total))
            tail = f"{G1}지금{RST} {G4}{cur}{RST}" if done < total else f"{LIME}{B}전부 완료!{RST}"
            cv.ansi_clip(x0, y, f"{G1}QUEST{RST} {LIME}{B}{done}/{total}{RST} {segbar(done, total, n)} {tail}", W)
            self._anchor(x0 + W - 1, y, "quest")
            y += 1
        if end - y >= 2:
            self._log_panel(cv, x0, y, W, end - y, 3)
            self._anchor(x0 + title_end(3, "LOG", led=True), y, "log")

    def _home_id(self, cv, x0, y, W, gnow, side):
        """맨 윗줄: 이름 「칭호」 [형태] (좁으면 LV) ··· 오른쪽 상태 칩"""
        g, p = self.g, self.g.p
        f = D.FORMS[p["form"]]
        col = rgb(f["color"])
        name = f"{col}{B}{p['name']}{RST}"
        title = f" {G}「{p['title']}」{RST}" if p.get("title") else ""
        form = f" {BG_NAVY1}{G4} {f['name']} {RST}"
        lv = f" {G1}LV{RST}{LIME}{B}{p['lvl']}{RST}" if not side and not g.is_egg() else ""
        tags = []
        if g.expd:
            tags.append(f"{BG_NAVY2}{WH} 원정 {RST}")
        if p["sleeping"]:
            tags.append(f"{BG_NAVY1}{NV4} zZ {RST}")
        if p["sick"]:
            tags.append(f"{BG_WHITE}{BLACK}{B} {SICK_NAMES.get(p['sick'], p['sick'])} {RST}")
        if g.absent_since is not None:
            tags.append(f"{G1}기다리는 중{RST}")
        right = " ".join(tags)
        room = W - (vlen(right) + 2 if right else 0)
        # 좁으면 칭호 → 형태 순으로 뺀다 (이름과 LV 는 끝까지 남김)
        for s in (name + title + form + lv, name + form + lv, name + lv, name):
            if vlen(s) <= room:
                break
        if right and vlen(s) + vlen(right) + 2 <= W:
            cv.ansi(x0 + W - vlen(right), y, right)
            cv.ansi_clip(x0, y, s, W - vlen(right) - 1)
        else:
            cv.ansi_clip(x0, y, s + ("  " + right if right else ""), W)

    def _modbox(self, cv, x, y, w, h, num, title, right="", foot_l="", foot_r="", color=None, on=True):
        """번호 붙은 모듈 틀: ┌ 01 ROOM ──── right ┐ … └ foot_l ─── foot_r ┘"""
        col = color or NV2
        cv.box(x, y, w, h, col)
        lab = f" {module(num, title, on)} "
        room = w - 4
        if right and vlen(lab) + vlen(right) + 3 <= room:
            cv.ansi(x + w - 2 - vlen(right) - 2, y, f" {right} ")
        cv.ansi_clip(x + 1, y, lab, room + 1)
        if h >= 2:
            yb = y + h - 1
            if foot_r and vlen(foot_r) + 4 <= room:
                cv.ansi(x + w - 2 - vlen(foot_r) - 2, yb, f" {G1}{foot_r}{RST} ")
                room -= vlen(foot_r) + 3
            if foot_l and room > 4:
                cv.ansi_clip(x + 2, yb, f" {G1}{foot_l}{RST} ", room - 1)

    def _ease(self, key, v, now, speed=7.0):
        """페이더가 기계처럼 미끄러지게: 표시값이 실제값을 따라간다"""
        d = self._disp.get(key)
        if d is None or abs(d[0] - v) < 0.4:
            self._disp[key] = [v, now]
            return v
        dt = max(0.0, min(0.5, now - d[1]))
        d[0] += (v - d[0]) * min(1.0, dt * speed)
        d[1] = now
        return d[0]

    def _vu(self, now, n=6):
        """AI 활동 레벨 미터 (응답 생성 중이면 출렁인다)"""
        busy = bool(self.g.busy_roots)
        out = []
        for i in range(n):
            if busy:
                lv = (math.sin(now * 7.3 + i * 1.7) + math.sin(now * 3.1 + i * 0.9) + 2) / 4
                out.append("▁▂▃▄▅▆▇"[min(6, int(lv * 7))])
            else:
                out.append("▁")
        return (LIME if busy else NV2) + "".join(out) + RST

    def _vitals(self, cv, x0, y, W, now):
        """페이더 4개. 색 = 조작: 포만①파랑(F) · 기분②초록(P) · 체력③흰색(Z) · 건강④회색(M).
        색은 '어느 키가 바꾸는 값인가'를 뜻하고, 부족함은 숫자(20 미만이면 흰 블록 깜빡)로 보여 준다"""
        p = self.g.p
        cells_ = [("포만", "full"), ("기분", "mood"), ("체력", "energy"), ("건강", "health")]
        half = (W - 2) // 2
        fw = max(3, half - 11)
        blink = int(now * 2) % 2
        for i, (lab, k) in enumerate(cells_):
            v = min(100.0, max(0.0, float(p[k])))
            dv = self._ease(k, v, now)
            xx = x0 + (0 if i % 2 == 0 else half + 2)
            col = ENC[i]
            if v < 20:
                num = (f"{BG_WHITE}{BLACK}{B}{int(round(v)):>3}{RST}" if blink else f"{WH}{B}{int(round(v)):>3}{RST}")
            else:
                num = f"{G4}{B}{int(round(v)):>3}{RST}"
            cv.ansi(xx, y + i // 2, f"{enc_dot(i)} {G}{lab}{RST} {meter(dv, 100, fw, on=col)} {num}")

    def _status_row(self, cv, x0, y, W, gnow, now, side):
        g, p = self.g, self.g.p
        blink = int(now * 2) % 2
        if g.waits:
            w = next(iter(g.waits.values()))
            tag, what = ("PERM", "허락 대기") if w["kind"] == "perm" else ("ASK", "질문 도착")
            head = chip(tag, "black", "lime") if blink else chip(tag, "lime", "navy2")
            cv.ansi_clip(x0, y, f"{head} {WH}{B}{what}{RST} {G4}{w['label']}{RST} {G1}· opencode 창에서 응답{RST}", W)
            return
        call = g.s.get("call")
        if call:
            left = max(0, int(P.T["call_expire"] - (gnow - call["since"])))
            head = chip("CALL", "black", "lime") if blink else chip("CALL", "lime", "navy2")
            if call["kind"] == "tantrum":
                body = (f"{WH}{B}떼쓰는 중!!{RST} {G1}다 채워져 있어요 →{RST} {keycap('G', '훈육')} "
                        f"{G1}· 받아주면 응석받이 · {left // 60}분{RST}")
            else:
                txt, keyh = D.CALLS[call["kind"]]
                body = f"{WH}{B}\"{txt}\"{RST} {keycap(keyh)} {G1}{left // 60}분 안에 응답하면 돌봄↑{RST}"
            cv.ansi_clip(x0, y, f"{head} {body}", W)
            return
        parts = []
        s_ = g.story()
        if s_ and self._story_news():
            if s_.get("pending") is not None:
                msg = f"{G4}에필로그 도착{RST}"
            elif s_["phase"] == "boss":
                msg = f"{WH}{B}챕터 보스 도전 가능{RST}"
            else:
                msg = f"{G4}새 챕터 CH{s_['ch'] + 1:02d}{RST}"
            parts.append((chip("STORY", "black", "lime") if blink else chip("STORY", "lime", "navy2")) + f" {msg} {G1}[7]{RST}")
        if not side:
            S = g.stats()
            parts.append(f"{G1}HP{RST}{segbar(p['hp'], S['maxhp'], 6, on=hp_hex(p['hp'], S['maxhp']))}")
            parts.append(f"{G1}MP{RST}{segbar(p['mp'], S['maxmp'], 4, on=P3['navy4'])}")
            parts.append(f"{G1}돌봄{RST}{LIME}{knob(p['care'])}{int(p['care'])}{RST}")
            parts.append(f"{G1}훈육{RST}{NV4}{knob(p.get('discipline', 50))}{int(p.get('discipline', 50))}{RST}")
        if p["bugs"]:
            parts.append(f"{WH}{B}ж{p['bugs']}{RST}")
        if g.stance:
            stance = {"build": "공격", "plan": "전략"}.get(g.stance, g.stance)
            parts.append(f"{G1}태세{RST} {LIME3}{stance}{RST}")
        if g.s["buffs"].get("exp_boost", 0) > gnow:
            parts.append(chip("EXP×2", "black", "lime3"))
        if side and not parts:
            parts.append(f"{G1}NEXT ›{RST} {G}{g.evolution_hint()}{RST}")
        cv.ansi_clip(x0, y, "  ".join(parts), W)

    def _level_panel(self, cv, x, y, w, h, gnow, now):
        """02 LEVEL: 세그먼트 숫자 레벨 + EXP 페이더 + HP/MP LED 막대 + 돌봄/훈육 노브 + 능력치"""
        g, p = self.g, self.g.p
        if g.is_egg():
            return self._hatch_panel(cv, x, y, w, h, gnow, now)
        f = D.FORMS[p["form"]]
        S = g.stats()
        need = P.exp_to_next(p["lvl"])
        pct = int(p["exp"] / need * 100) if need else 0
        self._modbox(cv, x, y, w, h, 2, "LEVEL", right=f"{G1}GEN{RST} {G4}{g.s['family'].get('gen', 1)}{RST}")
        ix, iy, iw, ih = x + 2, y + 1, w - 4, h - 2
        rows = []
        if ih >= 7:
            lv = f"{p['lvl']:>2}".replace(" ", "_")
            flash = g.fx.get("levelup", 0) > gnow and int(now * 6) % 2
            seg = seg_lines(lv, P3["white"] if flash else P3["lime"], ghost=P3["navy1"])
            sw_ = seg_width(lv)
            info = [f"{G1}LV{RST}", f"{rgb(f['color'])}{B}{f['name']}{RST}", f"{G1}NEXT{RST} {LIME}{pct}%{RST}"]
            for i in range(3):
                rows.append(seg[i] + " " + clip(info[i], max(1, iw - sw_ - 1)))
        else:
            rows.append(f"{G1}LV{RST} {LIME}{B}{p['lvl']}{RST} {rgb(f['color'])}{f['name']}{RST}")
        ev = self._ease("exp", pct, now)
        rows.append(f"{G1}EXP{RST} {meter(ev, 100, max(3, iw - 9))} {G4}{pct:>3}%{RST}")
        nb = max(3, iw - 9)
        rows.append(f"{G1}HP{RST}  {segbar(p['hp'], S['maxhp'], nb, on=hp_hex(p['hp'], S['maxhp']))} {G4}{int(p['hp']):>4}{RST}")
        rows.append(f"{G1}MP{RST}  {segbar(p['mp'], S['maxmp'], nb, on=P3['navy4'])} {G4}{int(p['mp']):>4}{RST}")
        care, disc = int(p["care"]), int(p.get("discipline", 50))
        rows.append(f"{G1}돌봄{RST} {LIME}{knob(care)} {care:<3}{RST} {G1}훈육{RST} {NV4}{knob(disc)} {disc}{RST}")
        stats = [("ATK", S["atk"]), ("DEF", S["df"]), ("SPD", S["spd"]), ("INT", S["int"])]
        line = []
        for k, v in stats:
            piece = f"{G1}{k}{RST}{G4}{v}{RST}"
            if vlen(" ".join(line + [piece])) > iw:
                break
            line.append(piece)
        rows.append(" ".join(line))
        for i, r in enumerate(rows[:ih]):
            cv.ansi_clip(ix, iy + i, r, iw)

    def _hatch_panel(self, cv, x, y, w, h, gnow, now):
        g = self.g
        age = gnow - g.s["created"] + g.s["timers"].get("egg_bonus", 0)
        pct = max(0, min(100, int(age / 180 * 100)))
        self._modbox(cv, x, y, w, h, 2, "HATCH")
        ix, iy, iw, ih = x + 2, y + 1, w - 4, h - 2
        rows = []
        if ih >= 6:
            seg = seg_lines(f"{pct:>3}".replace(" ", "_") + "%", P3["lime"], ghost=P3["navy1"])
            rows.extend(seg)
        else:
            rows.append(f"{G1}HATCH{RST} {LIME}{B}{pct}%{RST}")
        rows.append(meter(self._ease("hatch", pct, now), 100, iw))
        if pct < 100:
            left = max(0, int(180 - age))
            rows.append(f"{G1}부화까지{RST} {G4}{left // 60}:{left % 60:02d}{RST}")
        else:
            wait = max(0, int(600 - age))
            on = int(now * 2) % 2
            rows.append((chip("WAIT", "black", "lime") if on else chip("WAIT", "lime", "navy2")) + f" {G4}첫 응답{RST}")
            rows.append(f"{G1}늦어도 {wait // 60 + 1}분 뒤{RST}")
        for i, r in enumerate(rows[:ih]):
            cv.ansi_clip(ix, iy + i, r, iw)

    def _egg_guide(self, cv, x0, y, W, h, gnow, side):
        """알 상태: 방 아래 안내문 (항목 단위 줄바꿈)"""
        g = self.g
        if h <= 0:
            return
        lines = []
        if not side:
            lines += wrap_sep(f"{G}{g.evolution_hint()}{RST}", W)
        tips = ["opencode가 쓰는 토큰이 이 아이의 밥이자 경험치가 돼요",
                "AI가 일하는 동안 자동으로 던전에 원정 가고, 응답이 오면 전리품을 들고 돌아와요",
                "밥·청소·놀이·잠을 챙겨주면 돌봄 점수가 오르고, 키운 방식대로 진화해요",
                "서브에이전트는 동료가, 도구 사용은 강화 재료가, 에러는 보스가 돼요"]
        self._anchor(x0 + title_end(3, "GUIDE"), y + len(lines), "guide")
        lines.append(sect(3, "GUIDE", W))
        for i, t in enumerate(tips):
            wl = wrap(t, max(8, W - 4))
            for j, ln in enumerate(wl):
                lines.append((f"{LIME}{i + 1:02d}{RST}  " if j == 0 else "    ") + f"{G}{ln}{RST}")
        for i, ln in enumerate(lines[:h]):
            cv.ansi_clip(x0, y + i, ln, W)

    def _log_panel(self, cv, x0, y, W, h, num=3, title="LOG"):
        """── 03 LOG ● ───── + 최근 기록 (오래된 줄일수록 흐리게). LED = 1.5초 안에 새 줄"""
        last = self.g.log[-1] if self.g.log else None
        now = time.time()
        if last is not self._log_mark[0]:
            self._log_mark = (last, now if self._log_mark[0] is not None else 0.0)
        cv.ansi(x0, y, sect(num, title, W, led=(now - self._log_mark[1] < 1.5)))
        logs = list(self.g.log)[-(h - 1):] if h > 1 else []
        n = len(logs)
        for i, (ts, t) in enumerate(logs):
            age = n - 1 - i
            tc = G4 if age == 0 else G if age <= 2 else G2
            cv.ansi_clip(x0, y + 1 + i, f"{NV3}{ts[:5]}{RST} {tc}{t}{RST}", W)

    def _room(self, cv, x0, y0, W, h, gnow):
        g, p = self.g, self.g.p
        now = time.time()
        dark = p["sleeping"]
        egg = g.is_egg()
        clock = time.strftime("%H:%M", time.localtime(gnow))
        right = (f"{BG_NAVY1}{NV4} 소등 {RST}" if dark else f"{self._vu(now)} {G}{clock}{RST}")
        foot_l = "알" if egg else f"AGE {P.fmt_age(g.age())}"
        foot_r = "" if egg else f"{p['kb']:.1f}KB"
        self._modbox(cv, x0, y0, W, h, 1, "ROOM", right=right, foot_l=foot_l, foot_r=foot_r,
                     color=(G0 if dark else NV2), on=not dark)
        inner_w = W - 2
        floor_y = y0 + h - 2
        # 점 격자 (TE 화면 배경 느낌)
        if not dark:
            for yy in range(y0 + 2, floor_y, 2):
                for xx in range(x0 + 4, x0 + W - 3, 6):
                    cv.text(xx, yy, "·", NV1)
        # 꾸미기 (최대 4): 왼쪽 위, 오른쪽 위, 왼쪽 바닥, 오른쪽 바닥
        placed = g.s["inv"]["placed"]
        spots = [(x0 + 2, y0 + 1), (x0 + W - 9, y0 + 1), (x0 + 2, floor_y - 1), (x0 + W - 9, floor_y - 1)]
        for iid, (sx, sy) in zip(placed, spots):
            art = D.DECO_ART.get(iid, [])
            colr = rarity_color(iid) if not dark else G0
            if iid == "led" and not dark:
                colr = LIME if int(now * 2) % 2 else NV4
            for i, ln in enumerate(art):
                if y0 < sy + i < y0 + h - 1:
                    cv.text(sx, sy + i, ln, colr)
        # 시즌 장식 (벽 가운데 위)
        se = P.current_season(g.now())
        if se and se.get("deco"):
            dx = x0 + (W - max(vlen(ln) for ln in se["deco"])) // 2
            for i, ln in enumerate(se["deco"]):
                if y0 < y0 + 1 + i < floor_y - 3:
                    cv.text(dx, y0 + 1 + i, ln, (LIME3 if not dark else G0))
        # 바닥 버그
        bs = g.fx.get("bug_spawn")
        for i in range(p["bugs"]):
            bx = x0 + 2 + (i * 7 + 3) % max(1, inner_w - 4)
            cv.text(bx, floor_y, "ж", WH if int(now * 2 + i) % 2 else G)
            if bs and bs[0] == i and bs[1] > gnow:
                cv.text(max(x0 + 1, bx - 1), floor_y - 1, "뿅!", WH + B)
        # 밥그릇 (오른쪽 바닥 꾸미기와 겹치지 않게)
        cv.text(x0 + W - 15 if len(placed) >= 4 else x0 + 1 + inner_w - 4, floor_y, "\\_/", G1)
        # 펫 위치 (산책)
        art, color = face_sprite(g, gnow)
        sw = max(vlen(ln) for ln in art)
        lo, hi = x0 + 1, x0 + 1 + max(0, inner_w - sw)
        if self.pet_x is None or not (lo <= self.pet_x <= hi):
            self.pet_x = (lo + hi) // 2
        typing = bool(g.busy_roots) and not g.expd and not p["sleeping"] and not egg
        busy_face = p["sleeping"] or g.fx.get("eat", 0) > gnow or egg or g.expd or typing
        if typing:
            self.pet_x = max(lo, min(hi, x0 + 8))
        if not busy_face and now >= self.next_step:
            self.next_step = now + 0.7
            r = random.random()
            if r < 0.35:
                self.pet_dir = -self.pet_dir if random.random() < 0.3 else self.pet_dir
                self.pet_x = max(lo, min(hi, self.pet_x + self.pet_dir * 2))
        py = floor_y - 3
        if g.expd:
            self._tape(cv, x0, y0, W, h, now)
        else:
            pc = rgb(color) if not dark else NV2
            bounce = 0
            if g.fx.get("joy", 0) > gnow and not p["sleeping"]:
                bounce = -1 if int(now * 6) % 2 else 0
            elif not p["sleeping"] and not egg and int(now * 2) % 4 == 0 and p["mood"] >= 60:
                bounce = -1
            for i, ln in enumerate(art):
                yy = py + i + bounce
                if y0 < yy < y0 + h - 1:
                    cv.text(self.pet_x, yy, ln, pc)
            # 효과
            fx_y = max(y0 + 1, py - 1 + bounce)
            if p["sleeping"]:
                zz = ["z", "Z", "z"][int(now * 1.5) % 3]
                cv.text(min(x0 + W - 3, self.pet_x + sw), fx_y, zz + " " + ("Z" if int(now) % 2 else "z"), NV4)
            if g.fx.get("eat", 0) > gnow:
                iid = g.fx.get("eat_item", ("", 0))[0]
                if iid in D.ITEMS:
                    cv.ansi(min(x0 + W - 12, self.pet_x + sw), py + 1, f"{G4}[{D.ITEMS[iid]['name']}]{RST}")
            if g.fx.get("munch", 0) > gnow and not p["sleeping"]:
                cv.text(max(x0 + 1, self.pet_x - 4), py + 1, "냠!" if int(now * 4) % 2 else "냠 ", LIME3)
            if g.fx.get("love", 0) > gnow:
                cv.text(self.pet_x + sw // 2 - 1, fx_y, "<3", LIME)
            if g.fx.get("levelup", 0) > gnow:
                lab = " LEVEL UP "
                st = (BG_LIME + BLACK + B) if int(now * 4) % 2 else (BG_NAVY2 + LIME + B)
                cv.text(max(x0 + 1, min(x0 + W - 1 - len(lab), self.pet_x + sw // 2 - len(lab) // 2)), fx_y, lab, st)
            if g.fx.get("clean", 0) > gnow:
                t = 1 - (g.fx["clean"] - gnow) / 1.6
                bx = x0 + 1 + int(t * (inner_w - 4))
                cv.text(bx, floor_y, "≈≈>", NV4)
            if g.anxious_until > gnow and not p["sleeping"]:
                cv.text(self.pet_x + sw, py, "!?", WH)
            if g.fx.get("joy", 0) > gnow and not p["sleeping"]:
                cv.text(self.pet_x + sw // 2, fx_y, "!", LIME + B)
            call = g.s.get("call")
            if call and call["kind"] == "tantrum" and not p["sleeping"]:
                cv.text(min(x0 + W - 9, self.pet_x + sw), py + 2, "버둥버둥" if int(now * 3) % 2 else "  버둥버둥", NV4)
            if g.fx.get("scold", 0) > gnow:
                cv.text(min(x0 + W - 7, self.pet_x + sw), py, "(훌쩍)", NV4)
            if g.fx.get("burp", 0) > gnow:
                cv.text(max(x0 + 1, self.pet_x - 6), py, "꺼억~", LIME3 + B)
            if g.waits and not p["sleeping"]:
                w = next(iter(g.waits.values()))
                sign = " 결재 부탁! " if w["kind"] == "perm" else " 질문 왔어요! "
                sx = max(x0 + 1, min(x0 + W - 1 - vlen(sign), self.pet_x + sw // 2 - vlen(sign) // 2))
                st = (BG_LIME + BLACK + B) if int(now * 2) % 2 else (BG_NAVY2 + WH + B)
                cv.text(sx, max(y0 + 1, fx_y - 1), sign, st)
            if typing:
                lx = self.pet_x + sw + 1
                cv.text(lx, floor_y - 1, " ____ ", NV4)
                cv.text(lx, floor_y, "|____|", NV4)
                tk = ["타닥", "타닥타닥", "탁", "타다닥"][int(now * 3) % 4]
                cv.text(lx, floor_y - 2, tk, G1)
            # 놀러온 친구 펫
            vis = g.visitor
            if vis and vis["until"] > gnow:
                vf = D.FORMS.get(vis["form"], D.FORMS["bit"])
                vart = [ln.replace("{f}", vis.get("face", "^_^")) for ln in vf["art"][int(now * 2) % 2]]
                vx = min(x0 + W - 13, x0 + int(W * 0.6)) + (int(now) % 2)
                for i, ln in enumerate(vart):
                    if y0 < py + i < y0 + h - 1:
                        cv.text(vx, py + i, ln, rgb(vis.get("color", "#D4D6D8")))
                cv.text(vx + 2, max(y0 + 1, py - 1), vis["name"][:6], G1)
        # 동료(서브에이전트)가 방에 놀러옴
        if g.allies and not g.expd:
            ax = x0 + 2
            for a in list(g.allies.values())[:2]:
                for i, ln in enumerate(a["art"]):
                    cv.text(ax, floor_y - 1 + i - 1, ln, rgb(a["color"]))
                ax += 8

    def _tape(self, cv, x0, y0, W, h, now):
        """원정 중: 빈 방 가운데 테이프 릴 두 개가 돈다 (◐━━━━◑)"""
        g = self.g
        z = D.ZONES[g.expd["zone"]]
        span = max(8, min(24, W - 16))
        off = int(now * 8) % 4
        tape = "".join("━" if (i + off) % 4 else "─" for i in range(span))
        line = f"{LIME}({spinner(now, 6)}){RST}{NV3}{tape}{RST}{LIME}({spinner(now + 0.2, 6)}){RST}"
        cy = y0 + max(1, h // 2 - 1)
        cv.ansi(x0 + (W - vlen(line)) // 2, cy, line)
        msg = f"{G1}EXPEDITION{RST} {G4}{z['short']} B{g.expd['floor']}F{RST}"
        cv.ansi(x0 + (W - vlen(msg)) // 2, cy + 1, msg)

    # ------------------------------------------------------------ 모험
    def _draw_adv(self, cv, x0, y0, W, H, gnow):
        g = self.g
        if g.battle and g.battle.get("story") is not None:
            self._draw_story_battle(cv, x0, y0, W, H, gnow)
            return
        if g.battle and g.battle.get("raid"):
            self._draw_raid(cv, x0, y0, W, H, gnow)
            return
        if not g.expd:
            self._draw_zones(cv, x0, y0, W, H)
            return
        now = time.time()
        e = g.expd
        z = D.ZONES[e["zone"]]
        c = e["carry"]
        loot_n = sum(c["items"].values()) + sum(c["mats"].values()) + len(c["gear"])
        # 머리줄: [B7F] 지역 이름 ··· ENC 3/5 · LOOT 320G ◆4 · KO 6 [AUTO]
        chips = []
        if e["auto"]:
            chips.append(chip("AUTO", "black", "navy4"))
        if e["ret"]:
            chips.append(chip("귀환 대기", "black", "lime") if int(now * 2) % 2 else chip("귀환 대기", "lime", "navy2"))
        enc_txt = f"{min(e['enc'] + 1, e['enc_total'])}/{e['enc_total']}"
        if W >= 64:
            stat = (f"{G1}ENC{RST} {G4}{enc_txt}{RST}  {G1}LOOT{RST} {G4}{P.fmt_num(c['gold'])}G ◆{loot_n}{RST}  "
                    f"{G1}KO{RST} {G4}{c['kills']}{RST}")
        else:
            stat = f"{G4}{enc_txt}{RST} {G1}·{RST} {G4}{P.fmt_num(c['gold'])}G◆{loot_n}{RST} {G1}·{RST} {G4}KO{c['kills']}{RST}"
        head = f"{chip('B' + str(e['floor']) + 'F', 'black', 'lime')} {rgb(z['color'])}{B}{z['name']}{RST}"
        steps = " " + self._floor_steps(e["floor"], now)
        right = stat + ("  " + " ".join(chips) if chips else "")
        if vlen(head) + vlen(steps) + vlen(right) + 2 <= W:
            self._anchor(x0 + vlen(head) + vlen(steps), y0, "floor")
            head += steps
        if vlen(head) + vlen(right) + 2 <= W:
            cv.ansi(x0 + W - vlen(right), y0, right)
            cv.ansi_clip(x0, y0, head, W - vlen(right) - 2)
        else:
            cv.ansi_clip(x0, y0, head + "  " + right, W)
        # 무대 (이벤트 중 + 작은 창이면 무대를 줄여 선택지 공간 확보)
        event_mode = g.event is not None and not g.battle
        stage_h = 5 if (event_mode and H < 20) else 6
        sy = y0 + 1
        self._arena(cv, x0, sy, W, stage_h, gnow)
        self._anchor(x0 + title_end(1, "FIELD") - 3, sy, "field")
        y = sy + stage_h
        self._anchor(x0 + W - 1, y, "hp")
        y = self._hp_rows(cv, x0, y, W, gnow, event_mode)
        if g.event:
            self._anchor(x0 + title_end("EV", "EVENT", boxed=True), y, "event")
            ev = g.event
            body = len(wrap(ev["ev"]["text"], W - 4))
            need = 2 + body + (2 if ev.get("result") else len(ev["ev"]["options"]))
            eh = min(y0 + H - y, need)
            self._event_box(cv, x0, y, W, eh, gnow)
            y += eh
        if y0 + H - y >= 2:
            self._log_panel(cv, x0, y, W, y0 + H - y, 2, "LOG")
            self._anchor(x0 + title_end(2, "LOG", led=True), y, "log")

    def _hp_rows(self, cv, x0, y, W, gnow, event_mode=False):
        """펫 / 적 체력 줄 (LED 막대). 반환: 다음 y"""
        g, p = self.g, self.g.p
        S = g.stats()
        nb = max(6, min(20, (W - 34) // 2))
        pst = g.battle["pst"] if g.battle else {}
        pst_txt = " ".join(chip(STATUS_NAMES.get(k, k), "gray4", "navy1", False) for k in pst)
        name = clip(p["name"], 8)
        cv.ansi_clip(x0, y, f"{rgb(D.FORMS[p['form']]['color'])}{B}{pad(name, 8)}{RST} "
                            f"{G1}HP{RST} {segbar(p['hp'], S['maxhp'], nb, on=hp_hex(p['hp'], S['maxhp']))} "
                            f"{G4}{int(max(0, p['hp'])):>4}{RST}{G1}/{S['maxhp']}{RST}  "
                            f"{G1}MP{RST} {segbar(p['mp'], S['maxmp'], max(4, nb // 2), on=P3['navy4'])} {G4}{int(p['mp'])}{RST} {pst_txt}", W)
        y += 1
        if g.battle:
            m = g.battle["mon"]
            boss = m["rank"] == "boss"
            mst = " ".join(chip(STATUS_NAMES.get(k, k), "gray4", "navy1", False) for k in m["st"])
            if g.battle.get("raid"):
                tag = chip("RAID", "black", "white")
            elif g.battle.get("story") is not None:
                tag = chip(f"CH{g.battle['story'] + 1:02d}", "black", "lime")
                boss = True
            else:
                tag = {"boss": chip("BOSS", "black", "white"), "mini": chip("MINI", "black", "gray")}.get(m["rank"], "")
            lv = f" {G1}LV{RST}{G4}{m['level']}{RST}" if W >= 60 and not g.battle.get("raid") else ""
            label = (tag + " " if tag else "") + f"{WH if boss else G4}{m['name']}{RST}{lv}"
            hpv = f"{G4}{P.fmt_num(max(0, int(m['hp'])))}{RST}{G1}/{P.fmt_num(m['maxhp'])}{RST}"
            bar_ = segbar(max(0, m["hp"]), m["maxhp"], nb, on=P3["white"] if boss else P3["gray4"])
            cv.ansi_clip(x0, y, f"{label} {bar_} {hpv} {mst}", W)
            y += 1
        elif not event_mode:
            if g.expd and g.expd["state"] == "walk":
                cv.ansi_clip(x0, y, f"{G1}다음 방으로 이동 중{RST} {NV4}{'›' * (1 + int(time.time() * 3) % 3)}{RST}", W)
            y += 1
        return y

    def _floor_steps(self, floor, now):
        """B1~B10 을 시퀀서 스텝처럼: 지난 층 라임, 지금 층 깜빡, 보스층(5·10)은 ◆"""
        out = []
        for f in range(1, D.FLOORS_PER_ZONE + 1):
            ch = "◆" if f in (D.MINI_FLOOR, D.BOSS_FLOOR) else "▮"
            if f < floor:
                out.append(f"{LIME}{ch}")
            elif f == floor:
                out.append(f"{WH if int(now * 3) % 2 else LIME3}{ch}")
            else:
                out.append(f"{NV2}{ch}")
        return "".join(out) + RST

    def _arena(self, cv, x0, y0, W, h, gnow):
        g, now = self.g, time.time()
        e = g.expd
        z = D.ZONES[e["zone"]] if e else None
        if not z and g.battle and g.battle.get("story") is not None:
            zid = D.CHAPTERS[g.battle["story"]]["zone"]
            z = next((zz for zz in D.ZONES if zz["id"] == zid), None)      # 챕터 보스전 무대 = 그 챕터의 지역
        ground_y = y0 + h - 1
        pat = z["ground"] if z else "=#=-=#=-"
        # 이벤트 중엔 걷지 않는다 (작은 창에서 스프라이트가 머리줄을 덮지 않게)
        walking = bool(e) and not g.battle and not g.event and e["state"] == "walk"
        shift = int(now * 8) if walking else 0
        gl = "".join(pat[(i + shift) % len(pat)] for i in range(W))
        cv.text(x0, ground_y, gl, rgb(z["color"]) if z else NV2)
        cv.ansi(x0, y0, module(1, "FIELD"))
        # 펫
        art, color = face_sprite(g, gnow)
        px = x0 + 2
        hurt = g.fx.get("hurt", 0) > gnow
        bob = -1 if walking and int(now * 4) % 2 else 0
        for i, ln in enumerate(art):
            yy = ground_y - 4 + i + bob
            if y0 <= yy < ground_y:
                cv.text(px, yy, ln, WH if hurt and int(now * 10) % 2 else rgb(color))
        # 동료
        ax = px + 12
        helpers = list(g.allies.values())
        if g.battle and g.battle.get("pair", 0) > 0:
            helpers.append(dict(name="짝꿍", color=P3["gray4"], art=[r" (^^)", r" /||\ "]))
        for a in helpers[:3]:
            if ax + 6 >= x0 + W - 14:
                break
            for i, ln in enumerate(a["art"]):
                cv.text(ax, ground_y - 2 + i, ln, rgb(a["color"]))
            cv.text(ax, ground_y - 3, a["name"].split()[-1][:3], G1)
            ax += 7
        # 적
        if g.battle:
            m = g.battle["mon"]
            mw = max(vlen(ln) for ln in m["art"])
            mx = x0 + W - mw - 2
            hit = g.fx.get("mon_hit", 0) > gnow or g.fx.get("phase2", 0) > gnow
            shake = 1 if hit and int(now * 20) % 2 else 0
            over = g.battle.get("over")
            mc = WH if hit else (G4 if m["rank"] == "boss" else G if m["rank"] == "mini" else G2)
            if over == "win":
                mc = G0
            for i, ln in enumerate(m["art"]):
                cv.text(mx + shake, ground_y - 4 + i, ln, mc)
            sk = g.fx.get("skill")
            if sk and sk[1] > gnow:
                label = f" {sk[0]} "
                cv.text(max(x0, x0 + (W - vlen(label)) // 2), y0, label, BG_LIME + BLACK + B)
        elif g.event:
            cv.text(x0 + W - 8, ground_y - 2, " ? ", (BG_LIME + BLACK + B) if int(now * 2) % 2 else (BG_NAVY2 + LIME + B))
        # 데미지 팝업 (떠오르며 사라짐)
        for text, side, colr, until, born in g.pops:
            age = gnow - born
            dy = int(age * 2)
            tx = x0 + W - 14 if side == "mon" else px + 1
            ty = ground_y - 5 - dy
            if y0 <= ty < ground_y:
                cv.text(tx, ty, text, rgb(colr) + B)

    def _event_box(self, cv, x0, y, W, h, gnow):
        g = self.g
        ev = g.event
        if h < 3:
            return
        left = max(0, int(ev["deadline"] - gnow))
        foot = "" if ev.get("result") else f"AUTO {left}s"
        self._modbox(cv, x0, y, W, h, "EV", "EVENT", foot_r=foot, color=NV3)
        lines = wrap(ev["ev"]["text"], W - 4)
        yy = y + 1
        # 선택지 줄을 먼저 확보하고 남는 줄에 본문 (작은 창에서 [2] 가 잘리지 않게)
        room = h - 2 - (1 if ev.get("result") else len(ev["ev"]["options"]))
        for ln in lines[: max(0, room)]:
            cv.ansi(x0 + 2, yy, f"{G4}{ln}{RST}")
            yy += 1
        if ev.get("result"):
            label, msg, auto = ev["result"]
            head = chip("AUTO" if auto else "OK", "black", "lime")
            for ln in wrap(f"{head} {LIME}{label}{RST} {G1}→{RST} {G4}{msg}{RST}", W - 4)[: max(1, y + h - 1 - yy)]:
                cv.ansi(x0 + 2, yy, ln)
                yy += 1
            return
        for i, (label, _) in enumerate(ev["ev"]["options"]):
            if yy >= y + h - 1:
                break
            cv.ansi_clip(x0 + 2, yy, f"{keycap(str(i + 1))} {G4}{label}{RST}", W - 4)
            yy += 1

    def _draw_zones(self, cv, x0, y0, W, H):
        g = self.g
        ok, why = g.can_depart()
        head = f"{NV2}──{RST} {module(1, 'DUNGEON')} "
        state = chip("READY", "black", "lime") if ok else f"{WH}{why}{RST}"
        fill = max(1, W - vlen(head) - vlen(state) - 2)
        cv.ansi_clip(x0, y0, head + f"{NV2}{'─' * fill}{RST} " + state, W)
        zi = g.zones_info()
        c = min(self.cur.get("zone", 0), len(zi))
        wide = W >= 60
        nw = max(vlen(i["z"]["name"]) for i in zi)
        nw = min(nw, W - (34 if wide else 18))
        rows = []
        for i, info in enumerate(zi):
            z = info["z"]
            if info["cleared"]:
                mark = f"{LIME}☼{RST}"
            elif info["unlocked"]:
                mark = f"{LIME3}●{RST}"
            else:
                mark = f"{G1}×{RST}"
            name = f"{rgb(z['color'])}{pad(z['name'], nw)}{RST}" if info["unlocked"] else f"{G1}{pad(z['name'], nw)}{RST}"
            best = info["best"]
            steps = segbar(best, D.FLOORS_PER_ZONE, 10 if wide else 5,
                           on=(P3["lime"] if info["unlocked"] else P3["gray1"]))
            row = f"{NV4}{i + 1:02d}{RST} {mark} {name} "
            if not info["released"]:
                # 아직 공개 전: 스토리 챕터가 열리는 날
                when = self._release_text(i).split(" · ")[0] if self._release_text(i) else "이전 챕터 클리어 후"
                row += f"{G1}CH{i + 1:02d} · {when}{RST}" if wide else f"{G1}CH{i + 1:02d}{RST}"
                rows.append(row)
                continue
            if wide:
                row += f"{G1}LV{RST}{G4}{z['lvl']:<3}{RST}{steps} {G1}B{best}F{RST}" if best else f"{G1}LV{RST}{G4}{z['lvl']:<3}{RST}{steps}"
                if info["cleared"]:
                    row += f" {LIME}CLEAR{RST}"
            else:
                row += steps
            rows.append(row)
        ri = g.raid_info() if not g.is_egg() else None
        if ri:
            pct = 100 * ri["dealt"] / max(1, ri["hp"])
            state = (f"{LIME}{B}격파!{RST}" if ri["cleared"] else
                     f"{G4}{pct:.0f}%{RST} {G1}· 오늘 {ri['tries_left']}/{D.RAID['per_day']}{RST}")
            rows.append(f"{WH}{B}RD{RST} {WH}†{RST} {chip('WEEKLY RAID', 'black', 'white')} {G4}{D.MONSTERS[ri['boss']]['name']}{RST} {state}")
        else:
            rows.append(f"{G1}RD † 주간 레이드 (부화하면 참가){RST}")
        list_h = min(len(rows), max(3, H - 5))
        self._list(cv, x0, y0 + 1, W, list_h, rows, c)
        self._anchor(x0 + title_end(1, "DUNGEON"), y0, "dungeon")
        y = y0 + 1 + list_h
        if c == len(zi):
            self._raid_panel(cv, x0, y, W, y0 + H - 1 - y, ri)
            self._anchor(x0 + title_end(2, "RAID"), y, "raid")
        elif y < y0 + H - 1:
            info = zi[c]
            z = info["z"]
            head = f"{NV2}──{RST} {module(2, 'INFO')} "
            lines = [head + f"{NV2}{'─' * max(0, W - vlen(head))}{RST}"]
            lines += wrap(f"{G}{z['desc']}{RST}", W)
            if not info["released"]:
                rt = self._release_text(c)
                lines.append(f"{chip('LOCK', 'black', 'white')} {WH}스토리 CH{c + 1:02d} 「{D.CHAPTERS[c]['title']}」이 열리면 공개{RST}"
                             + (f" {G1}· {rt}{RST}" if rt else ""))
            elif not info["unlocked"]:
                need = [] if info["prev_ok"] else ["이전 지역 보스 격파"]
                if g.p["lvl"] < z["lvl"]:
                    need.append(f"Lv.{z['lvl']}")
                lines.append(f"{chip('LOCK', 'black', 'white')} {WH}{' + '.join(need)} 필요{RST}")
            else:
                seen = g.s["seen"]
                boss = D.MONSTERS[z["boss"]]["name"] if seen.get(z["boss"]) else "???"
                lines.append(f"{G1}B5F{RST} {G}중보스{RST}  {G1}B10F{RST} {G}보스{RST} {WH}{boss}{RST}")
            fb = g.s["prog"].get("boss_fail", {}).get(z["id"])
            boss_lv = z["base"] + D.BOSS_FLOOR - 1 + 2
            if not info["cleared"] and info["unlocked"]:
                need = max(boss_lv - 4, fb + 2 if fb else 0)
                lines.append(f"{G1}보스 LV{boss_lv} · 자동 원정은 LV{need}부터 보스 도전"
                             + (f" (패배 기록 LV{fb})" if fb else "") + f"{RST}")
            map_at = None
            if info["unlocked"] and y0 + H - 1 - y - len(lines) >= 4:
                map_at = len(lines)
                lines += self._zone_map(z, info["best"], W)
            self._anchor(x0 + title_end(2, "INFO"), y, "info")
            if map_at is not None and map_at < y0 + H - 1 - y:
                self._anchor(x0 + title_end(3, "MAP"), y + map_at, "map")
            for ln in lines[: y0 + H - 1 - y]:
                cv.ansi_clip(x0, y, ln, W)
                y += 1
        st = g.s["settings"]

        def sw(on):
            return chip("ON", "black", "lime") if on else chip("OFF", "gray4", "navy1")
        cv.ansi_clip(x0, y0 + H - 1, f"{G1}AUTO 원정{RST} {sw(st['auto_exp'])} {G1}(AI 일하면 출발 · 응답 오면 귀환){RST}  "
                                     f"{G1}AUTO 전투{RST} {sw(st['auto_battle'])}", W)
        self._anchor(x0 + W - 1, y0 + H - 1, "auto")

    def _zone_map(self, z, best, W):
        """03 MAP: B1~B10 층 지도 (시퀀서 스텝처럼) + 이 지역 몬스터 명단"""
        g = self.g
        head = f"{NV2}──{RST} {module(3, 'MAP')} "
        out = [head + f"{NV2}{'─' * max(0, W - vlen(head))}{RST}"]
        n = D.FLOORS_PER_ZONE
        link = 3 if W >= 52 else 1
        cells, xs, x = [], [], 3
        for f in range(1, n + 1):
            ch = "◆" if f in (D.MINI_FLOOR, D.BOSS_FLOOR) else "▮"
            col = LIME if f <= best else NV3 if f == best + 1 else NV2
            cells.append(f"{col}{ch}{RST}")
            xs.append(x)
            x += 1 + link
        out.append(f"{G1}B1{RST} " + f"{NV2}{'─' * link}{RST}".join(cells) + f" {G1}B{n}{RST}")
        marks = [" "] * (xs[-1] + 5)
        for f, lab in ((D.MINI_FLOOR, "MINI"), (D.BOSS_FLOOR, "BOSS")):
            px = xs[f - 1] - 1
            for i, ch in enumerate(lab):
                if 0 <= px + i < len(marks):
                    marks[px + i] = ch
        out.append(f"{G1}{''.join(marks).rstrip()}{RST}")
        seen = g.s["seen"]
        names = [D.MONSTERS[m]["name"] if seen.get(m) else "???" for m in z["normals"]]
        mini = D.MONSTERS[z["mini"]]["name"] if seen.get(z["mini"]) else "???"
        out += wrap_sep(f"{G}{' · '.join(names)}{RST} {G1}· 중보스{RST} {G4}{mini}{RST}", W)
        return out

    def _raid_panel(self, cv, x0, y, W, h, ri):
        """모험 목록에서 '주간 레이드' 줄을 골랐을 때 아래 설명"""
        if h <= 0:
            return
        g = self.g
        head = f"{NV2}──{RST} {module(2, 'RAID')} "
        lines = [head + f"{NV2}{'─' * max(0, W - vlen(head))}{RST}"]
        if not ri:
            lines.append(f"{G}알이 부화하면 주간 레이드에 참가할 수 있어요.{RST}")
        else:
            m = D.MONSTERS[ri["boss"]]
            lines += wrap(f"{G}{m['desc']}{RST}", W)
            left = max(0, ri["hp"] - ri["dealt"])
            lines.append(f"{G1}공동 체력{RST} {segbar(left, ri['hp'], max(8, min(24, W - 34)), on=P3['white'])} "
                         f"{G4}{P.fmt_num(left)}{RST}{G1}/{P.fmt_num(ri['hp'])}{RST}")
            lines.append(f"{G1}모든 인스턴스 탭의 펫이 함께 때려요 · 한 판 {D.RAID['rounds']}라운드 · 하루 {D.RAID['per_day']}번 · "
                         f"체력 {D.RAID['energy']} 소모 · 기절 페널티 없음{RST}")
            if ri["rows"]:
                top = "  ".join(f"{NV4}{i + 1:02d}{RST} {G4}{r['name']}{RST} {G1}{P.fmt_num(r['dmg'])}{RST}"
                                for i, r in enumerate(ri["rows"][:3]))
                lines.append(top)
            lines.append(f"{G1}내 기여{RST} {LIME}{B}{P.fmt_num(ri['mine'])}{RST}" + (f" {G1}({ri['rank']}위){RST}" if ri.get("rank") else "")
                         + (f" {chip('보상 받음', 'black', 'lime3')}" if ri.get("claimed") else ""))
            ok, why = g.can_raid()
            lines.append(f"{keycap('↵')} {G1}/{RST} {keycap('W', '출격!')}" if ok else f"{WH}{why}{RST}")
        for ln in lines[:h]:
            cv.ansi_clip(x0, y, ln, W)
            y += 1

    def _draw_raid(self, cv, x0, y0, W, H, gnow):
        g = self.g
        now = time.time()
        b = g.battle
        m = b["mon"]
        dealt = int(max(0, b["start_hp"] - max(0, m["hp"])))
        rnd = min(b["round"] + 1, b["rounds_max"])
        head = (f"{chip('WEEKLY RAID', 'black', 'white')} {WH}{B}{m['name']}{RST}  "
                f"{G1}ROUND{RST} {G4}{rnd}/{b['rounds_max']}{RST}  {G1}이번 출격 피해{RST} {LIME}{B}{P.fmt_num(dealt)}{RST}")
        cv.ansi_clip(x0, y0, head, W)
        stage_h = 6
        self._arena(cv, x0, y0 + 1, W, stage_h, gnow)
        # 무대 가운데 위: 세그먼트 라운드 표시 (06 /12)
        if W >= 56:
            rs = f"{rnd:02d}"
            seg = seg_lines(rs, P3["white"] if int(now * 2) % 2 and b["rounds_max"] - rnd <= 2 else P3["lime"], ghost=P3["navy1"])
            sx = x0 + (W - seg_width(rs) - 4) // 2
            for i, ln in enumerate(seg):          # 무대 1~3번째 줄 (0번째 줄은 스킬 이름 자리)
                cv.ansi(sx, y0 + 2 + i, ln)
            cv.ansi(sx + seg_width(rs), y0 + 4, f"{G1}/{b['rounds_max']}{RST}")
            self._anchor(sx - 2, y0 + 3, "round")
        self._anchor(x0 + title_end(1, "FIELD") - 3, y0 + 1, "field")
        y = y0 + 1 + stage_h
        self._anchor(x0 + W - 1, y, "hp")
        y = self._hp_rows(cv, x0, y, W, gnow)
        if y0 + H - y >= 2:
            self._log_panel(cv, x0, y, W, y0 + H - y, 2, "LOG")
            self._anchor(x0 + title_end(2, "LOG", led=True), y, "log")

    # ------------------------------------------------------------ 스토리
    def _release_text(self, j):
        """챕터(=지역) j 공개일: '10/26(월) 공개 · D-5'. 이미 공개됐으면 ''"""
        d = self.g.story_release_date(j)
        if not d:
            return ""
        today = datetime.date.fromtimestamp(self.g.now())
        left = (d - today).days
        if left <= 0 or j < self.g.story_released_n():
            return ""
        return f"{d.month}/{d.day}({'월화수목금토일'[d.weekday()]}) 공개 · D-{left}"

    def _story_chip(self, st, i, now):
        c = D.CHAPTERS[i]
        blink = int(now * 2) % 2
        if c["id"] in st["cleared"]:
            return chip("CLEAR", "black", "lime3")
        if i > st["ch"]:
            return chip("LOCK", "gray4", "navy1", False)
        if not self.g.story_seen(i, "intro"):
            return chip("NEW", "black", "lime") if blink else chip("NEW", "lime", "navy2")
        if st["phase"] == "boss":
            return chip("BOSS", "black", "white") if blink else chip("BOSS", "white", "navy2")
        return chip("PLAY", "black", "navy4")

    def _shard_strip(self, st, now, n=None):
        """커밋 조각 12칸 LED: 모은 조각 라임 · 지금 챕터 깜빡 · 나머지 네이비"""
        out = []
        for k, c in enumerate(D.CHAPTERS):
            if c["id"] in st["cleared"]:
                out.append(f"{LIME}▮")
            elif k == st["ch"] and st["phase"] in ("play", "boss"):
                out.append(f"{WH if int(now * 2) % 2 else LIME1}▮")
            else:
                out.append(f"{NV2}▮")
        return "".join(out) + RST

    def _draw_story(self, cv, x0, y0, W, H, gnow):
        """스토리 = 01 CHAPTER(줄거리) + 02 SHARDS(커밋 조각) + 03 MISSIONS + 04 NEXT + 05 LOG"""
        g = self.g
        if g.battle and g.battle.get("story") is not None:
            self._draw_story_battle(cv, x0, y0, W, H, gnow)
            return
        st = g.story()
        now = time.time()
        n = len(D.CHAPTERS)
        head_l = f"{chip('S' + str(D.STORY['season']), 'black', 'lime')} {WH}{B}{D.STORY['title']}{RST}"
        if W >= 64:
            head_l += f" {G1}{D.STORY['en']}{RST}"
        if not st:
            cv.ansi_clip(x0, y0, head_l, W)
            lines = [sect(1, "CHAPTER", W),
                     f"{G}알이 깨면 시즌 1 「{D.STORY['title']}」이 시작돼요.{RST}",
                     f"{G1}어느 월요일 아침, 세상의 모든 빌드가 빨갛게 물들었다…{RST}",
                     f"{G1}챕터 12개 · 챕터마다 새 지역 · 일주일에 하나씩 열려요{RST}"]
            for k, ln in enumerate(lines[: max(0, H - 1)]):
                cv.ansi_clip(x0, y0 + 1 + k, ln, W)
            self._anchor(x0 + title_end(1, "CHAPTER"), y0 + 1, "chapter")
            return
        i = self._story_idx()
        c = D.CHAPTERS[i]
        cur = st["ch"]
        cleared = c["id"] in st["cleared"]
        future = i > cur
        # 머리줄: S1 초록불을 찾아서 ········ ‹ 07/12 ›
        pager = f"{G1}‹{RST} {LIME}{B}{i + 1:02d}{RST}{G1}/{n} ›{RST}"
        cv.ansi(x0 + W - vlen(pager), y0, pager)
        cv.ansi_clip(x0, y0, head_l, W - vlen(pager) - 1)
        self._anchor(x0 + W - vlen(pager) - 1, y0, "pages")
        y, end = y0 + 1, y0 + H
        side = W >= 66 and H >= 17
        sw = 22 if side else 0
        # ---- 01 CHAPTER (+ 02 SHARDS)
        box_h = 6 if H >= 17 else 5 if H >= 14 else 4
        bw = W - sw
        self._modbox(cv, x0, y, bw, box_h, 1, "CHAPTER", right=self._story_chip(st, i, now))
        self._anchor(x0 + title_end(1, "CHAPTER", boxed=True), y, "chapter")
        iw = bw - 4
        body = [f"{LIME}{B}CH{i + 1:02d}{RST} {WH}{B}{c['title']}{RST}" + (f" {G1}{c['en']}{RST}" if vlen(c['title']) + vlen(c['en']) + 7 <= iw else "")]
        if future:
            rt = self._release_text(i)
            body += [f"{G}{ln}{RST}" for ln in wrap_words(c["teaser"], iw)]
            cta = (f"{chip('LOCK', 'gray4', 'navy1', False)} {G4}{rt}{RST}" if rt else
                   f"{chip('LOCK', 'gray4', 'navy1', False)} {G4}CH{cur + 1:02d}를 끝내면 열려요{RST}")
        else:
            body += [f"{G}{ln}{RST}" for ln in wrap_words(c["summary"], iw)]
            if cleared:
                want = st.get("pending") == i or not g.story_seen(i, "outro")
                cta = (f"{keycap('↵', on=want and int(now * 2) % 2)} {LIME if want else G}{'에필로그 보기' if want else '다시 보기'}{RST}"
                       f"  {G1}조각 #{i + 1}{RST} {G4}{c['hash']}{RST}")
            elif not g.story_seen(i, "intro"):
                cta = f"{keycap('↵', on=int(now * 2) % 2)} {LIME}{B}프롤로그 보기{RST}"
            else:
                cta = f"{keycap('↵')} {G}대화 다시 보기{RST}"
                if st["phase"] == "boss":
                    cta += f"  {keycap('B', '보스 도전!', color=P3['lime'])}"
        inner = box_h - 2
        body = body[: max(1, inner - 1)]
        for k, ln in enumerate(body):
            cv.ansi_clip(x0 + 2, y + 1 + k, ln, iw)
        cv.ansi_clip(x0 + 2, y + box_h - 2, cta, iw)
        if side:
            self._shards_box(cv, x0 + bw + 1, y, sw - 1, box_h, st, now)
            self._anchor(x0 + bw + 1 + title_end(2, "SHARDS", boxed=True), y, "shards")
        y += box_h
        if not side and y < end:
            cv.ansi_clip(x0, y, f"{G1}SHARDS{RST} {self._shard_strip(st, now)} {G4}{len(st['cleared']):02d}{RST}{G1}/{n}{RST}", W)
            self._anchor(x0 + 6, y, "shards")
            y += 1
        # ---- 03 MISSIONS
        if y < end:
            y = self._story_missions(cv, x0, y, W, end - y, st, i, now)
        # ---- 04 NEXT
        if end - y >= 2:
            cv.ansi(x0, y, sect(4, "NEXT", W))
            self._anchor(x0 + title_end(4, "NEXT") + 1, y, "next")
            y += 1
            for ln in self._next_lines(st, W)[: max(0, min(2, end - y - 2) if end - y > 3 else 1)]:
                cv.ansi_clip(x0, y, ln, W)
                y += 1
        # ---- 05 LOG
        if end - y >= 2:
            log = st.get("log") or []
            fresh = bool(log) and g.now() - log[-1][0] < 3
            cv.ansi(x0, y, sect(5, "LOG", W, led=fresh))
            self._anchor(x0 + title_end(5, "LOG", led=True), y, "slog")
            rows = log[-(end - y - 1):]
            for k, (ts, t) in enumerate(rows):
                age = len(rows) - 1 - k
                tc = G4 if age == 0 else G if age <= 2 else G2
                stamp = time.strftime("%m/%d %H:%M", time.localtime(ts)) if W >= 56 else time.strftime("%H:%M", time.localtime(ts))
                cv.ansi_clip(x0, y + 1 + k, f"{NV3}{stamp}{RST} {tc}{t}{RST}", W)

    def _shards_box(self, cv, x, y, w, h, st, now):
        """02 SHARDS: 모은 커밋 조각 수 (세그먼트) + 12칸 LED + 마지막 해시"""
        k = len(st["cleared"])
        self._modbox(cv, x, y, w, h, 2, "SHARDS")
        ix, iy = x + 2, y + 1
        if h >= 6:
            for r, ln in enumerate(seg_lines(f"{k:02d}", P3["lime"], ghost=P3["navy1"])):
                cv.ansi(ix, iy + r, ln)
            cv.ansi(ix + seg_width(f"{k:02d}") + 1, iy + 2, f"{G1}/{len(D.CHAPTERS)}{RST}")
            iy += 3
        else:
            cv.ansi(ix, iy, f"{LIME}{B}{k:02d}{RST}{G1}/{len(D.CHAPTERS)}{RST}")
            iy += 1
        if iy < y + h - 1:
            cv.ansi(ix, iy, self._shard_strip(st, now))
            iy += 1
        last = next((c for c in reversed(D.CHAPTERS) if c["id"] in st["cleared"]), None)
        if iy < y + h - 1:
            cv.ansi_clip(ix, iy, f"{G1}#{RST}{G4}{last['hash']}{RST}" if last else f"{G1}#-------{RST}", w - 4)

    def _story_missions(self, cv, x0, y, W, h, st, i, now):
        """03 MISSIONS: √ 완료 · ▶ 진행 중 · ○ 남음 · ⋆/☼ 보너스 · ◆ 챕터 보스. 반환: 다음 y"""
        g = self.g
        c = D.CHAPTERS[i]
        ms = g.story_missions(i)
        req = [m for m in ms if not m["opt"]]
        done = sum(m["done"] for m in req)
        bonus = next((m for m in ms if m["opt"]), None)
        right = f"{G1}필수{RST} {G4}{done}/{len(req)}{RST}" + (f" {G1}보너스{RST} {LIME if bonus['done'] else G2}{'☼' if bonus['done'] else '⋆'}{RST}" if bonus else "")
        cv.ansi(x0, y, sect(3, "MISSIONS", W, right=right if W >= 44 else ""))
        self._anchor(x0 + title_end(3, "MISSIONS") + 1, y, "missions")
        y += 1
        end = y + h - 1
        if i > st["ch"]:
            if y < end:
                cv.ansi_clip(x0, y, f" {G1}??? 챕터가 열리면 미션이 공개돼요{RST}", W)
                y += 1
            return y
        nb = 10 if W >= 70 else 6 if W >= 54 else 0
        first_open = next((k for k, m in enumerate(ms) if not m["done"] and not m["opt"]), None)
        rows = []
        for k, m in enumerate(ms):
            if m["opt"]:
                mark = f"{LIME}☼{RST}" if m["done"] else f"{G2}⋆{RST}"
            elif m["done"]:
                mark = f"{LIME}√{RST}"
            elif k == first_open:
                mark = f"{WH}▶{RST}"
            else:
                mark = f"{G1}○{RST}"
            tc = G2 if m["done"] and not m["opt"] else G4 if not m["opt"] else G
            text = f"{mark} {NV4}{k + 1:02d}{RST} {tc}{m['text']}{RST}" + (f" {G1}(보너스){RST}" if m["opt"] and W >= 60 else "")
            tgt = m["target"]
            prog = min(m["prog"], tgt) if m["done"] else m["prog"]
            nums = f"{G4}{P.fmt_num(prog)}{RST}{G1}/{P.fmt_num(tgt)}{RST}"
            bar_ = segbar(prog, tgt, nb, on=P3["lime"] if not m["opt"] else P3["lime3"]) + " " if nb else ""
            rows.append((text, bar_ + nums))
        bd = c["boss"]
        bname = D.MONSTERS[bd["mid"]]["name"]
        if c["id"] in st["cleared"]:
            bstate = chip("격파", "black", "lime3")
        elif st["phase"] == "boss" and i == st["ch"]:
            ok, _ = g.can_story_boss()
            bstate = (chip("READY", "black", "lime") if int(now * 2) % 2 else chip("READY", "lime", "navy2")) if ok else chip("REST", "black", "white")
        else:
            bstate = chip("LOCK", "gray4", "navy1", False)
        rows.append((f"{WH}◆{RST} {NV4}{len(ms) + 1:02d}{RST} {WH}챕터 보스{RST} {G4}{bname}{RST} {G1}LV{bd['lvl']}{RST}", bstate))
        for text, rt in rows:
            if y >= end:
                break
            if vlen(text) + vlen(rt) + 2 <= W:
                cv.ansi(x0 + W - vlen(rt), y, rt)
                cv.ansi_clip(x0 + 1, y, text, W - vlen(rt) - 2)
            else:
                cv.ansi_clip(x0 + 1, y, text, W - 1)
            y += 1
        if st["phase"] == "boss" and i == st["ch"] and y < end:
            ok, why = g.can_story_boss()
            if not ok:
                cv.ansi_clip(x0 + 1, y, f"{G1}›{RST} {WH}{why}{RST}", W - 1)
                y += 1
            elif st.get("fails"):
                cv.ansi_clip(x0 + 1, y, f"{G1}› 패배 {st['fails']}번 (LV{st.get('fail_lvl', 0)}) · 레벨·장비를 올리면 쉬워져요{RST}", W - 1)
                y += 1
        return y

    def _next_lines(self, st, W):
        n = len(D.CHAPTERS)
        if st["phase"] == "end":
            return [f"{LIME}{B}시즌 {D.STORY['season']} 완결!{RST} {G}모든 빌드가 초록불. 다음 시즌을 기다려 주세요{RST}"]
        j = st["ch"] + 1
        if j >= n:
            return [f"{G}마지막 챕터예요. 보스를 쓰러뜨리면 시즌 {D.STORY['season']} 완결!{RST}"]
        nxt = D.CHAPTERS[j]
        rt = self._release_text(j)
        if st["phase"] == "wait":
            when = rt or "곧 열려요"
        else:
            when = (rt + " · 이번 챕터를 끝내면 시작") if rt else "이번 챕터를 끝내면 바로 시작"
        return [f"{NV4}CH{j + 1:02d}{RST} {G4}{B}{nxt['title']}{RST} {G1}·{RST} {LIME3}{when}{RST}",
                f"{G1}{nxt['teaser']} · 새 지역 {D.ZONES[j]['name']} (LV{D.ZONES[j]['lvl']}~){RST}"]

    def _draw_story_battle(self, cv, x0, y0, W, H, gnow):
        """챕터 보스전: 레이드 화면과 같은 틀 + 챕터 번호 · 페이즈"""
        g = self.g
        b = g.battle
        m = b["mon"]
        i = b["story"]
        head = f"{chip(f'CH{i + 1:02d} BOSS', 'black', 'lime')} {WH}{B}{m['name']}{RST}  {G1}ROUND{RST} {G4}{b['round'] + 1}{RST}"
        if b.get("phase2"):
            head += "  " + (chip("PHASE 2", "black", "white") if b.get("p2_done") else f"{G1}PHASE 1/2{RST}")
        cv.ansi_clip(x0, y0, head, W)
        stage_h = 6
        self._arena(cv, x0, y0 + 1, W, stage_h, gnow)
        self._anchor(x0 + title_end(1, "FIELD") - 3, y0 + 1, "field")
        y = y0 + 1 + stage_h
        self._anchor(x0 + W - 1, y, "hp")
        y = self._hp_rows(cv, x0, y, W, gnow)
        if y0 + H - y >= 2:
            self._log_panel(cv, x0, y, W, y0 + H - y, 2, "LOG")
            self._anchor(x0 + title_end(2, "LOG", led=True), y, "log")

    def _speaker(self, spk, gnow):
        """대사 주인 → (이름, 색, 그림 4줄)"""
        g = self.g
        if spk == "pet":
            art, color = face_sprite(g, gnow, face="happy") if not g.is_egg() else (D.FORMS["egg"]["art"][0], D.FORMS["egg"]["color"])
            return g.p["name"], color, list(art)
        if spk == "boss":
            sc = self.scene
            mid = D.CHAPTERS[sc["ch"]]["boss"]["mid"] if sc else None
            if mid:
                m = D.MONSTERS[mid]
                return m["name"], P3["white"], list(m["art"])
        npc = D.NPCS.get(spk)
        if npc:
            return npc["name"], npc["color"], list(npc["art"])
        return "", P3["gray"], []

    def _scene_other(self, idx):
        """무대 오른쪽에 설 상대: 지금 말하는 NPC/보스, 아니면 가장 최근(없으면 다음)에 말한 NPC/보스"""
        lines = self.scene["lines"]
        spk = lines[idx][0]
        if spk not in ("pet", "narr"):
            return spk
        for sp, _ in reversed(lines[:idx]):
            if sp not in ("pet", "narr"):
                return sp
        for sp, _ in lines[idx + 1:]:
            if sp not in ("pet", "narr"):
                return sp
        return None

    def _scene_stage(self, cv, x0, y0, W, h, gnow, idx):
        """대화 무대: 그 챕터 지역의 바닥 위에 펫(왼쪽)과 상대(오른쪽). 말하는 쪽만 불이 켜진다"""
        sc = self.scene
        now = time.time()
        c = D.CHAPTERS[sc["ch"]]
        z = next((zz for zz in D.ZONES if zz["id"] == c["zone"]), None)
        spk = sc["lines"][idx][0]
        gy = y0 + h - 1
        pat = z["ground"] if z else "=-=-"
        cv.text(x0, gy, "".join(pat[k % len(pat)] for k in range(W)), rgb(z["color"]) if z and spk != "narr" else NV2)
        typing = int((now - sc["t0"]) * SCENE_CPS) < len(self._scene_text(sc["lines"][idx]))

        def put(art, x, color, active):
            bob = -1 if active and typing and int(now * 6) % 2 else 0
            for r, ln in enumerate(art[-4:]):
                yy = gy - len(art[-4:]) + r + bob
                if y0 <= yy < gy:
                    cv.text(x, yy, ln, (rgb(color) + B) if active else NV3)
            if active and int(now * 2) % 2:
                mx = x + max(vlen(a) for a in art) // 2
                if y0 <= gy - 5 + bob:
                    cv.text(mx, gy - 5 + bob, "▼", LIME)
        name, color, art = self._speaker("pet", gnow)
        put(art, x0 + 3, color, spk == "pet")
        other = self._scene_other(idx)
        if other:
            name2, color2, art2 = self._speaker(other, gnow)
            if art2:
                ow = max(vlen(a) for a in art2)
                put(art2, x0 + W - ow - 3, color2, spk == other)
        if spk == "narr" and h >= 3:
            tag = " · · · "
            cv.text(x0 + (W - len(tag)) // 2, y0 + max(0, (h - 2) // 2), tag, G1)

    def _draw_scene(self, cv, x0, y0, W, H, gnow):
        """스토리 대화: 머리줄(챕터 · 줄 번호) → 무대(펫 ↔ 상대) → 지난 대사(흐리게) → 말 상자(타자 효과)"""
        sc = self.scene
        now = time.time()
        i, part = sc["ch"], sc["part"]
        c = D.CHAPTERS[i]
        lines = sc["lines"]
        idx = min(sc["idx"], len(lines) - 1)
        spk = lines[idx][0]
        text = self._scene_text(lines[idx])
        shown = int((now - sc["t0"]) * SCENE_CPS)
        typing = shown < len(text)
        # 머리줄
        head = f"{chip(f'CH{i + 1:02d}', 'black', 'lime')} {WH}{B}{c['title']}{RST} {G1}· {PART_NAMES.get(part, part.upper())}{RST}"
        cnt = f"{G4}{idx + 1:02d}{RST}{G1}/{len(lines):02d}{RST}"
        strip = segbar(idx + 1, len(lines), min(len(lines), max(4, (W - 30) // 2)), on=P3["lime"]) if W >= 56 else ""
        right = cnt + (" " + strip if strip else "")
        cv.ansi(x0 + W - vlen(right), y0, right)
        cv.ansi_clip(x0, y0, head, W - vlen(right) - 1)
        narr = spk == "narr"
        name, color, art = self._speaker(spk, gnow)
        stage = H >= 16 and W >= 44
        # 말 상자 (아래쪽). 무대가 없는 작은 창에선 상자 왼쪽에 초상화
        pw = 0 if (stage or narr or W < 50 or not art) else max(vlen(a) for a in art) + 2
        bx, bw = x0 + pw, W - pw
        tw = max(8, bw - 4)
        full = wrap_words(text, tw)
        bh = max(4, min(H - 2, len(full) + 2))
        by = y0 + H - bh
        body, left = [], max(0, shown)
        for ln in full:                           # 줄바꿈은 전체 문장 기준으로 고정하고 글자만 차례로 드러낸다
            if left <= 0:
                break
            body.append(ln[:left])
            left -= len(ln) + 1
        cv.box(bx, by, bw, bh, NV3 if not narr else NV2)
        label = f" {rgb(color)}{B}{name}{RST} " if name else f" {G1}· · ·{RST} "
        cv.ansi(bx + 2, by, label)
        self._anchor(bx + 2 + vlen(label), by, "talk")
        tc = G4 if narr else WH
        rows = bh - 2
        for r, ln in enumerate(body[:rows]):
            cv.ansi_clip(bx + 2, by + 1 + r, f"{tc}{ln}{RST}", tw)
        if typing:
            if body:
                r = min(len(body), rows) - 1
                cx = bx + 2 + vlen(body[r])
                if cx < bx + bw - 1:
                    cv.text(cx, by + 1 + r, "▌", LIME)
            else:
                cv.text(bx + 2, by + 1, "▌", LIME)
        elif int(now * 2) % 2:
            cv.text(bx + bw - 3, by + bh - 2, "▼", LIME)
        if pw:
            for r, ln in enumerate(art):
                yy = by + bh - len(art) + r
                if y0 < yy < y0 + H:
                    cv.text(x0 + 1, yy, ln, rgb(color) + B)
        # 무대는 말 상자 바로 위, 지난 대사는 그 위 (최근 줄이 무대 쪽, 위로 갈수록 흐리게)
        sh = 6 if stage and by - (y0 + 1) >= 6 else 0
        stage_top = by - sh
        if sh:
            self._scene_stage(cv, x0, stage_top, W, sh, gnow, idx)
        top = y0 + 1
        room = stage_top - top
        hist = lines[max(0, idx - room):idx]
        yy = stage_top - 1
        for k, (sp2, t2) in enumerate(reversed(hist)):
            if yy < top:
                break
            n2, c2, _ = self._speaker(sp2, gnow)
            tcol = G if k == 0 else G1 if k < 3 else G2
            who = f"{rgb(c2) if k == 0 else G1}{n2}{RST} " if n2 else ""
            cv.ansi_clip(x0 + 1, yy, who + f"{tcol}{self._scene_text((sp2, t2))}{RST}", W - 2)
            yy -= 1
        # 윗부분이 비어 있으면 장소 자막. 지난 대사가 차오르면 자리를 내준다
        cap = [f"{NV4}◇{RST} {G4}{B}{c['en']}{RST}"] + [f"  {G1}{ln}{RST}" for ln in wrap_words(c["summary"], max(8, W - 6))]
        if yy + 1 - top >= len(cap) + 2:
            for r, ln in enumerate(cap):
                cv.ansi_clip(x0 + 1, top + 1 + r, ln, W - 2)

    # ------------------------------------------------------------ 가방
    def _draw_bag(self, cv, x0, y0, W, H, gnow):
        g = self.g
        self._subtabs(cv, x0, y0, "bag")
        sub = self.sub["bag"]
        inv = g.s["inv"]
        counts = {0: len(inv.get("gear", [])), 1: sum(inv["items"].values()), 2: sum(inv["mats"].values()),
                  3: len(inv.get("decos", []))}
        cnt = f"{G4}{counts.get(sub, 0)}{RST}{G1}개{RST}"
        y = y0 + 1
        if sub == 0:
            S = g.stats()
            cv.ansi_clip(x0, y, sect(1, "EQUIP", W), W)
            self._anchor(x0 + title_end(1, "EQUIP"), y, "equip")
            y += 1
            for slot, label in D.EQUIP_SLOTS.items():
                gg = g.s["equip"].get(slot)
                if gg:
                    txt = f"{G1}{pad(label, 6)}{RST}{item_label(gg['id'], gg.get('plus', 0))} {G1}{eff_text(gg['id'])}{RST}"
                else:
                    txt = f"{G1}{pad(label, 6)}{RST}{G2}— 비어 있음 —{RST}"
                cv.ansi_clip(x0 + 1, y, txt, W - 1)
                y += 1
            stats = [("HP", S["maxhp"]), ("MP", S["maxmp"]), ("ATK", S["atk"]), ("DEF", S["df"]), ("INT", S["int"]),
                     ("SPD", S["spd"]), ("LUK", S["luk"])]
            stats = stats if W >= 76 else stats[2:6]
            cv.ansi(x0, y, cells([(k, f"{G4}{B}{v}{RST}") for k, v in stats], W))
            y += 1
            cv.ansi_clip(x0, y, sect(2, "SPARE", W, cnt), W)
            self._anchor(x0 + title_end(2, "SPARE"), y, "list")
            y += 1
        else:
            nm = {1: "ITEMS", 2: "MATERIALS", 3: "DECOR"}[sub]
            cv.ansi_clip(x0, y, sect(1, nm, W, cnt), W)
            self._anchor(x0 + title_end(1, nm), y, "list")
            y += 1
        rows_raw = self._bag_rows()
        rows = []
        for kind, a, b_ in rows_raw:
            if kind == "gear":
                it = D.ITEMS[b_["id"]]
                lock = f" {chip('LV' + str(it['lvl']), 'black', 'white')}" if it["lvl"] > g.p["lvl"] else ""
                rows.append(f"{G1}{pad(D.EQUIP_SLOTS[it['kind']], 6)}{RST}{item_label(b_['id'], b_.get('plus', 0))} "
                            f"{G1}{eff_text(b_['id'])}{RST}{lock}")
            elif kind in ("item", "mat"):
                rows.append(f"{item_label(a)} {G1}×{RST}{G4}{b_}{RST}")
            else:
                rows.append(f"{item_label(a)}" + (f" {chip('배치됨', 'black', 'lime')}" if b_ else ""))
        c = self.cur.get(f"bag{sub}", 0)
        c = min(c, max(0, len(rows) - 1))
        self.cur[f"bag{sub}"] = c
        list_h = max(1, y0 + H - y - 2)
        self._list(cv, x0, y, W, list_h, rows, c, {0: "(여분 장비 없음 · 상점/드롭/제작으로 획득)", 1: "(소모품 없음)",
                                                    2: "(재료 없음 · opencode 도구가 일하면 파편이 생겨요)", 3: "(꾸미기 없음 · 상점에서 구매)"}[sub])
        if rows_raw:
            kind, a, b_ = rows_raw[c]
            iid = b_["id"] if kind == "gear" else a
            for i, ln in enumerate(desc_lines(D.ITEMS[iid]["desc"], W)):
                cv.ansi(x0, y0 + H - 2 + i, ln)
            self._anchor(x0 + W - 1, y0 + H - 2, "desc")

    # ------------------------------------------------------------ 상점
    def _draw_shop(self, cv, x0, y0, W, H, gnow):
        g = self.g
        x = self._subtabs(cv, x0, y0, "shop")
        gold = f"{G1}GOLD{RST} {LIME}{B}{P.fmt_num(g.s['gold'])}{RST}{G1}G{RST}"
        if x + vlen(gold) + 2 <= x0 + W:
            cv.ansi(x0 + W - vlen(gold), y0, gold)
            self._anchor(x0 + W - vlen(gold) - 2, y0, "gold")
        y = y0 + 1
        kinds = {"food": "음식", "drink": "음료", "med": "약", "battle": "전투", "special": "특수", "weapon": "무기",
                 "armor": "상의", "acc": "장신구", "deco": "꾸미기"}
        if self.sub["shop"] == 0:
            rows_raw = g.shop_list()
            nw = min(max((vlen(D.ITEMS[r["id"]]["name"]) for r in rows_raw), default=8), max(8, W - 30))
            rows = []
            for r in rows_raw:
                it = D.ITEMS[r["id"]]
                kind = pad(kinds.get(it["kind"], ""), 6)
                price = f"{r['price']:>6,}G"
                if r["locked"]:
                    rows.append(f"{G2}{kind}{pad(it['name'], nw)} {price}{RST} {chip('LV' + str(it['lvl']), 'gray4', 'navy1', False)}")
                elif r["owned"]:
                    rows.append(f"{G2}{kind}{pad(it['name'], nw)}{RST} {G1}보유 중{RST}")
                else:
                    tag = ""
                    if r["special"]:
                        tag = " " + (chip("SEASON", "black", "lime3") if r.get("season") else chip("SALE -30%", "black", "lime"))
                    rows.append(f"{G1}{kind}{RST}{rarity_color(r['id'])}{pad(it['name'], nw)}{RST} {G4}{price}{RST}{tag} "
                                f"{G1}{eff_text(r['id'])}{RST}")
            key = "shop0"
        else:
            rows_raw = g.sell_list()
            rows = [f"{item_label(r['id'], r.get('plus', 0))} {G1}×{r['n']}{RST} {NV4}→{RST} {G4}{r['price']:,}G{RST}"
                    for r in rows_raw]
            key = "shop1"
        c = min(self.cur.get(key, 0), max(0, len(rows) - 1))
        self.cur[key] = c
        nm = "BUY" if key == "shop0" else "SELL"
        cv.ansi_clip(x0, y, sect(1, nm, W, f"{G4}{len(rows)}{RST}{G1}개{RST}"), W)
        self._anchor(x0 + title_end(1, nm), y, "list")
        self._list(cv, x0, y + 1, W, max(1, H - 4), rows, c, "(팔 물건이 없어요)")
        if rows_raw:
            iid = rows_raw[c]["id"]
            for i, ln in enumerate(desc_lines(D.ITEMS[iid]["desc"], W)):
                cv.ansi(x0, y0 + H - 2 + i, ln)
            self._anchor(x0 + W - 1, y0 + H - 2, "desc")

    # ------------------------------------------------------------ 공방
    def _draw_forge(self, cv, x0, y0, W, H, gnow):
        g = self.g
        x = self._subtabs(cv, x0, y0, "forge")
        mats = g.s["inv"]["mats"]
        mat_txt = "  ".join(f"{G1}{lab}{RST}{G4}{mats.get(k, 0)}{RST}" for k, lab in
                            (("shard_edit", "편집"), ("shard_scan", "탐색"), ("shard_exec", "실행"), ("boss_core", "코어")))
        if x + vlen(mat_txt) + 2 <= x0 + W:
            cv.ansi(x0 + W - vlen(mat_txt), y0, mat_txt)
            self._anchor(x0 + W - vlen(mat_txt) - 2, y0, "mats")
        nm = "GEAR" if self.sub["forge"] == 0 else "RECIPES"
        cv.ansi_clip(x0, y0 + 1, sect(1, nm, W), W)
        self._anchor(x0 + title_end(1, nm), y0 + 1, "list")
        y0 += 1
        H -= 1
        y = y0 + 1
        if self.sub["forge"] == 0:
            rows_raw = g.enhance_targets()
            rows = []
            for where, key, gg in rows_raw:
                label = "장착" if where == "equip" else "가방"
                rows.append(f"{G1}{label}{RST} {item_label(gg['id'], gg.get('plus', 0))} {G1}{eff_text(gg['id'])}{RST}")
            c = min(self.cur.get("forge0", 0), max(0, len(rows) - 1))
            self.cur["forge0"] = c
            big = H >= 16 and W >= 56
            info_h = 4 if big else 3
            list_h = max(1, H - 1 - info_h)
            self._list(cv, x0, y, W, list_h, rows, c, "(강화할 장비 없음)")
            yy = y + list_h
            if rows_raw:
                gg = rows_raw[c][2]
                info = g.enhance_info(gg)
                plus = gg.get("plus", 0)
                cv.ansi_clip(x0, yy, sect(2, "ENHANCE", W), W)
                self._anchor(x0 + title_end(2, "ENHANCE"), yy, "enhance")
                yy += 1
                if info:
                    rate = int(info["rate"] * 100)
                    rate_hex = P3["lime"] if rate >= 70 else P3["lime3"] if rate >= 40 else P3["white"]
                    t1 = (f"{G1}RATE{RST} {rgb(rate_hex)}{knob(rate)} {B}{rate}%{RST} {segbar(rate, 100, 10, on=rate_hex)}")
                    t2 = (f"{G1}COST{RST} {G4}{P.fmt_num(info['gold'])}G{RST} {G1}+{RST} {G4}{D.ITEMS[info['shard']]['name']} ×{info['need']}{RST}"
                          f" {G1}(보유 {info['have']}){RST}")
                    if info["down"]:
                        duck = g.s["inv"]["items"].get("duck_charm", 0)
                        t3 = (f"{chip('DOWN', 'black', 'white')} {G}실패 시 1단계 하락{RST} {G1}· 러버덕 부적 {duck} · 보호{RST} "
                              + (chip("ON", "black", "lime") if self.protect else chip("OFF", "gray4", "navy1")))
                    else:
                        t3 = f"{chip('SAFE', 'black', 'lime3')} {G}실패해도 하락 없음{RST}"
                    if big:
                        a, b_ = str(plus), str(plus + 1)
                        s1 = seg_lines("+" + a, P3["gray"], ghost=P3["navy1"])
                        s2 = seg_lines("+" + b_, P3["lime"], ghost=P3["navy1"])
                        wa = seg_width("+" + a)
                        wb = seg_width("+" + b_)
                        tx = x0 + 1 + wa + 3 + wb + 2
                        for i in range(3):
                            cv.ansi(x0 + 1, yy + i, s1[i])
                            cv.ansi(x0 + 1 + wa + 3, yy + i, s2[i])
                            cv.ansi_clip(tx, yy + i, (t1, t2, t3)[i], x0 + W - tx)
                        cv.ansi(x0 + 1 + wa, yy + 1, f"{NV4}›{RST}")
                    else:
                        cv.ansi_clip(x0, yy, f"{G4}+{plus}{RST} {NV4}›{RST} {LIME}{B}+{plus + 1}{RST}  " + t1, W)
                        cv.ansi_clip(x0, yy + 1, t2 + "  " + t3, W)
                else:
                    cv.ansi_clip(x0, yy, f"{chip('MAX', 'black', 'lime')} {LIME}{B}최대 강화 +10 달성!{RST}", W)
            if self.enh_show:
                self._forge_fx(cv, x0, y0, W, H)
        else:
            rows_raw = g.recipe_list()
            rows = []
            for r in rows_raw:
                rc = r["r"]
                need = " ".join(f"{D.ITEMS[k]['name'][:4]}{v}" for k, v in rc["need"].items())
                lock = f" {chip('LV' + str(rc['lvl']), 'black', 'white')}" if r["locked"] else ""
                name = item_label(rc["out"]) if r["ok"] else f"{G2}{D.ITEMS[rc['out']]['name']}{RST}"
                rows.append(f"{name} {G1}×{rc['qty']}{RST} {NV4}←{RST} {G1}{need}" + (f" +{rc['gold']}G" if rc["gold"] else "")
                            + f"{RST}{lock}" + (f" {chip('OK', 'black', 'lime')}" if r["ok"] else ""))
            c = min(self.cur.get("forge1", 0), max(0, len(rows) - 1))
            self.cur["forge1"] = c
            self._list(cv, x0, y, W, max(1, H - 3), rows, c)
            if rows_raw:
                rc = rows_raw[c]["r"]
                have = "  ".join(f"{D.ITEMS[k]['name']} {LIME if mats.get(k, 0) >= v else WH}{mats.get(k, 0)}{RST}{G1}/{v}{RST}"
                                 for k, v in rc["need"].items())
                for i, ln in enumerate(wrap_sep(f"{G1}보유{RST} {have}", W, "  ")[:2]):
                    cv.ansi(x0, y0 + H - 2 + i, ln)

    def _forge_fx(self, cv, x0, y0, W, H):
        """강화 연출: 네이비 패널에서 게이지가 차오르고(깡!) → 세그먼트 숫자로 결과"""
        res, t0 = self.enh_show
        el = time.time() - t0
        if el >= 2.8:
            self.enh_show = None
            return
        bw, bh = min(W - 4, 40), 7
        bx, by = x0 + (W - bw) // 2, y0 + max(1, (H - bh) // 2)
        cv.panel(bx, by, bw, bh, "navy")
        cv.ansi(bx + 1, by, f" {module('FX', 'FORGE')} ", BG_NAVY)
        if el < 1.2:
            k = "깡!" * (1 + int(el * 3) % 3)
            cv.ansi(bx + (bw - vlen(k)) // 2, by + 2, f"{LIME}{B}{k}{RST}", BG_NAVY)
            cv.ansi(bx + 3, by + 4, meter(el / 1.2 * 100, 100, bw - 6), BG_NAVY)
            for i in range(3):
                sx = bx + 2 + int((math.sin(el * 17 + i * 2.1) + 1) / 2 * (bw - 5))
                cv.ansi(sx, by + 1 + (i % 2) * 4, f"{LIME3}◈{RST}", BG_NAVY)
            return
        if res["ok"]:
            head, col, msg = chip("SUCCESS", "black", "lime"), P3["lime"], "강화 성공!!"
        elif res["protected"]:
            head, col, msg = chip("GUARD", "black", "navy4"), P3["navy4"], "실패… 러버덕이 지켜줬다!"
        elif res["down"]:
            head, col, msg = chip("DOWN", "black", "white"), P3["white"], f"실패… +{res['before']} → +{res['after']}"
        else:
            head, col, msg = chip("FAIL", "black", "gray"), P3["gray"], "실패… 재료만 날아갔다"
        num = f"+{res['after']}"
        seg = seg_lines(num, col, ghost=P3["navy2"])
        sx = bx + 3
        for i, ln in enumerate(seg):
            cv.ansi(sx, by + 2 + i, ln, BG_NAVY)
        tx = sx + seg_width(num) + 2
        cv.ansi(tx, by + 2, head, BG_NAVY)
        cv.ansi_clip(tx, by + 3, f"{G4}{msg}{RST}", bx + bw - 1 - tx, BG_NAVY)
        cv.ansi_clip(tx, by + 4, f"{G1}{res.get('name', '')}{RST}", bx + bw - 1 - tx, BG_NAVY)

    # ------------------------------------------------------------ 도감
    def _draw_dex(self, cv, x0, y0, W, H, gnow):
        g = self.g
        self._subtabs(cv, x0, y0, "dex", W)
        sub = self.sub["dex"]
        y = y0 + 1
        if sub == DEX_PROFILE:
            self._dex_profile(cv, x0, y, W, y0 + H - y, gnow)
        elif sub == DEX_QUEST:
            self._dex_quests(cv, x0, y, W, y0 + H - y, gnow)
        elif sub == DEX_DIARY:
            diary = g.s.get("diary", [])
            if not diary:
                cv.ansi_clip(x0, y, f"{G1}아직 일기가 없어요. 하루가 지나면 '어제의 개발 일지'가 쌓여요.{RST}", W)
                return
            c = min(self.cur.get("dex_diary", 0), len(diary) - 1)
            self.cur["dex_diary"] = c
            e = diary[-1 - c]
            cv.ansi_clip(x0, y, sect(1, "DIARY", W, f"{keycap('↑↓')} {G1}{c + 1}/{len(diary)}{RST}"), W)
            self._anchor(x0 + title_end(1, "DIARY"), y, "list")
            y += 1
            end = y0 + H - (2 if len(diary) > 1 else 0)
            for ln in g.diary_lines(e):
                for w in wrap_sep(ln, W):
                    if y >= end:
                        break
                    cv.ansi(x0, y, (f"{LIME}{B}{w}{RST}" if ln.startswith("◈") else f"{G4}{w}{RST}"))
                    y += 1
            # 최근 7일 토큰 스파크라인
            if len(diary) > 1 and y0 + H - 1 > y:
                last = diary[-7:]
                mx = max(1, max(d["tokens"] for d in last))
                spark = "".join(" ▁▂▃▄▅▆▇█"[min(8, int(d["tokens"] / mx * 8))] for d in last)
                cv.ansi_clip(x0, y0 + H - 1, f"{G1}TOKENS {len(last)}D{RST} {LIME}{spark}{RST} {G1}max{RST} {G4}{P.fmt_num(mx)}{RST}", W)
        elif sub == DEX_MON:
            mids = list(D.MONSTERS)
            rows = []
            for mid in mids:
                m = D.MONSTERS[mid]
                seen = g.s["seen"].get(mid, 0)
                kills = g.s["dex"].get(mid, 0)
                tag = chip("RAID", "black", "white") + " " if mid in D.RAID_BOSSES else ""
                rows.append(tag + (f"{G4}{m['name']}{RST}" if seen else f"{G2}???{RST}")
                            + (f" {G1}만남 {seen}{RST}" if mid in D.RAID_BOSSES else f" {G1}처치{RST} {G4 if kills else G2}{kills}{RST}"))
            c = min(self.cur.get("dex_mon", 0), len(rows) - 1)
            seen_n = sum(1 for mid in mids if g.s["seen"].get(mid))
            cv.ansi_clip(x0, y, sect(1, "BESTIARY", W, f"{G4}{seen_n}{RST}{G1}/{len(mids)}{RST}"), W)
            self._anchor(x0 + title_end(1, "BESTIARY"), y, "list")
            y += 1
            list_w = min(W, max(24, W - 14)) if W >= 60 else W
            list_h = max(1, H - 4)
            self._list(cv, x0, y, list_w, list_h, rows, c)
            mid = mids[c]
            m = D.MONSTERS[mid]
            if g.s["seen"].get(mid):
                if W >= 60:
                    for i, ln in enumerate(m["art"]):
                        cv.text(x0 + W - 13, y + 1 + i, ln, G4)
                for i, ln in enumerate(desc_lines(m["desc"], W)):
                    cv.ansi(x0, y0 + H - 2 + i, ln)
            else:
                cv.ansi(x0, y0 + H - 2, f"{NV4}›{RST} {G1}아직 만나지 못한 몬스터{RST}")
        elif sub == DEX_FORMS:
            self._dex_forms(cv, x0, y, W, y0 + H - y, gnow)
        elif sub == DEX_HALL:
            self._dex_hall(cv, x0, y, W, y0 + H - y, gnow)
        elif sub == DEX_ACH:
            rows = []
            for aid, name, desc, gold, title in D.ACHIEVEMENTS:
                got = aid in g.s["ach"]
                tt = f" {chip(title, 'gray4', 'navy1', False)}" if title and got else ""
                rows.append((f"{LIME}☼ {name}{RST}" if got else f"{G2}⋆ {name}{RST}") + f" {G1}{desc}{RST}{tt}")
            c = min(self.cur.get("dex_ach", 0), len(rows) - 1)
            got_n = len(g.s["ach"])
            right = f"{segbar(got_n, len(D.ACHIEVEMENTS), 10)} {G4}{got_n}{RST}{G1}/{len(D.ACHIEVEMENTS)}{RST}"
            cv.ansi_clip(x0, y, sect(1, "ACHIEVEMENTS", W, right), W)
            self._anchor(x0 + title_end(1, "ACHIEVEMENTS"), y, "list")
            self._list(cv, x0, y + 1, W, max(1, H - 3), rows, c)
            cv.ansi_clip(x0, y0 + H - 1, f"{NV4}›{RST} {G1}달성한 업적에서{RST} {keycap('↵')} {G1}→ 칭호로 설정{RST}", W)
        else:
            rows = []
            for key, label in self.SETTINGS:
                on = g.s["settings"].get(key)
                rows.append((chip("ON ", "black", "lime") if on else chip("OFF", "gray4", "navy1")) + f" {G4}{label}{RST}")
            rows.append(f"{chip('ABC', 'black', 'gray')} {G4}이름 바꾸기{RST} {G1}(이름표 {g.s['inv']['items'].get('nametag', 0)}개){RST}")
            c = min(self.cur.get("dex_set", 0), len(rows) - 1)
            cv.ansi_clip(x0, y, sect(1, "SETTINGS", W), W)
            self._anchor(x0 + title_end(1, "SETTINGS"), y, "list")
            list_h = max(1, min(len(rows), H - 6))
            self._list(cv, x0, y + 1, W, list_h, rows, c)
            ys = y + 1 + list_h
            if ys + 3 <= y0 + H:
                # 02 SYS: 실제 상태를 숨기지 않는다 (저장 파일 · 마지막 저장 · fps · 버전)
                fr = list(self._frames)
                fps = (len(fr) - 1) / (fr[-1] - fr[0]) if len(fr) > 1 and fr[-1] > fr[0] else 0.0
                age = max(0, int(g.now() - g.last_save))
                cv.ansi_clip(x0, ys, sect(2, "SYS", W), W)
                self._anchor(x0 + title_end(2, "SYS"), ys, "sys")
                td = g.s["tok_day"]
                tok_n = td["n"] if td.get("date") == P.day_key(g.now()) else 0
                cv.ansi_clip(x0 + 1, ys + 1, sysline([("save", f"{age}s ago"), ("fps", f"{fps:.0f}"),
                                                       ("data", f"v{D.SAVE_VERSION}"), ("mode", "관전" if g.readonly else "돌봄"),
                                                       ("tok", f"{P.fmt_num(tok_n)}/day ×{P.token_rate(tok_n):.2f}"),
                                                       ("size", f"{cv.w}x{cv.h}")]), W - 1)
                cv.ansi_clip(x0 + 1, ys + 2, f"{G1}file{RST} {G2}{P.pet_path(g.scope)}{RST}", W - 1)
            else:
                cv.ansi_clip(x0, y0 + H - 1, f"{G1}SAVE{RST} {G2}{P.pet_path(g.scope)}{RST}", W)

    def _dex_profile(self, cv, x0, y, W, h, gnow):
        g, p = self.g, self.g.p
        S = g.stats()
        f = D.FORMS[p["form"]]
        fam = g.s["family"]
        gen = fam.get("gen", 1)
        pers = D.PERSONALITIES.get(p.get("personality") or "")
        end = y + h
        head = f"{rgb(f['color'])}{B}{p['name']}{RST}" + (f" {G}「{p['title']}」{RST}" if p["title"] else "")
        head += f" {BG_NAVY1}{G4} {f['name']} {RST} {G1}{D.STAGES[f['stage']]}{RST}"
        right = f"{G1}GEN{RST} {LIME}{B}{gen}{RST}"
        cv.ansi_clip(x0, y, head, W - vlen(right) - 1)
        cv.ansi(x0 + W - vlen(right), y, right)
        lines = [f"{G}{f['desc']}{RST}"]
        if pers:
            lines.append(f"{G1}성격{RST} {G4}{B}{pers['name']}{RST} {G1}— {pers['desc']}{RST}")
        lines.append(("anchor", "spec"))
        lines.append(sect(1, "SPEC", W))
        need = P.exp_to_next(p["lvl"])
        lines.append(f"{G1}LV{RST} {LIME}{B}{p['lvl']:<3}{RST} {G1}EXP{RST} {meter(p['exp'], need, max(6, min(24, W - 34)))} "
                     f"{G4}{P.fmt_num(int(p['exp']))}{RST}{G1}/{P.fmt_num(need)}{RST}")
        # 스펙 표: 칸 하나 = 값 하나 (칸 사이 검은 1칸 틈)
        spec = [("HP", S["maxhp"]), ("MP", S["maxmp"]), ("ATK", S["atk"]), ("DEF", S["df"]), ("INT", S["int"]),
                ("SPD", S["spd"]), ("LUK", S["luk"]), ("KB", f"{p['kb']:.1f}")]
        per = 4 if W >= 48 else 2
        for i in range(0, len(spec), per):
            lines.append(cells([(k, f"{G4}{B}{v}{RST}") for k, v in spec[i:i + per]], W))
        care, disc = int(p["care"]), int(p.get("discipline", 50))
        lines.append(f"{G1}CARE{RST} {LIME}{knob(care)} {care:<3}{RST} {G1}DISC{RST} {NV4}{knob(disc)} {disc:<3}{RST} "
                     f"{G1}MISS{RST} {G4}{int(g.s['traits']['mistakes'])}{RST}")
        lines.append(f"{G1}NEXT ›{RST} {G}{g.evolution_hint()}{RST}")
        ok, why = g.can_retire()
        lines.append(f"{keycap('R', '은퇴식')} {LIME}{B}가능!{RST} {G}명예의 전당에 올리고 {gen + 1}대 알 받기{RST}" if ok
                     else f"{G1}RETIRE ›{RST} {G1}{why}{RST}")
        if gen > 1:
            lines.append(f"{G1}FAMILY{RST} {LIME3}EXP +{int(g.family_bonus('exp') * 100)}% · GOLD +{int(g.family_bonus('gold') * 100)}%{RST}"
                         f" {G1}(선대 {gen - 1}명){RST}")
        t = g.s["traits"]
        lines.append(("anchor", "record"))
        lines.append(sect(2, "RECORD", W))
        lines.append(f"{G1}성향{RST} {G4}전투 {int(t['battle'])} · 청소 {int(t['bug'])} · 기획 {int(t['plan'])}분 · 놀이 {int(t['play'])}{RST}")
        st = g.s["stats"]
        rec = [("KO", st.get("kills", 0)), ("BOSS", st.get("bosses", 0)), ("RESP", st.get("quests", 0)),
               ("TODO", st.get("todos_done", 0)), ("TOKEN", P.fmt_num(st.get("tokens", 0))), ("MEAL", st.get("meals", 0)),
               ("CLEAN", st.get("cleaned", 0)), ("FAINT", st.get("faints", 0))]
        for i in range(0, len(rec), per):
            lines.append(cells([(k, f"{G4}{v}{RST}") for k, v in rec[i:i + per]], W))
        yy = y + 1
        for ln in lines:
            if isinstance(ln, tuple):
                if yy < end:
                    self._anchor(x0 + title_end(1 if ln[1] == "spec" else 2, ln[1].upper()), yy, ln[1])
                continue
            for w in wrap_sep(ln, W):
                if yy >= end:
                    return
                cv.ansi(x0, yy, w)
                yy += 1

    def _dex_quests(self, cv, x0, y, W, h, gnow):
        g = self.g
        end = y + h
        now = time.time()
        ql = g.s.get("quest_log")
        q = g.quest_progress()
        if ql and ql.get("items"):
            done = sum(1 for it in ql["items"] if it["st"] == "completed")
            total = len([it for it in ql["items"] if it["st"] != "cancelled"])
            right = f"{segbar(done, total, max(4, min(12, total)))} {LIME}{B}{done}{RST}{G1}/{total}{RST}"
            cv.ansi_clip(x0, y, sect(1, "MAIN QUEST", W, right), W)
            self._anchor(x0 + title_end(1, "MAIN QUEST"), y, "list")
            y += 1
            title = ql.get("title", "")
            if title or not q:
                cv.ansi_clip(x0, y, f"{G4}{title}{RST}" + ("" if q else f" {chip('지난 목록', 'gray4', 'navy1', False)}"), W)
                y += 1
            blink = int(now * 2) % 2
            marks = {"completed": f"{LIME}⊠{RST}", "in_progress": f"{LIME if blink else LIME1}»{RST}", "cancelled": f"{G2}×{RST}"}
            rows = []
            for it in ql["items"]:
                mk = marks.get(it["st"], f"{G1}□{RST}")
                txt = (f"{G2}{it['c']}{RST}" if it["st"] in ("completed", "cancelled") else
                       f"{WH}{B}{it['c']}{RST}" if it["st"] == "in_progress" else f"{G4}{it['c']}{RST}")
                rows.append(f"{mk} {txt}")
            list_h = max(1, min(len(rows), (end - y) - 5))
            c = min(self.cur.get("dex_quest", 0), len(rows) - 1)
            self._list(cv, x0, y, W, list_h, rows, c)
            y += list_h
        else:
            cv.ansi_clip(x0, y, sect(1, "MAIN QUEST", W), W)
            self._anchor(x0 + title_end(1, "MAIN QUEST"), y, "list")
            y += 1
            for ln in wrap(f"{G}opencode가 할 일 목록(todo)을 만들면 여기에 떠요. 하나씩 끝날 때마다 보상!{RST}", W):
                if y >= end:
                    return
                cv.ansi(x0, y, ln)
                y += 1
        d = g.s["daily"]
        if y < end:
            cv.ansi_clip(x0, y, sect(2, "DAILY", W, f"{G1}출근 도장{RST} {LIME}{B}{d['streak']}{RST}{G1}일{RST}"), W)
            y += 1
        for qq in d["quests"]:
            if y >= end:
                return
            tgt, prog = qq["target"], qq["prog"]
            st = chip("DONE", "black", "lime") if qq["done"] else f"{G4}{P.fmt_num(prog)}{RST}{G1}/{P.fmt_num(tgt)}{RST}"
            mk = f"{LIME}☼{RST}" if qq["done"] else f"{G1}·{RST}"
            cv.ansi_clip(x0, y, f"{mk} {G4}{qq['text']}{RST} {segbar(prog, tgt, 8)} {st} {G1}+{qq['gold']}G{RST}", W)
            y += 1
        buffs = []
        if g.s["buffs"].get("exp_boost", 0) > gnow:
            buffs.append(chip(f"EXP×2 {int((g.s['buffs']['exp_boost'] - gnow) // 60)}m", "black", "lime"))
        if g.s["buffs"].get("inspired", 0) > gnow:
            buffs.append(chip(f"영감 +10% {int((g.s['buffs']['inspired'] - gnow) // 60)}m", "black", "lime3"))
        if g.s["buffs"].get("focus", 0) > gnow:
            buffs.append(chip("집중", "black", "navy4"))
        if y < end:
            cv.ansi_clip(x0, y, f"{G1}BUFF{RST} " + (" ".join(buffs) if buffs else f"{G2}—{RST}")
                         + f"  {G1}오늘 먹은 토큰{RST} {G4}{P.fmt_num(g.s['tok_day']['n'])}{RST}", W)

    def _dex_forms(self, cv, x0, y, W, h, gnow):
        g = self.g
        seen = set(g.s["family"].get("forms_seen") or [])
        order = D.FORM_ORDER
        rows = []
        for fid in order:
            f = D.FORMS[fid]
            if fid in seen:
                stage = D.STAGES[f["stage"]]
                rows.append(f"{rgb(f['color'])}{f['name']}{RST}" + (f" {G1}{stage}{RST}" if stage != f["name"] else ""))
            else:
                rows.append(f"{G2}??? {G1}({D.STAGES[f['stage']]}){RST}")
        n_adult = sum(1 for f in D.ADULT_FORMS if f in seen)
        right = f"{segbar(len(seen), len(order), len(order))} {G4}{len(seen)}{RST}{G1}/{len(order)} · 성체 {n_adult}/{len(D.ADULT_FORMS)}{RST}"
        cv.ansi_clip(x0, y, sect(1, "FORMS", W, right), W)
        self._anchor(x0 + title_end(1, "FORMS"), y, "list")
        c = min(self.cur.get("dex_forms", 0), len(rows) - 1)
        list_w = max(20, W - 14) if W >= 50 else W
        list_h = max(1, h - 3)
        self._list(cv, x0, y + 1, list_w, list_h, rows, c)
        fid = order[c]
        f = D.FORMS[fid]
        if fid in seen:
            if W >= 50:
                art = f["art"][int(time.time() * 2) % 2]
                for i, ln in enumerate(art):
                    cv.text(x0 + W - 12, y + 2 + i, ln.replace("{f}", D.FACES["happy"]), rgb(f["color"]))
            desc = f["desc"]
            if f.get("ult"):
                desc += f"  궁극기: {D.SKILLS[f['ult']]['name']}"
        else:
            desc = D.SECRET_HINT if fid == "maintainer" else "아직 만나지 못한 형태. 키우는 방식을 바꿔 보세요."
        for i, ln in enumerate(desc_lines(desc, W)):
            cv.ansi(x0, y + h - 2 + i, ln)

    def _dex_hall(self, cv, x0, y, W, h, gnow):
        g = self.g
        hall = g.s["family"].get("hall") or []
        cv.ansi_clip(x0, y, sect(1, "HALL OF FAME", W, f"{G4}{len(hall)}{RST}{G1}명{RST}"), W)
        self._anchor(x0 + title_end(1, "HALL OF FAME"), y, "list")
        y += 1
        h -= 1
        if not hall:
            for ln in wrap(f"{G}명예의 전당이 비어 있어요. 성체가 Lv.{D.RETIRE_RULE['lvl']}에 부화 {D.RETIRE_RULE['days']}일이 지나면"
                           f" (전설은 언제든) 프로필에서 [R] 은퇴식을 열 수 있어요. 은퇴한 선대마다 경험치 +5%·골드 +3% 가문 보너스!{RST}", W):
                if h <= 0:
                    return
                cv.ansi(x0, y, ln)
                y += 1
                h -= 1
            return
        rows = []
        for r in reversed(hall):
            f = D.FORMS.get(r["form"], D.FORMS["bit"])
            rows.append(f"{NV4}{r['gen']:02d}{RST} {rgb(f['color'])}{r['name']}{RST} {G1}{f['name']} LV{r['lvl']} · {r['days']}일{RST}")
        c = min(self.cur.get("dex_hall", 0), len(rows) - 1)
        list_h = max(1, min(len(rows), h - 5))
        self._list(cv, x0, y, W, list_h, rows, c)
        r = list(reversed(hall))[c]
        f = D.FORMS.get(r["form"], D.FORMS["bit"])
        yy = y + list_h
        pers = D.PERSONALITIES.get(r.get("personality") or "", {}).get("name", "-")
        info = [f"{G4}처치 {r.get('kills', 0)} · 보스 {r.get('bosses', 0)} · 응답 {r.get('quests', 0)} · 할 일 {r.get('todos', 0)} · "
                f"토큰 {P.fmt_num(r.get('tokens', 0))} · 돌봄 {r.get('care', 0)} · 성격 {pers}{RST}",
                f"{LIME3}「{r.get('epitaph', '')}」{RST}"]
        if r.get("title"):
            info.insert(0, f"{chip(r['title'], 'gray4', 'navy1', False)} {G1}정복한 지역 {r.get('zones', 0)}곳{RST}")
        art_ok = W >= 60 and h - list_h >= 4
        tw = W - 13 if art_ok else W
        for ln in info:
            for w in wrap_sep(ln, tw):
                if yy >= y + h:
                    break
                cv.ansi(x0, yy, w)
                yy += 1
        if art_ok:
            art = f["art"][0]
            for i, ln in enumerate(art):
                cv.text(x0 + W - 12, y + list_h + i, ln.replace("{f}", D.FACES["proud"]), rgb(f["color"]))

    # ------------------------------------------------------------ 오버레이들
    def _draw_overlay(self, cv, W, H, gnow):
        g, ov = self.g, self.overlay
        kind = ov["kind"]
        if kind in ("feed", "med"):
            items = g.items_of(("food", "drink")) if kind == "feed" else g.items_of(("med", "special"))
            ov["items"] = items
            if not items:
                self.overlay = None
                return
            rows = []
            for i, (iid, n) in enumerate(items):
                e = D.ITEMS[iid]["eff"]
                eff = " ".join(f"{k}{'+' if v > 0 else ''}{v}" for k, v in (("포만", e.get("full")), ("기분", e.get("mood")),
                                                                            ("체력", e.get("energy")), ("건강", e.get("health"))) if v)
                rows.append(f"{G1}{i + 1}{RST} {item_label(iid)} {G1}×{RST}{G4}{n}{RST} {LIME3}{eff}{RST}")
            self._menu_box(cv, W, H, "FEED  무엇을 먹일까?" if kind == "feed" else "MED  무엇을 쓸까?", rows,
                           self.cur.get("ov_" + kind, 0))
        elif kind == "play":
            rows = [f"{keycap(str(i + 1))} {G4}{B}{name}{RST} {G1}{desc}{RST}" for i, (_, name, desc) in enumerate(D.MINIGAMES)]
            self._menu_box(cv, W, H, "PLAY  뭐 하고 놀까?", rows, None)
        elif kind == "skill":
            rows = []
            p = g.p
            for i, sid in enumerate(g.available_skills()):
                sk = D.SKILLS[sid]
                cd = g.battle and sid in g.battle.get("cd", {})
                ok = p["mp"] >= sk["mp"] and not cd
                rows.append(f"{keycap(str(i + 1), on=ok)} {LIME3 if ok else G2}{B}{sk['name']}{RST} {G1}MP{sk['mp']}{RST} "
                            f"{G if ok else G2}{sk['desc']}{RST}" + (f" {chip('CD', 'gray4', 'navy2', False)}" if cd else ""))
            self._menu_box(cv, W, H, f"SKILL  MP {int(p['mp'])}", rows, None)
        elif kind == "bitem":
            items = g.battle_items()
            rows = [f"{keycap(str(i + 1))} {item_label(iid)} {G1}×{n}{RST} {G}{D.ITEMS[iid]['desc']}{RST}" for i, (iid, n) in enumerate(items)]
            if not rows:
                rows = [f"{G1}(전투용 아이템 없음 · 상점에서 커피/핫픽스 패치){RST}"]
            self._menu_box(cv, W, H, "ITEM", rows, None)
        elif kind == "rename":
            bw = min(W - 4, 42)
            bh = 5
            bx, by = (W - bw) // 2, max(2, H // 2 - 3)
            cv.fill(bx - 1, by, bw + 2, bh)
            cv.panel(bx, by, bw, bh, "navy")
            cv.ansi(bx + 1, by, chip("NAME", "black", "lime") + f" {G4}새 이름 (최대 12자){RST}", BG_NAVY)
            cur = f"{LIME}▌{RST}" if int(time.time() * 2) % 2 else " "
            cv.panel(bx + 2, by + 2, bw - 4, 1, "navy1")
            cv.ansi_clip(bx + 3, by + 2, f"{WH}{B}{ov['buf']}{RST}" + cur, bw - 6, BG_NAVY1)
            cv.ansi(bx + 2, by + 4, f"{G1}이름표 1개 사용{RST}  {keycap('↵', '확인')}  {keycap('Esc', '취소')}", BG_NAVY)
        elif kind == "retire":
            p = g.p
            gen = g.s["family"].get("gen", 1)
            f = D.FORMS[p["form"]]
            lines = [f"{rgb(f['color'])}{B}{p['name']}{RST} {G1}{gen}대 · {f['name']} LV{p['lvl']} · {P.fmt_age(g.age())}{RST}",
                     f"{G4}명예의 전당에 올라 은퇴하고, 새 알이 도착해요.{RST}",
                     f"{chip('KEEP', 'black', 'lime')} {G}골드 · 가방 · 방 꾸미기 · 업적 · 몬스터/진화 도감 · 출근 도장{RST}",
                     f"{chip('RESET', 'black', 'white')} {G}레벨 · 진화 · 모험 진행(지역) · 성향 · 성격{RST}",
                     f"{chip('BONUS', 'black', 'lime3')} {G}은퇴한 선대 1명마다 경험치 +5% · 골드 +3% (최대 10대){RST}",
                     f"{G1}새 이름: {P.heir_name(p['name'], gen + 1)} (이름표로 바꿀 수 있어요){RST}"]
            self._center_box(cv, W, H, "RETIRE  은퇴식", lines, footer=[("↵", "진행"), ("Esc", "취소")])

    def _menu_box(self, cv, W, H, title, rows, cursor):
        """네이비 카드 + 라임 제목 칩. cursor 가 있으면 목록 선택형"""
        bw = min(W - 2, max(32, max(vlen(r) for r in rows) + 6, vlen(title) + 8))
        bh = min(H - 3, len(rows) + 3)
        bx, by = (W - bw) // 2, max(1, (H - bh) // 2)
        cv.fill(bx - 1, by, bw + 2, bh)       # 한 칸 여백: 뒤 화면 글자가 카드에 붙어 보이지 않게
        cv.panel(bx, by, bw, bh, "navy")
        cv.ansi(bx + 1, by, chip(title, "black", "lime"), BG_NAVY)
        esc = keycap("Esc", "닫기")
        cv.ansi(bx + bw - vlen(esc) - 1, by, esc, BG_NAVY)
        if cursor is None:
            for i, r in enumerate(rows[: bh - 2]):
                cv.ansi_clip(bx + 2, by + 2 + i, r, bw - 4, BG_NAVY)
        else:
            self._list(cv, bx + 1, by + 2, bw - 2, bh - 2, rows, min(cursor, len(rows) - 1), base=BG_NAVY, sel="navy2")

    def _center_box(self, cv, W, H, title, lines, tone="lime", footer=None):
        """가운데 카드. lines 에 ('seg', 글자, 색, 단위) 를 넣으면 세그먼트 숫자 3줄로 그린다"""
        maxw = min(W - 6, 58)
        body = []
        for ln in lines:
            if isinstance(ln, tuple):
                _, txt, col, unit = (ln + ("",))[:4]
                rows = seg_lines(txt, col, ghost=P3["navy1"])
                if unit:
                    rows[2] += f" {G1}{unit}{RST}"
                if seg_width(txt) + vlen(unit) + 1 <= maxw:
                    body.extend(rows)
                else:
                    body.append(f"{rgb(col)}{B}{txt}{RST} {G1}{unit}{RST}")
            else:
                body.extend(wrap_sep(ln, maxw) if ln else [""])
        foot = "  ".join(keycap(k, v) if k else f"{G1}{v}{RST}" for k, v in (footer or [("", "아무 키나 누르면 닫혀요")]))
        head = chip(title, "black", tone)
        bw = min(W - 2, max(28, max((vlen(x) for x in body), default=0) + 4, vlen(head) + 4, vlen(foot) + 4))
        bh = min(H - 3, len(body) + 4)
        bx, by = (W - bw) // 2, max(1, (H - bh) // 2)
        cv.fill(bx - 1, by, bw + 2, bh)       # 한 칸 여백
        cv.panel(bx, by, bw, bh, "navy")
        cv.ansi(bx + 1, by, head, BG_NAVY)
        for i, ln in enumerate(body[: bh - 4]):
            cv.ansi(bx + 2, by + 2 + i, ln, BG_NAVY)
        cv.ansi(bx + bw - vlen(foot) - 2, by + bh - 1, foot, BG_NAVY)

    def _welcome_box(self, cv, W, H, lines):
        self._center_box(cv, W, H, f"HELLO  {self.g.p['name']}", [f"{G4}{ln}{RST}" if ln else "" for ln in lines], tone="navy4")

    def _summary_box(self, cv, W, H, s):
        if s.get("story"):
            n = len(D.CHAPTERS)
            if s.get("win"):
                lines = [f"{LIME}{B}CH{s['ch'] + 1:02d} CLEAR{RST} {G4}「{s['title']}」{RST} {G1}· {s['boss']} 격파{RST}",
                         ("seg", f"{s['shards']:02d}", P3["lime"], f"/{n} 커밋 조각"),
                         f"{G1}조각{RST} {LIME}#{s['ch'] + 1}{RST} {G4}{s['hash']}{RST}  {G1}+{RST}{G4}{P.fmt_num(s['gold'])}G{RST}"
                         f"  {G1}+{RST}{G4}{P.fmt_num(s['exp'])}EXP{RST}"]
                if s.get("loot"):
                    lines.append(f"{G1}LOOT{RST} {G}" + ", ".join(s["loot"][:6]) + RST)
                lines.append(f"{G1}에필로그는 [7] 스토리 화면에서 이어져요{RST}")
                self._center_box(cv, W, H, "CHAPTER CLEAR", lines, tone="lime")
            else:
                left = s.get("left", 0)
                lines = [f"{WH}{B}{s['boss']}{RST} {G1}LV{s['lvl']}{RST}",
                         f"{G1}남은 체력{RST} {segbar(left, s.get('maxhp') or 1, 14, on=P3['white'])} {G4}{P.fmt_num(left)}{RST}",
                         f"{G4}{s['reason']}{RST}",
                         f"{G1}챕터 보스전은 져도 기절 페널티 없음 · HP가 50% 넘으면 다시 도전 [B]{RST}"]
                self._center_box(cv, W, H, "BOSS FIGHT", lines, tone="white" if s.get("fainted") else "navy4")
            return
        if s.get("raid"):
            tone = "lime" if s.get("cleared") else "navy4"
            lines = [f"{G4}{B}{s['reason']}{RST} {G1}· {s['boss']}{RST}",
                     ("seg", P.fmt_num(s["dealt"]), P3["lime"], "DMG"),
                     f"{G4}+{s['gold']}G · +{s['exp']}EXP{RST}",
                     f"{G1}공동 진행{RST} {segbar(s['total'], s['hp'], 14, on=P3['white'])} {G4}{s['pct']:.0f}%{RST}"
                     + (f" {G1}· 내 순위 {s['rank']}위{RST}" if s.get("rank") else "")]
            if s.get("cleared"):
                lines.append(f"{LIME}{B}이번 주 레이드 보스 격파! 기여한 모든 펫이 보상을 받아요{RST}")
            self._center_box(cv, W, H, "RAID RESULT", lines, tone=tone)
            return
        tone = "white" if s["fainted"] else "lime"
        lines = [f"{WH if s['fainted'] else G4}{B}{s['reason']}{RST} {G1}· {s['zone']} B{s['floor']}F · {s['mins']:.0f}분{RST}",
                 ("seg", f"+{s['gold']}", P3["white"] if s["fainted"] else P3["lime"], "G"),
                 f"{G1}FLOORS{RST} {G4}{s['floors']}{RST}  {G1}KO{RST} {G4}{s['kills']}{RST}"]
        if s["loot"]:
            lines.append(f"{G1}LOOT{RST} {G}" + ", ".join(s["loot"][:8]) + (" …" if len(s["loot"]) > 8 else "") + RST)
        if s["fainted"]:
            lines.append(f"{chip('FAINT', 'black', 'white')} {WH}기절해서 골드·재료 절반을 잃었어요… 밥 먹고 쉬게 해주세요{RST}")
        self._center_box(cv, W, H, "EXPEDITION RESULT", lines, tone=tone)

    def _frame_rect(self, cv, x0, y0, W, H, cx, cy, rw, rh, style):
        """장면 영역(y0..y0+H) 안에서만 사각 틀을 그린다 (머리줄·안내줄 보호)"""
        x1, x2 = cx - rw, cx + rw
        y1, y2 = cy - rh, cy + rh
        for yy in (y1, y2):
            if y0 <= yy < y0 + H:
                a, b = max(x0, x1), min(x0 + W - 1, x2)
                if b > a:
                    cv.text(a, yy, "─" * (b - a + 1), style)
                    if x1 >= x0:
                        cv.text(x1, yy, "┌" if yy == y1 else "└", style)
                    if x2 < x0 + W:
                        cv.text(x2, yy, "┐" if yy == y1 else "┘", style)
        for yy in range(max(y0, y1 + 1), min(y0 + H, y2)):
            if x1 >= x0:
                cv.text(x1, yy, "│", style)
            if x2 < x0 + W:
                cv.text(x2, yy, "│", style)

    # ------------------------------------------------------------ 진화 연출
    def _evolve_scene(self, cv, x0, y0, W, H, ev, gnow):
        """진화: 가운데서 사각 틀이 퍼져 나가고(줌), 옛 모습 ↔ 새 모습이 깜빡이다가 확정"""
        g = self.g
        old, new, until = ev
        now = time.time()
        total = 4.0 if old == "egg" else 4.5
        el = total - (until - gnow)
        cx, cy = x0 + W // 2, y0 + H // 2
        for k in range(4):
            r = (el * 6 + k * 3.5) % 14
            rw, rh = int(r * 2.6), int(r * 0.8)
            if rw >= 7 and rh >= 3:
                self._frame_rect(cv, x0, y0, W, H, cx, cy, rw, rh, (NV2, NV3, LIME1, NV2)[k])
        form = old if el < 2.4 and int(now * (2 + el * 3)) % 2 else new
        if form != "egg":
            art, color = face_sprite(g, gnow, form=form, face="joy")
        else:
            art, color = D.FORMS["egg"]["art"][0], D.FORMS["egg"]["color"]
        sx = cx - 5
        for i, ln in enumerate(art):
            cv.text(sx, cy - 2 + i, ln, rgb(color) + B)
        head = chip("HATCH" if old == "egg" else "EVOLVE", "black", "lime" if el > 2.4 or int(now * 6) % 2 else "navy4")
        cv.ansi(cx - vlen(head) // 2, y0, head)
        # 왼쪽 위: 단계 숫자
        stage = D.FORMS[new]["stage"] if el > 2.4 else D.FORMS[old]["stage"]
        if W >= 50 and H >= 10:
            for i, ln in enumerate(seg_lines(f"{stage:02d}", P3["lime"], ghost=P3["navy1"])):
                cv.ansi(x0 + 1, y0 + 1 + i, ln)
            cv.ansi(x0 + 1, y0 + 4, f"{G1}STAGE{RST} {G4}{D.STAGES[stage]}{RST}")
        if old == "egg":
            t = f"{LIME}{B}부화!!{RST} {G4}{g.p['name']} 탄생{RST}"
        else:
            t = f"{G}{D.FORMS[old]['name']}{RST} {NV4}›{RST} {LIME}{B}{D.FORMS[new]['name']}{RST}"
        ty = min(y0 + H - 3, cy + 3)
        cv.ansi(cx - vlen(t) // 2, ty, t)
        if el > 2.4:
            for i, ln in enumerate(wrap(f"{G}{D.FORMS[new]['desc']}{RST}", max(10, W - 8))[:2]):
                if ty + 1 + i < y0 + H:
                    cv.ansi(cx - vlen(ln) // 2, ty + 1 + i, ln)

    def _retire_scene(self, cv, x0, y0, W, H, rt, gnow):
        """은퇴식 연출: 선대가 손을 흔들며 명예의 전당으로 떠나고, 새 알이 도착"""
        g = self.g
        old_form, old_name, until = rt
        now = time.time()
        total = 6.0
        el = total - (until - gnow)
        for i in range(14):
            sx = x0 + (i * 11 + int(now * 5)) % max(1, W)
            sy = y0 + 1 + (i * 7 + int(now * 2)) % max(1, H - 1)
            cv.text(sx, sy, "◈" if (i + int(now * 3)) % 3 == 0 else "·", LIME if i % 3 == 0 else NV3)
        head = chip("RETIRE", "black", "lime") + f" {G4}{B}{old_name}{RST}{G}, 그동안 고마웠어요!{RST}"
        cv.ansi_clip(max(x0, x0 + (W - vlen(head)) // 2), y0, head, W)
        cy = y0 + max(2, H // 2 - 2)
        f = D.FORMS.get(old_form, D.FORMS["bit"])
        art = [ln.replace("{f}", D.FACES["proud"] if int(now * 2) % 2 else D.FACES["wink"]) for ln in f["art"][int(now * 2) % 2]]
        walk = int(max(0.0, el - 1.5) * 5)
        ox = min(x0 + W - 12, x0 + (W - 11) // 2 + walk)
        for i, ln in enumerate(art):
            if cy + i < y0 + H:
                cv.text(ox, cy + i, ln, rgb(f["color"]) + B)
        if el < 3.5:
            wave = "안녕~ o/" if int(now * 3) % 2 else "안녕~ o_"
            cv.text(min(x0 + W - vlen(wave) - 1, ox + 12), cy, wave, G4)
        if el > 2.8:
            egg = D.FORMS["egg"]["art"][int(now * 2) % 2]
            ex = max(x0 + 1, x0 + (W - 11) // 2 - 16)
            for i, ln in enumerate(egg):
                if cy + i < y0 + H:
                    cv.text(ex, cy + i, ln, rgb(D.FORMS["egg"]["color"]))
            msg = f"{G1}NEXT GEN ›{RST} {LIME}{B}{g.s['family'].get('gen', 2)}대 알이 도착했어요{RST}"
            if cy + 5 < y0 + H:
                cv.ansi(max(x0, x0 + (W - vlen(msg)) // 2), cy + 5, msg)
        rec = (g.s["family"].get("hall") or [{}])[-1]
        if rec.get("epitaph") and cy + 6 < y0 + H:
            for i, ln in enumerate(wrap(f"{LIME3}「{rec['epitaph']}」{RST}", W - 4)[:2]):
                if cy + 6 + i < y0 + H:
                    cv.ansi(x0 + max(2, (W - vlen(ln)) // 2), cy + 6 + i, ln)

    # ------------------------------------------------------------ 미니게임
    def _minigame(self, cv, x0, y0, W, H, gnow):
        g = self.g
        mg = g.mg
        kind = mg["kind"]
        name = dict((k, n) for k, n, _ in D.MINIGAMES)[kind]
        cv.ansi_clip(x0, y0, f"{chip('GAME', 'black', 'lime')} {G4}{B}{name}{RST}", W)
        if mg.get("phase") == "result":
            self._center_box(cv, W, H + 2, "RESULT", [f"{G4}{mg.get('summary', '')}{RST}"], footer=[("↵", "닫기")])
            return
        getattr(self, "_mg_" + kind)(cv, x0, y0, W, H, gnow, mg)

    def _mg_dir(self, cv, x0, y0, W, H, gnow, mg):
        g = self.g
        right = f"{G1}ROUND{RST} {segbar(mg['round'] + 1, mg['rounds'], mg['rounds'])} {G1}HIT{RST} {LIME}{B}{mg['score']}{RST}"
        cv.ansi(x0 + W - vlen(right), y0, right)
        cv.ansi_clip(x0, y0 + 1, f"{G}{P.fix_josa(g.p['name'] + '이(가)')} 어느 쪽을 볼까요?{RST}", W)
        art, color = face_sprite(g, gnow)
        cy = y0 + max(3, H // 2 - 2)
        cx = x0 + (W - 11) // 2
        look = mg.get("look")
        if mg["phase"] == "show":
            shift = -3 if look == "L" else 3
            for i, ln in enumerate(art):
                cv.text(cx + shift, cy + i, ln, rgb(color))
            arrow = "◀◀" if look == "L" else "▶▶"
            cv.text(cx - 6 if look == "L" else cx + 15, cy + 1, arrow, LIME + B)
            ok = mg["choice"] == look
            res = chip("HIT ○", "black", "lime") if ok else chip("MISS ×", "black", "white")
            cv.ansi(x0 + (W - vlen(res)) // 2, cy + 5, res)
        else:
            for i, ln in enumerate(art):
                cv.text(cx, cy + i, ln, rgb(color))
            cv.ansi(max(x0, cx - 8), cy + 1, keycap("←"))
            cv.ansi(min(x0 + W - 2, cx + 15), cy + 1, keycap("→"))

    def _mg_whack(self, cv, x0, y0, W, H, gnow, mg):
        now = time.time()
        if mg["phase"] == "ready":
            left = max(0, mg["t0"] - gnow)
            n = str(int(left) + 1)
            seg = seg_lines(n, P3["lime"], ghost=P3["navy1"])
            sx = x0 + (W - seg_width(n)) // 2
            for i, ln in enumerate(seg):
                cv.ansi(sx, y0 + H // 2 - 1 + i, ln)
            cv.ansi(x0 + (W - 5) // 2, y0 + H // 2 + 3, f"{G1}READY{RST}")
            return
        left = max(0, mg["dur"] - (gnow - mg["t0"]))
        right = f"{G1}HIT{RST} {LIME}{B}{mg['hits']}{RST} {G1}MISS{RST} {G4}{mg['miss']}{RST} {G1}ESC{RST} {G4}{mg['esc']}{RST}"
        cv.ansi(x0 + W - vlen(right), y0, right)
        cv.ansi_clip(x0, y0 + 1, f"{G1}TIME{RST} {meter(left, mg['dur'], max(8, min(30, W - 12)))} {G4}{int(left):>2}s{RST}", W)
        cell_w = max(7, min(12, (W - 4) // 3))
        cell_h = max(2, min(4, (H - 3) // 3))
        gx = x0 + (W - cell_w * 3) // 2
        gy = y0 + 2
        for r, row in enumerate(D.WHACK_LAYOUT):
            for c_, key in enumerate(row):
                bx, by = gx + c_ * cell_w, gy + r * cell_h
                if by + cell_h > y0 + H:
                    continue
                fl = mg["flash"].get(key)
                active = key in mg["cells"]
                pw, ph = cell_w - 1, max(1, cell_h - (1 if cell_h > 2 else 0))
                if fl:
                    pbg, lab = (P3["lime"], BLACK) if fl[1] else (P3["white"], BLACK)
                elif active:
                    pbg, lab = P3["navy2"], G4
                else:
                    pbg, lab = P3["navy1"], G1
                cv.panel(bx, by, pw, ph, pbg)
                base = bg(pbg)
                cv.ansi(bx + 1, by, f"{lab}{key}{RST}", base)
                mid_y = by + ph // 2 if ph > 1 else by
                if fl:
                    t = "팡!" if fl[1] else " × "
                    cv.ansi(bx + (pw - vlen(t)) // 2, mid_y, f"{BLACK}{B}{t}{RST}", base)
                elif active:
                    bug = "\\ж/" if int(now * 6) % 2 else "/ж\\"
                    cv.ansi(bx + (pw - 3) // 2, mid_y, f"{LIME}{B}{bug}{RST}", base)

    def _mg_quiz(self, cv, x0, y0, W, H, gnow, mg):
        g = self.g
        idx = min(mg["idx"], len(mg["qs"]) - 1)
        q, ans, expl = D.QUIZ[mg["qs"][idx]]
        marks = "".join((f"{LIME}○{RST}" if ok else f"{WH}×{RST}") for ok in mg["hist"])
        marks += f"{NV2}{'·' * (len(mg['qs']) - len(mg['hist']))}{RST}"
        right = f"{G1}Q{RST} {G4}{idx + 1}/{len(mg['qs'])}{RST} {marks} {G1}SCORE{RST} {LIME}{B}{mg['score']}{RST}"
        cv.ansi(x0 + W - vlen(right), y0, right)
        body = wrap(f"{WH}{B}{q}{RST}", W - 8)
        bh = min(max(3, len(body) + 2), max(3, H - 6))
        cv.panel(x0, y0 + 1, W, bh, "navy")
        cv.ansi(x0 + 1, y0 + 2, f"{LIME}{B}Q.{RST}", BG_NAVY)
        for i, ln in enumerate(body[: bh - 2]):
            cv.ansi(x0 + 5, y0 + 2 + i, ln, BG_NAVY)
        yy = y0 + 1 + bh + 1
        if mg["phase"] == "ask":
            left = max(0.0, D.QUIZ_TIME - (gnow - mg["t"]))
            cv.ansi_clip(x0, yy - 1, f"{G1}TIME{RST} {meter(left, D.QUIZ_TIME, max(8, min(30, W - 12)))} {G4}{int(left) + 1:>2}s{RST}", W)
            if yy + 1 < y0 + H:
                o = f"{BG_LIME}{BLACK}{B}  O  {RST} {G4}맞다{RST}"
                x = f"{BG_GRAY}{BLACK}{B}  X  {RST} {G4}아니다{RST}"
                cv.ansi(x0 + max(0, W // 4 - 4), yy + 1, o)
                cv.ansi(x0 + max(14, W * 3 // 4 - 6), yy + 1, x)
        else:
            ok = mg.get("ok")
            timeout = mg.get("ans") is None
            res = chip("정답 ○", "black", "lime") if ok else chip("시간 초과" if timeout else "땡 ×", "black", "white")
            cv.ansi_clip(x0, yy - 1, f"{res} {G1}정답은{RST} {LIME if ans else WH}{B}{'O' if ans else 'X'}{RST}", W)
            for i, ln in enumerate(wrap(f"{NV5}{expl}{RST}", W - 14 if W >= 30 else W)[: max(0, y0 + H - yy)]):
                cv.ansi(x0, yy + i, ln)
            art, color = face_sprite(g, gnow, face="joy" if ok else "sad")
            ay = y0 + H - 4
            if ay > yy - 1 and W >= 30:
                for i, ln in enumerate(art):
                    cv.text(x0 + W - 13, ay + i, ln, rgb(color))

    def _mg_type(self, cv, x0, y0, W, H, gnow, mg):
        now = time.time()
        idx = mg["idx"]
        tgt = mg["phrases"][idx] if idx < len(mg["phrases"]) else ""
        right = f"{G1}LINE{RST} {segbar(idx + 1, len(mg['phrases']), len(mg['phrases']))} {G4}{idx + 1}/{len(mg['phrases'])}{RST}"
        cv.ansi(x0 + W - vlen(right), y0, right)
        cv.panel(x0, y0 + 1, W, 3, "navy")
        cv.ansi(x0 + 1, y0 + 1, f"{G1}TYPE THIS{RST}", BG_NAVY)
        cv.ansi_clip(x0 + 2, y0 + 2, f"{WH}{B}{tgt}{RST}", W - 4, BG_NAVY)
        cv.panel(x0, y0 + 4, W, 3, "navy1")
        cv.ansi(x0 + 1, y0 + 4, f"{G1}INPUT{RST}", BG_NAVY1)
        xx = x0 + 2
        for i, ch in enumerate(mg["buf"]):
            ok = i < len(tgt) and tgt[i] == ch
            xx = cv.text(xx, y0 + 5, ch, (BG_NAVY1 + LIME) if ok else (BG_WHITE + BLACK + B))
            if xx >= x0 + W - 2:
                break
        cv.text(min(xx, x0 + W - 3), y0 + 5, "▌" if int(now * 2) % 2 else " ", BG_NAVY1 + LIME)
        y = y0 + 7
        if mg.get("t"):
            el = max(0.5, gnow - mg["t"])
            cpm = len(mg["buf"]) / el * 60
            num = f"{cpm:.0f}"
            if H - 7 >= 4 and W >= 30:
                for i, ln in enumerate(seg_lines(num, P3["lime"], ghost=P3["navy1"])):
                    cv.ansi(x0 + 1, y + i, ln)
                cv.ansi(x0 + 2 + seg_width(num), y + 2, f"{G1}타/분{RST}")
                y += 3
            else:
                cv.ansi(x0, y, f"{G1}CPM{RST} {LIME}{B}{num}{RST}")
                y += 1
        for i, (acc, cpm) in enumerate(mg["res"]):
            if y + i < y0 + H:
                cv.ansi(x0, y + i, f"{NV4}{i + 1:02d}{RST} {G1}정확도{RST} {G4}{acc * 100:.0f}%{RST} {G1}· 분당{RST} {G4}{cpm:.0f}타{RST}")


# ============================================================== 목장 (overview 창)
def render_ranch(scopes, W, H, reg_colors=None, anchors=None):
    """등록된 모든 인스턴스의 펫을 한눈에 (읽기 전용) — 번호 붙은 모듈 카드.
    anchors: `?` 가이드 번호표 자리 [(x, y, key)] (oc_monitor.MON_GUIDE 의 ranch/raidbar/cards)"""
    reg_colors = reg_colors or {}
    now = time.time()
    cv = Canvas(W, H)
    pets = [(sc, P.pet_summary(sc, now)) for sc in scopes]
    pets = [(sc, sm) for sc, sm in pets if sm]
    blink = int(now * 2) % 2
    # 머리줄: ── RANCH 3 ──── RAID 보스 ▮▮▮▯ 64% MVP
    right = ""
    wk = P.week_key(now)
    rs = P.raid_summary(wk, now)
    boss = D.MONSTERS[rs["boss"]]["name"]
    if rs["rows"]:
        pct = 100 * rs["dealt"] / max(1, rs["hp"])
        right = (f"{chip('RAID', 'black', 'white')} {G4}{boss}{RST} "
                 + (f"{LIME}{B}격파!{RST}" if rs["cleared"] else f"{segbar(rs['dealt'], rs['hp'], 8, on=P3['white'])} {G4}{pct:.0f}%{RST}")
                 + f" {G1}MVP{RST} {G4}{rs['rows'][0]['name']}{RST}")
    else:
        right = f"{chip('RAID', 'black', 'white')} {G4}{boss}{RST} {G1}이번 주 첫 출격 대기{RST}"
    right += f" {keycap('?')}"
    head = f"{NV2}──{RST} {module('PET', 'RANCH')} {G4}{len(pets)}{RST} "
    if anchors is not None:
        anchors.append((vlen(head) + 1, 0, "ranch"))
    if right and vlen(head) + vlen(right) + 3 <= W:
        cv.ansi(0, 0, head + f"{NV2}{'─' * max(1, W - vlen(head) - vlen(right) - 1)}{RST} " + right)
        if anchors is not None:
            anchors.append((W - vlen(right) - 2, 0, "raidbar"))
    else:
        cv.ansi_clip(0, 0, head + f"{NV2}{'─' * max(0, W - vlen(head))}{RST}", W)

    waits = [(sc, sm) for sc, sm in pets if sm.get("wait") and not sm.get("stale")]
    calls = [(sc, sm) for sc, sm in pets if sm.get("call")]
    if waits:
        tag = "PERM" if waits[0][1].get("wait_kind") == "perm" else "ASK"
        txt = " · ".join(f"{sm['name']}({sc}): {sm['wait']}" for sc, sm in waits)
        cv.ansi_clip(0, 1, (chip(tag, "black", "lime") if blink else chip(tag, "lime", "navy2")) + f" {WH}{B}응답 대기{RST} {G4}{txt}{RST}", W)
    elif calls:
        txt = " · ".join(f"{sm['name']}({sc}): {sm['call']}" for sc, sm in calls)
        cv.ansi_clip(0, 1, (chip("CALL", "black", "lime") if blink else chip("CALL", "lime", "navy2")) + f" {G4}{txt}{RST}", W)
    if not pets:
        cv.ansi_clip(0, 3, f"{G1}아직 펫이 없어요. 인스턴스 탭의 TOKEN QUEST 칸에서 알이 자라요.{RST}", W)
        return cv.lines()
    card_w = 32 if W >= 64 else W
    cols = max(1, W // card_w)
    if anchors is not None:
        anchors.append((card_w - 3, 2, "cards"))
    card_h = 7
    y0 = 2
    max_rows = max(1, (H - y0) // card_h)
    if len(pets) > max_rows * cols:
        max_rows = max(1, (H - y0 - 1) // card_h)
    shown = max_rows * cols
    for i, (sc, sm) in enumerate(pets):
        r, c = divmod(i, cols)
        x, y = c * card_w, y0 + r * card_h
        if i >= shown or y + card_h > H:
            cv.ansi_clip(0, H - 1, f"{G1}… 외 {len(pets) - i}마리 (창을 키우면 더 보여요){RST}", W)
            break
        stale = sm.get("stale")
        tag_hex = reg_colors.get(sc, P3["lime"])
        cv.box(x, y, card_w - 1, card_h, G0 if stale else NV2)
        lab = f" {bg(tag_hex)}{BLACK}{B}{i + 1:02d}{RST} {G4 if not stale else G1}{B}{sc}{RST} "
        cv.ansi_clip(x + 1, y, lab, card_w - 4)
        form = D.FORMS.get(sm.get("form"), D.FORMS["egg"])
        if sm.get("form") == "egg":
            art = form["art"][int(now * 1.5 + i) % 2]
        else:
            art = [ln.replace("{f}", sm.get("face", "o_o")) for ln in form["art"][int(now * 2 + i) % 2]]
        for j, ln in enumerate(art):
            cv.text(x + 1, y + 1 + j, ln, G0 if stale else rgb(form["color"]))
        ix = x + 13
        iw = card_w - 15
        gen = sm.get("gen", 1) or 1
        cv.ansi_clip(ix, y + 1, f"{rgb(form['color'])}{B}{sm['name']}{RST}", iw)
        # 레벨을 앞에 둬서 좁은 카드에서 'LV' 가 잘리지 않게
        cv.ansi_clip(ix, y + 2, f"{G1}LV{RST}{LIME}{B}{sm['lvl']}{RST} {G}{form['name']}{RST}" + (f" {G1}{gen}대{RST}" if gen > 1 else ""), iw)
        if sm.get("form") != "egg":
            mw = max(3, (iw - 6) // 2)
            cv.ansi_clip(ix, y + 3, f"{G1}포{RST}{meter(sm['full'], 100, mw, on=need_hex(sm['full']), knob=False)} "
                                    f"{G1}기{RST}{meter(sm['mood'], 100, mw, on=need_hex(sm['mood']), knob=False)}", iw)
        where = sm.get("where")
        if where == "exp":
            st = f"{chip('EXP', 'black', 'navy4')} {G4}{sm.get('zone')} B{sm.get('floor')}F{RST}"
        elif where == "raid":
            st = f"{chip('RAID', 'black', 'white')} {G4}싸우는 중{RST}"
        elif where == "story":
            st = f"{chip('BOSS', 'black', 'lime')} {G4}챕터 보스전{RST}"
        elif where == "sleep":
            st = f"{chip('zZ', 'navy4', 'navy1')} {G1}자는 중{RST}"
        elif stale:
            st = f"{chip('OFF', 'gray1', 'gray0')} {G1}창 꺼짐{RST}"
        else:
            st = f"{LIME}●{RST} {G}집{RST}"
        if sm.get("sick"):
            st += f" {chip(SICK_NAMES.get(sm['sick'], ''), 'black', 'white')}"
        if sm.get("call"):
            st = (chip("CALL", "black", "lime") if blink else chip("CALL", "lime", "navy2")) + f" {G4}{sm['call']}{RST}"
        if sm.get("wait") and not stale:
            tag = "PERM" if sm.get("wait_kind") == "perm" else "ASK"
            st = (chip(tag, "black", "lime") if blink else chip(tag, "lime", "navy2")) + f" {WH}{'허락 대기' if tag == 'PERM' else '질문 대기'}{RST}"
        cv.ansi_clip(ix, y + 4, st, iw)
        sp = sm.get("speech") or ""
        q = sm.get("quest") or {}
        if sp:
            cv.ansi_clip(x + 1, y + 5, f"{G}「{sp}」{RST}", card_w - 3)
        elif q.get("total") and not stale:
            cv.ansi_clip(x + 1, y + 5, f"{G1}QUEST{RST} {LIME}{q['done']}/{q['total']}{RST} {G}{q.get('cur') or ''}{RST}", card_w - 3)
        elif isinstance(sm.get("story"), dict):
            so = sm["story"]
            state = {"boss": f"{WH}◆ 보스{RST}", "wait": f"{LIME3}√ 다음 주{RST}", "end": f"{LIME}완결{RST}"}.get(
                so.get("phase"), f"{G1}{so.get('done', 0)}/{so.get('total', 0)}{RST}")
            cv.ansi_clip(x + 1, y + 5, f"{NV4}CH{so.get('ch', 1):02d}{RST} {G4}{so.get('title', '')}{RST} {state}", card_w - 3)
        else:
            cv.ansi_clip(x + 1, y + 5, f"{G1}KO{RST} {G4}{sm.get('kills', 0)}{RST} {G1}· TOKENS{RST} {G4}{P.fmt_num(sm.get('tok_today', 0))}{RST}", card_w - 3)
    return cv.lines()
