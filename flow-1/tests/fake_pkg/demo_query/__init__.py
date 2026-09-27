"""가짜 사내 쿼리 패키지 — Flow–1 테스트 · 데모용 (진짜 DB 에 붙지 않는다 · 표준 라이브러리만 · 이름도 지어낸 것)

진짜 사내 패키지의 이름 · 함수는 설치할 때 설정(query.modules · query.calls)에 넣는다 (docs/GUIDE.md › 05).
"""
import re
import time

DELAY = 0.01          # 쿼리 하나에 걸리는 척하는 시간 (초)


class Frame:
    """판다스 DataFrame 흉내 — 모양(shape)과 흐름에 필요한 메서드 몇 개만"""

    def __init__(self, rows=0, cols=0):
        self.shape = (rows, cols)

    def merge(self, other, **kw):
        return Frame(min(self.shape[0], other.shape[0]), self.shape[1] + other.shape[1])

    def to_csv(self, *a, **kw):
        return None


def query(sql, **kw):
    if "FAIL" in sql:
        raise RuntimeError("pwd=fake-not-real 로 연결하지 못했습니다")   # 오류 글의 비밀번호 꼴은 기록에서 가려져야 한다
    time.sleep(float(kw.get("delay", DELAY)))
    m = re.search(r"LIMIT (\d+)", sql)
    head = sql.upper().split("FROM")[0]
    return Frame(int(m.group(1)) if m else 3, head.count(",") + 1)


def execute(sql):
    time.sleep(DELAY)


def connect(env="dev"):
    return Client(env)


class Client:
    def __init__(self, env="dev"):
        self.env = env

    def fetch(self, sql):
        return query(sql)
