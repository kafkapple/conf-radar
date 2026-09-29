# conf-radar 사건·잔여·사고 기록

> 260930 `~/.agent/notes/projects/conf-radar.md` 크기 cap 초과로 이관. 원문 그대로.

## [사건 260910 — 잠복 버그 둘, 데이터를 늘리자 튀어나왔다]
- **마감 시각을 빌드가 잘라 버리고 있었다.** `str(d["date"])[:10]` 로 날짜만 싣고 시각은 버렸다.
  시간대 환산을 하려니 그제야 드러났다 → `t` 필드로 보존
- **`month_of` 가 `re.search(pat, text, m.end())`.** 세 번째 인자는 pos 가 아니라 flags 다.
  `"Fall 2024"`(끝 4 = `re.LOCALE`)에서 ValueError. 국내 학회 date_text 를 넣기 전까지
  맞는 오프셋이 안 나와 잠복해 있었다 → `re.finditer`
- 둘 다 **기존 데이터로는 안 걸리는** 버그였다. 수록 범위를 넓히는 것이 곧 테스트였다

## [사건 260910 — .ics DTSTAMP 가 푸시를 막고 있었다]
`stamp` 를 초 단위로 찍어 데이터가 그대로여도 매 빌드 `.ics` 가 달라졌다. 그래서 Actions 가
밀 변경이 없는데도 `chore: rebuild` 커밋을 만들고, 그 커밋 때문에 다음 푸시가 매번 non-ff 로
막혔다(두 번 연속 rebase). 날짜 단위(`%Y%m%dT000000Z`)로 바꿔 해소 — 이후 푸시에서 CI 가
커밋을 안 만드는 것 확인.

## [사건 260910 — 공개본이 8일 멈춰 있었다]
Pages 소스가 `gh-pages` 브랜치인데 Actions 워크플로는 `main` 에만 커밋했다. 매일 재빌드가
돌아도 공개본에 도달하지 못한다. 배포 단계를 워크플로에 추가해 해소(260910 실측 반영 확인).
**해소(260920)**: 원인 = 저장소 **기본 브랜치가 `gh-pages`**였다(260910 당시 "기본 브랜치 맞음"으로
적었던 확인이 틀렸다 — 실제로 안 봤던 것). GitHub Actions `schedule` 트리거는 워크플로 파일이 있는
브랜치가 아니라 **저장소 기본 브랜치**에서만 등록된다. push 트리거는 브랜치 무관이라 그동안 살아있는
것처럼 보였을 뿐. `gh repo edit --default-branch main` 으로 정정, Pages 소스는 `gh-pages` 그대로라
배포 경로 영향 없음. 다음 05:00 KST 스케줄 실행이 실제로 찍히는지는 `gh run list --workflow=update.yml`
로 하루 뒤 재확인.

## [잔여 260902]
- DevAI(NeurIPS 2026 Atlanta) 마감·URL 미확인 → 타겟이면 `workshops.yml` 한 블록
- BabyVLM 마감 시각·시간대가 사이트에 없어 AoE 가정 — 확인 필요
- 추정 마감 6건(Cosyne·OHBM·VSS·CogSci·CNS*·CCN) → 공지 나오면 `estimated`→`confirmed`
- 뇌과학 규모 6건 미상 · 투고 시계열 학회당 1-4년치(10년 추세 불가)
- 미검증 = 실제 아이폰에서의 홈화면추가·오프라인·캘린더구독·위젯 (데스크톱까지만 확인)

## [사고 기록 — 재발 방지]
- accept_rates 색인 키는 파일명이 아니라 YAML `title` (`nips.yml` → `NeurIPS`). 파일명 매칭으로 NeurIPS 이력 전체 누락
- 두 업스트림의 대소문자 차이(`Interspeech` vs `INTERSPEECH`)로 한 학회가 두 시리즈로 분리
- Nominatim 이 `Virtual` 을 러시아 실제 지명으로 찍음 → `prep.py` 에 virtual/online/remote 차단
- ccf 회차 75건에 ISO 날짜 없음 → `parse_range` 로 `date_text` 에서 유도(미상 2건까지)
- `.fill` 이 inline span 이라 `width` 가 안 먹어 규모 막대가 통째로 안 보였다
