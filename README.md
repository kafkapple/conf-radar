# 학회 레이더 (conf-radar)

AI + 뇌과학/계산신경과학/NeuroAI + 국내(KSBNS) 학회의 **제출 마감·개최 일정**을 한 화면에서 본다.

- 웹 뷰어 = `docs/index.html` 파일 하나. 서버·빌드체인·런타임 의존성 없음.
- 모바일 = 같은 URL 을 아이폰 사파리에서 **공유 → 홈 화면에 추가**. `manifest.webmanifest` +
  `apple-touch-icon` 이 있어 전체화면 앱처럼 뜬다.
- 뷰 5개: **목록**(D-day) · **칸반**(임박도 5열) · **표**(고밀도) · **연간 사이클**(전형 주기 격자) · **정보원**
- 정렬 7종: 마감 · 개최일 · 규모 · 티어 · CORE 등급 · 전형 주기 · 분야
- 필터: 그룹 · 티어 · ★즐겨찾기(localStorage) · 제출 마감만 · 검색

## 단위 = 회차가 아니라 학회 시리즈

차기 회차가 아직 공지되지 않은 학회(ICML·ICCV·AISTATS 등)도 목록에 남는다.
과거 3-6년 회차에서 **전형 마감월·개최월**을 유도해 함께 보여준다.
표본 수(`n=`)를 항상 같이 찍으므로 약한 추정을 숨기지 않는다.

## 티어 기준

두 축의 조합이고, 객관 축은 우리가 정하지 않는다.

- **객관 축** = CORE 등급 (ccf-deadlines 가 실어 나르는 외부 정본). 신경과학 학회는 등급이
  부여되지 않아 분야 대표성으로 대신한다.
- **개인 축** = 연구 주제(3D 비전 · 행동/뇌 계측 · NeuroAI)와의 거리.
- **T1** = 둘 다 충족. **T2** = 한 축만. **T3** = 마감 캘린더용.
- 분야마다 T1 이 최소 하나 있는지 `build.py --check` 가 assert 로 강제한다.

## 데이터 출처 = 2계층

| 계층 | 대상 | 갱신 |
|---|---|---|
| 업스트림 | AI 학회 차기 마감 (`huggingface/ai-deadlines`) | 빌드 때 자동 fetch. **우리가 관리 안 함** |
| 업스트림 | 회차 이력 · CORE/CCF 등급 · 투고/채택 수 (`ccfddl/ccf-deadlines`) | 〃 |
| 자체 | 뇌과학 학회 `data/neuro.yml` | 수동. 뇌과학은 기계가독 피드가 존재하지 않음 |
| 자체 | 저널·학회 연계 제도 `data/programs.yml` | 수동. 확인한 것만 기록하고 미확인은 비워 둔다 |
| 자체 | 정보원 링크 `data/sources.yml` | 수동 |

`data/neuro.yml` 의 각 마감에는 `status` 가 붙는다.

- `confirmed` — 학회가 공식 공지한 날짜
- `estimated` — 과거 패턴 기반 추정 (뷰어에 "추정" 표시)
- `tba` — 아직 미공지 (뷰어에 "미공지" 표시)

**추정·미공지 표시가 붙은 마감은 반드시 학회 사이트에서 재확인할 것.**

## 사용

```bash
pip install pyyaml
python build.py --check      # 업스트림 fetch + 병합 + docs/index.html 생성
python build.py --offline    # 캐시된 업스트림으로 재빌드 (뷰어 수정 중일 때)
open docs/index.html
```

`sources.py` = 업스트림 읽기 전담, `build.py` = 합치기·유도·렌더. 갱신은 GitHub Actions 가
매일 05:00 KST 에 재빌드해 커밋한다.

## 데이터 추가

`data/neuro.yml` 에 항목을 추가한다. 스키마는 업스트림과 동일하며 `source`(근거 URL) 와
`verified`(확인 날짜) 는 필수다. **근거 URL 없는 날짜는 넣지 않는다.**

## 설계 근거

`PRD.md` — 특히 §7 "기각한 대안" (fork·스크래퍼·React 앱을 왜 안 썼는지).
