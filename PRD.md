# conf-radar — PRD (260902)

> AI + 뇌과학/NeuroAI 학회 마감·일정 단일 뷰어. 웹 + 모바일(PWA).

## 0. Open issues

- [ ] neuro 데이터 갱신 주체 = 수동. 자동 소스 없음 (§2 제약)
- [ ] Cosyne 2027 초록 마감 = 추정치(2026-10 중순). 공지 나오면 `status: confirmed` 로 승격
- [ ] 네이티브 iOS 껍데기(Phase 3) 착수 여부 미결 — PWA 로 충분한지 1개월 사용 후 판단

## 1. 문제

- AI 학회 마감 = `aideadlin.es`(HF Space) 등 기존 서비스로 이미 해결됨.
- 뇌과학·계산신경과학·NeuroAI·국내(KSBNS) 학회 = **기존 집계 서비스 어디에도 없음**.
  - 실측: `huggingface/ai-deadlines` 68개 학회 중 cosyne·ccn·sfn·ohbm·vss·cogsci **0건**.
  - `ccfddl/ccf-deadlines` = CS 분야 CCF 등급 기준, 신경과학 미포함.
- 두 세계를 한 화면에서 보는 수단이 없어 매번 개별 사이트 순회.

## 2. 제약 (조사로 확인된 사실 — 설계를 여기에 맞춘다)

| 사실 | 설계 귀결 |
|---|---|
| AI 학회 = 기계가독 YAML 존재 (HF 리포, 260901 갱신) | 우리가 관리 안 함. 빌드 때 업스트림 그대로 fetch |
| 뇌과학 학회 = 피드 없음. 사이트마다 HTML, 상당수 "TBA" | 수동 YAML 1개가 유일한 방법. 스크래핑은 과설계 |
| 마감일이 확정 전에도 과거 패턴은 안정적 (Cosyne 마감 = 매년 10월 중순) | `status: confirmed / estimated / tba` 3값을 1급 필드로 |
| 학회는 연 1회 고정 주기 | 요구사항 (1) "보편 타임라인" = 데이터에서 월(month) 유도, 별도 입력 불필요 |

## 3. 범위

**In**: 뇌과학 계열 수동 큐레이션(≈10건) · AI 업스트림 병합 · 연간 사이클 시각화 · D-day 목록 · 반응형 웹 + PWA.
**Out (YAGNI)**: 로그인, 알림 푸시, 서버, DB, 스크래핑, 캘린더 동기화, 사용자별 즐겨찾기 서버 저장.

## 4. 아키텍처 (모듈 경계 = 소유자 기준)

```
업스트림 (남이 관리)        우리가 관리            산출물
huggingface/ai-deadlines --\
  src/data/conferences/*.yml \
                             >-- build.py --> docs/index.html (데이터 인라인)
data/neuro.yml (수동, 동일 스키마) /              단일 파일 = 웹·PWA·file:// 전부 동작
```

- **스키마 = 업스트림 것을 그대로 채택.** 자체 스키마 정의 안 함 → 변환 코드 0줄.
- **데이터 인라인** 이유: `fetch()` 를 쓰면 `file://` 에서 CORS 로 죽고 서버가 필요해진다. 인라인이면 파일 하나로 어디서나 열린다.
- 갱신 = GitHub Actions 일 1회 `build.py` 재실행 → 커밋. 서버 0대.

## 5. 단계

| Phase | 산출물 | 완료 기준 |
|---|---|---|
| **P1** | `data/neuro.yml` + `build.py` + `docs/index.html` | 로컬에서 열어 두 뷰(사이클·목록) 동작, 뇌과학 10건 + AI 24건 표시 |
| **P2** | GitHub Pages + Actions cron | URL 로 접속, 매일 자동 갱신, 아이폰 홈화면 추가 |
| **P3 (조건부)** | WKWebView 껍데기 (`~/dev/mobile/apps/` 패턴 재사용) | P2 를 한 달 써보고 PWA 로 부족할 때만 |

## 6. 검증

- 날짜 정확성: 각 entry 에 `source` URL + `verified` 날짜 기록. 근거 없는 날짜 입력 금지.
- 회귀: `build.py --check` 가 (a) 업스트림 fetch 성공 (b) 필수 필드 존재 (c) 과거 학회 D-day 음수 처리 를 assert.

## 7. 기각한 대안

| 대안 | 기각 사유 |
|---|---|
| ai-deadlines 를 fork 해 neuro 추가 | 업스트림 병합 부채. 우리 fetch 가 fork 를 안 보게 됨 |
| 스크래퍼로 학회 사이트 순회 | 10개 사이트 × 매년 개편 = 유지비가 수동 입력보다 비쌈. 연 10회 편집이 더 싸다 |
| React/Vite 앱 | 정적 표 1장에 빌드 체인 도입 = 과설계 |
| React Native 앱 신규 | 앱스토어·서명·배포가 본질 아님. 내용은 웹페이지 |
