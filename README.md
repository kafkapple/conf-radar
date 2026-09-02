# 학회 레이더 (conf-radar)

AI + 뇌과학/계산신경과학/NeuroAI + 국내(KSBNS) 학회의 **제출 마감·개최 일정**을 한 화면에서 본다.

- 웹 뷰어 = `docs/index.html` 파일 하나. 서버·빌드체인·의존성 없음.
- 모바일 = 같은 URL 을 아이폰 사파리에서 홈 화면에 추가 (PWA 메타 포함).
- 뷰 2개: **마감 목록**(D-day 정렬) · **연간 사이클**(12개월 격자에 마감●·개최■).

## 데이터 출처 = 2계층

| 계층 | 대상 | 갱신 |
|---|---|---|
| 업스트림 | AI 학회 (`huggingface/ai-deadlines`) | 빌드 때 자동 fetch. **우리가 관리 안 함** |
| 자체 | 뇌과학 학회 `data/neuro.yml` | 수동. 뇌과학은 기계가독 피드가 존재하지 않음 |

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

## 데이터 추가

`data/neuro.yml` 에 항목을 추가한다. 스키마는 업스트림과 동일하며 `source`(근거 URL) 와
`verified`(확인 날짜) 는 필수다. **근거 URL 없는 날짜는 넣지 않는다.**

## 설계 근거

`PRD.md` — 특히 §7 "기각한 대안" (fork·스크래퍼·React 앱을 왜 안 썼는지).
