# 문서 뼈대

새 앱은 여기서 시작한다 ([RULES.md › 새 앱 만드는 순서](../../RULES.md#새-앱-만드는-순서)).

```text
docs/templates/
├─ app/                  → 저장소 루트의 <name>-<n>/ 로 복사
│  ├─ README.md          소개 페이지 (OP–1 식)
│  ├─ INSTALL.md         opencode 가 따라 하는 설치 절차
│  ├─ docs/MANUAL.md     매뉴얼
│  ├─ .gitignore
│  └─ .gitattributes
└─ workflow.yml          → .github/workflows/<name>-<n>.yml 로 복사
```

복사한 뒤 자리표시자를 바꾼다.

| 자리표시자 | 뜻 | 예 |
|---|---|---|
| `{{NAME}}` | 화면 이름 (en dash) | `Secretary–1` |
| `{{APP}}` | 폴더 · 명령 · 파일 이름 | `secretary-1` |
| `{{TAGLINE}}` | 한 줄 소개 | `말하면 잡아 주는 일정 비서` |
| `{{ENV}}` | 환경 변수 접두어 | `SECRETARY` |

`<!-- … -->` 주석은 채우는 법 설명이다. 다 채우면 지운다.
`python tools/works_check.py` 는 자리표시자 `{{…}}` 가 남은 앱 문서를 알려 준다.
