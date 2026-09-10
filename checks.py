#!/usr/bin/env python3
"""빌드 산출물 검사 — 조용히 틀리는 것을 빌드 시점에 멈춘다.

왜 따로인가 — build.py 는 "만든다", 여기는 "만든 것이 말이 되는가"를 본다.
검사는 업스트림이 바뀔 때마다 늘고 빌드 논리는 안 늘어서, 한 파일에 두면 검사가 빌드를 덮는다.

검사의 성격 — 여기 걸리는 것은 대부분 코드 버그가 아니라 **업스트림 변화**다.
그래서 메시지에 "어디를 보라"를 적는다. 멈추기만 하면 다음 사람이 원인을 다시 찾는다.
"""
from __future__ import annotations

from build import OTHER, PHASE, SUBMIT


def check(d: dict) -> None:
    s, c = d["series"], d["counts"]
    assert c["hf"] >= 20 and c["ccf"] >= 200 and c["rates"] >= 60, f"업스트림 fetch 실패 의심: {c}"
    ai = [x for x in s if x["group"] == "ai"]
    neuro = [x for x in s if x["group"] == "neuro"]
    assert len(ai) >= 24, f"AI 시리즈 {len(ai)}건 — TRACKED_AI 매칭 확인"
    assert len(neuro) >= 9, f"neuro 시리즈 {len(neuro)}건"
    # 차기 회차가 없어도 남는 것이 이 모델의 존재 이유다. 전형 시기가 비면 아무 값도 못 준다.
    for x in s:
        assert x["editions"], f"{x['title']}: 회차 0건"
        assert x["typical"]["meeting_month"], f"{x['title']}: 전형 개최월 유도 실패"
        assert x["tier"] in (1, 2, 3) and x["field"], f"{x['title']}: tier/field 누락"
    # 메이저는 업스트림 CORE 등급과 수동 h5 표에 함께 의존한다. 어느 쪽이 깨져도 조용히 틀린다.
    major = {x["title"] for x in s if x["major"]}
    for t in ("NeurIPS", "ICML", "ICLR", "CVPR", "ACL"):
        assert t in major, f"{t} 이 메이저에서 빠졌다 — CORE 등급·개최 주기·impact.yml 확인"
    # 전부 CORE A* 다. ECCV·ICCV 는 격년이라, 나머지는 h5 가 임계 아래라 빠진다.
    for t in ("ECCV", "ICCV", "AAAI", "EMNLP", "IJCAI", "ICRA", "SIGGRAPH", "RSS", "COLT"):
        assert t not in major, f"{t} 이 메이저에 들어왔다 — MAJOR_H5·annual 판정 확인"
    # 격년 판정이 조용히 뒤집히면 ECCV·ICCV 가 다시 들어온다. 판정 자체를 직접 잡는다.
    for t in ("ECCV", "ICCV"):
        assert not next(x for x in s if x["title"] == t)["annual"], f"{t} 이 매년 개최로 판정됐다"
    for t in ("CVPR", "NeurIPS", "ICML", "ICLR", "ACL"):
        assert next(x for x in s if x["title"] == t)["annual"], f"{t} 이 격년으로 판정됐다"
    # 이 컷은 ACL 236 과 AAAI 232 사이 4점 차에 얹혀 있다. 순서가 뒤집히면 조용히 틀리는 대신
    # 여기서 멈춘다 — Scholar 판을 갱신했을 때 사람이 다시 판단해야 하는 지점이다.
    h5 = {x["title"]: x["h5"] for x in s}
    assert h5["ACL"] > h5["AAAI"], \
        f"ACL({h5['ACL']}) <= AAAI({h5['AAAI']}) — 메이저 경계 근거가 무너졌다, 규칙 재검토 필요"
    assert len(major) == 5, f"메이저 {len(major)}건 (기대 5) — {sorted(major)}"
    # 메이저 5곳은 계층·트랙이 반드시 채워져 있어야 한다. 비면 화면에 빈 칸이 조용히 남는다.
    for x in s:
        if x["major"]:
            assert x["tiers"], f"{x['title']}: 발표 계층 미기재 — data/venues.yml"
            assert x["tracks"], f"{x['title']}: 트랙 미기재 — data/venues.yml (없으면 kind: none)"
            assert (x["review"] or {}).get("level") in ("open", "partial", "closed"), \
                f"{x['title']}: 리뷰 공개 수준 미기재 — data/venues.yml"
    for f in {"ml", "vision", "nlp", "robotics", "medical", "neuro", "neuroimaging", "cognitive"}:
        assert any(x["field"] == f and x["tier"] == 1 for x in s), f"분야 {f} 에 T1 학회가 없다"
    eds = [e for x in s for e in x["editions"]]
    located = [e for e in eds if e["lat"] is not None]
    # 좌표가 대량으로 비면 지도가 조용히 빈 화면이 된다. 캐시 미스는 prep.py --geo 로 채운다.
    assert len(located) / len(eds) > 0.85, \
        f"좌표 없는 회차 {len(eds)-len(located)}/{len(eds)} — python prep.py --geo 실행 필요"
    assert d["world"]["paths"], "world.json 비어 있음"
    # 개최일을 못 얻은 회차가 많으면 타임라인 막대가 길이 0으로 뭉개진다
    nodate = [e for e in eds if not e["start"]]
    assert len(nodate) / len(eds) < 0.1, \
        f"개최일 미상 회차 {len(nodate)}/{len(eds)} — parse_range 확인: {[e['date_text'] for e in nodate[:4]]}"
    # 화면이 모르는 일정 이름은 조용히 안 그려진다. 업스트림이 새 이름을 실어 오면
    # 여기서 멈춰 사람이 어휘에 넣을지 판단하게 한다 (SUBMIT·PHASE = 파일 머리 참조).
    seen = {t for e in eds for t in (dl["type"] for dl in e["deadlines"])}
    assert not (seen - SUBMIT - PHASE - OTHER), \
        f"모르는 일정 이름 {sorted(seen - SUBMIT - PHASE - OTHER)} — build.py 의 SUBMIT/PHASE 에 넣을지 판단"
    # 메이저의 차기 회차는 심사 구간을 그릴 수 있어야 한다. 마감만 있고 통보가 없으면 표식만 남는다.
    for x in s:
        if x["major"] and x["next"]:
            nx = next(e for e in x["editions"] if e["year"] == x["next"])
            if not any(d["type"] == "notification" for d in nx["deadlines"]):
                print(f"    ⚠️  {x['title']} {x['next']}: 통보일 미상 — 심사 막대 대신 마감 표식만")
    ws = [x for x in s if x["kind"] != "conference"]
    assert len(ws) >= 3, f"워크샵·트랙 {len(ws)}건 — workshops.yml 로드 확인"
    assert all(x["parent"] and x["kind"] in ("workshop", "track") for x in ws), "워크샵 parent/kind 미지정"
    no_next = [x["title"] for x in s if not x["next"]]
    print(f"OK  AI {len(ai)} · neuro {len(neuro)} · 차기 미공지 {len(no_next)}건({', '.join(no_next[:6])})")

