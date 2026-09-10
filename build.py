#!/usr/bin/env python3
"""conf-radar 빌드 — 학회 '시리즈' 단위로 여러 출처를 합쳐 단일 HTML 을 만든다.

설계 메모:
- 단위는 회차(edition)가 아니라 시리즈(conference series)다. 차기 회차가 아직 공지되지 않은
  학회(ICML·ACL·ICCV 등)도 과거 회차에서 유도한 전형 시기와 함께 남는다. 회차 단위로 두고
  신선도로 걸러내면 이런 학회가 목록에서 통째로 사라진다.
- 업스트림 읽기는 sources.py 가 맡는다. 여기는 합치기·유도·렌더만 한다.
- 데이터를 HTML 에 인라인한다. fetch() 를 쓰면 file:// 에서 CORS 로 죽고 서버가 필요해진다.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from ics import build_ics
from sources import (DISPLAY, FIELD_AI, PAPERCOPILOT, TRACKED_AI, canon,
                     editions_from_ccf, editions_from_hf, fetch, month_of,
                     rates_from_ccf, valid)

ROOT = Path(__file__).parent
DATA = ROOT / "data"

# 회차 일정 어휘 — 이름은 ccf-deadlines 가 쓰는 것을 그대로 쓴다. 우리가 따로 지으면
# 업스트림이 나중에 같은 사실을 실어 올 때 같은 뜻의 이름이 둘 공존한다.
#
# SUBMIT = 저자가 "내야 하는" 날. PHASE = 낸 뒤에 흐르는 심사 단계의 경계.
# 화면의 심사 막대는 이 경계들 사이를 구간으로 잘라 그린다 — 어느 구간이 저자가 일하는
# 때(리버틀·최종본)이고 어느 구간이 기다리는 때인지가 투고 계획의 핵심이다.
SUBMIT = {"abstract", "paper", "submission", "supplementary", "abstract_late", "registration"}
PHASE = {"review_release", "rebuttal_start", "rebuttal_end", "author_response",
         "rebuttal_and_revision", "notification", "commitment_deadline",
         "withdrawal", "camera_ready"}
# 저자와 무관한 날. 어휘에는 두되 화면에는 안 쓴다 — 빼면 assert 가 매번 걸린다.
OTHER = {"reviewer_registration"}

# 메이저 = 세 조건의 교집합 — CORE A* 등급 ∩ 매년 개최 ∩ Google Scholar h5-index >= 237.
# 결과 5곳: CVPR 450 · NeurIPS 371 · ICLR 362 · ICML 272 · ACL 236.
#
# 왜 셋인가 — 어느 하나만으로는 틀린다.
#   CORE 만: 4단계뿐이라 A* 안의 격차를 못 나타낸다(COLT 와 NeurIPS 371 이 같은 칸).
#   h5 만: 규모 편향이 등급 자리를 차지한다(data/impact.yml 의 한계 3가지).
#   매년 개최만: 주기는 급을 뜻하지 않는다. 순위 조건과 같이 써야 의미가 있다.
#
# 매년 개최 조건은 260910 사용자 결정이다. 이 뷰어의 용도가 "언제 준비를 시작할 것인가"라
# 격년 학회(ECCV 짝수 해 · ICCV 홀수 해)는 해마다 도는 달력에 안 맞는다. 급이 낮아서가
# 아니다 — ECCV 262 · ICCV 256 은 ACL 236 보다 위다.
#
# 손으로 빼는 항목은 없다. 세 조건이 전부 가른다.
#
# 🔴 이 임계는 둔감하지 않다. 위 여유는 크지만(ICML 272 까지 36) 아래가 ACL 236 · AAAI 232 로
# 간격이 4뿐이다. 233~236 만이 ACL 을 넣고 AAAI 를 빼며, Scholar 판이 바뀌어 둘의 순서가
# 뒤집히면 결과가 뒤집힌다. 앞선 컷들(문턱 200·250)은 간격 20 이상이었고 이건 다르다.
# 그래서 check() 가 ACL > AAAI 관계 자체를 assert 로 잡는다 — 뒤집히면 빌드가 실패한다.
MAJOR_H5 = 236


MON = {m[:3]: i for i, m in enumerate(
    "january february march april may june july august september october november december".split(), 1)}
RANGE = re.compile(r"([A-Za-z]{3,})\.?\s*(\d{1,2})\s*[-–~]\s*(?:([A-Za-z]{3,})\.?\s*)?(\d{1,2})")
ONE = re.compile(r"([A-Za-z]{3,})\.?\s*(\d{1,2})\b")


def parse_range(text: str, year: int) -> tuple[str, str]:
    """'May 16-21, 2027' → ('2027-05-16', '2027-05-21').

    ccf 출신 회차는 ISO 날짜가 없고 자유 문장만 있다. 그대로 두면 타임라인에서 막대가
    길이 0으로 뭉개지고 표에는 개최일이 '—' 로 뜬다. 유도 실패하면 빈 문자열을 돌려준다.
    """
    t = (text or "").replace("\u2013", "-")
    m = RANGE.search(t)
    try:
        if m:
            m1 = MON.get(m.group(1)[:3].lower())
            m2 = MON.get((m.group(3) or m.group(1))[:3].lower())
            if not (m1 and m2):
                return "", ""
            y2 = year + 1 if m2 < m1 else year          # 12월 → 1월 같은 연말 걸침
            return (f"{year}-{m1:02d}-{int(m.group(2)):02d}", f"{y2}-{m2:02d}-{int(m.group(4)):02d}")
        m = ONE.search(t)
        if m and (mo := MON.get(m.group(1)[:3].lower())):
            d = f"{year}-{mo:02d}-{int(m.group(2)):02d}"
            return d, d
    except ValueError:
        pass
    return "", ""


# 같은 마감이 시간대 표기만 달라 두 번 들어온다. ccf 는 AoE 마감을 UTC+0 으로 환산해 싣기
# 때문에 하루 뒤 날짜가 같이 오고, 뷰어에는 "초록 05-04"와 "초록 05-05"가 나란히 뜬다
# (260910 사용자 신고: "마감이 이상한데"). 종류가 같고 이틀 안쪽이면 이른 쪽 하나만 남긴다 —
# AoE 표기가 곧 그 이른 날짜다.
KIND = {"paper": "paper", "submission": "paper"}


def dedupe_deadlines(dls: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: dict[str, str] = {}
    for d in sorted(dls, key=lambda x: x["date"]):
        k = KIND.get(d["type"], d["type"])
        prev = seen.get(k)
        if prev and (date.fromisoformat(d["date"]) - date.fromisoformat(prev)).days <= 2:
            continue
        seen[k] = d["date"]
        out.append(d)
    return out


def merge_editions(a: list[dict], b: list[dict]) -> list[dict]:
    """연도별로 합치되 hf(차기·상세) 가 ccf(이력) 를 이긴다. 마감은 합집합."""
    by_year: dict[int, dict] = {}
    for e in sorted(a + b, key=lambda e: (e["year"], e["src"] == "hf")):
        y = e["year"]
        if y not in by_year:
            by_year[y] = e
            continue
        keep, drop = by_year[y], e
        if drop["src"] == "hf":                      # hf 가 나중 = 우선
            keep, drop = drop, keep
        seen = {(d["type"], d["date"]) for d in keep["deadlines"]}
        keep["deadlines"] += [d for d in drop["deadlines"] if (d["type"], d["date"]) not in seen]
        keep["deadlines"] = dedupe_deadlines(keep["deadlines"])
        for k in ("date_text", "city", "venue", "link", "start", "end"):
            keep[k] = keep.get(k) or drop.get(k, "")
        by_year[y] = keep
    return sorted(by_year.values(), key=lambda e: e["year"])


def annual(eds: list[dict]) -> bool:
    """회차 연도에 연속한 쌍이 하나라도 있으면 매년 개최로 본다.

    격년(ECCV 짝수 해 · ICCV 홀수 해)은 연속 쌍이 절대 안 생긴다. 표본이 1건뿐이면
    판정할 수 없으므로 False 를 준다 — 매년일 수도 있으니 메이저에서 빠지는 쪽이 안전하다.
    """
    ys = {e["year"] for e in eds}
    return any(y + 1 in ys for y in ys)


def typical(eds: list[dict]) -> dict:
    """과거 회차에서 전형 시기를 유도한다. 표본 수를 함께 내보내 약한 추정을 숨기지 않는다."""
    dmonths, mmonths, years = [], [], []
    for e in eds:
        subs = [d for d in e["deadlines"] if d["type"] in SUBMIT and d["status"] == "confirmed"]
        if subs:
            dmonths.append(int(subs[0]["date"][5:7]))
        mm = int(e["start"][5:7]) if e["start"] else month_of(e["date_text"])
        if mm:
            mmonths.append(mm)
            years.append(e["year"])
    pick = lambda xs: Counter(xs).most_common(1)[0][0] if xs else None
    return {"deadline_month": pick(dmonths), "meeting_month": pick(mmonths),
            "n_deadline": len(dmonths), "n_meeting": len(mmonths),
            "years": [min(years), max(years)] if years else None}


def build_series(title, eds, group, tier, field, rank, rates, programs, extra, today) -> dict:
    eds = [e for e in eds if e["year"] >= today.year - 6]
    def ends(e: dict) -> str:
        if e["end"] or e["start"]:
            return e["end"] or e["start"]
        m = month_of(e["date_text"])
        return f"{e['year']}-{m:02d}-28" if m else f"{e['year']}-12-31"
    nxt = next((e for e in eds if ends(e) >= today.isoformat()), None)
    slug = next((e.get("slug") for e in eds if e.get("slug")), title.lower())
    links = []
    if slug in PAPERCOPILOT:
        links.append(["통계·추세", f"https://papercopilot.com/statistics/{slug}-statistics/"])
    if group == "ai":
        links += [["OpenReview", f"https://openreview.net/search?query={title}"],
                  ["역대 수상 논문", "https://jeffhuang.com/best_paper_awards/"]]
    hist = rates.get(title, [])
    scale = extra.get("scale") or (
        {"metric": "submitted", "value": hist[-1]["submitted"], "year": hist[-1]["year"],
         "source": hist[-1]["source"]} if hist else None)
    r = rank.get(title, {})
    return {
        "id": slug if group == "ai" else extra.get("id", slug),
        "title": DISPLAY.get(title, title), "full_name": extra.get("full_name", ""), "group": group,
        "tier": tier, "field": field, "rank": r,
        "link": (nxt or eds[-1])["link"] if eds else extra.get("link", ""),
        "editions": eds, "next": nxt["year"] if nxt else None,
        "typical": typical(eds), "scale": scale, "history": hist,
        "programs": programs.get(title, []), "links": links,
        "kind": "conference", "parent": "",
        "source": extra.get("source", ""), "verified": str(extra.get("verified", "")),
    }


def build(offline: bool = False) -> dict:
    today = date.today()
    hf_tf, ccf_tf = fetch("hf", offline), fetch("ccf", offline)
    hf_eds = editions_from_hf(hf_tf)
    ccf_eds, rank = editions_from_ccf(ccf_tf)
    rates = rates_from_ccf(ccf_tf)
    programs = {canon(k): v for k, v in (yaml.safe_load((DATA / "programs.yml").read_text()) or {}).items()}
    geo = yaml.safe_load((DATA / "geo.yml").read_text()) or {}

    series = []
    for slug, tier in sorted(TRACKED_AI.items()):
        title = next((t for t, es in hf_eds.items() if any(e.get("slug") == slug for e in es)), None)
        title = title or next((t for t in ccf_eds if t.lower().replace(" ", "") == slug), None)
        if title is None:
            continue
        eds = merge_editions(hf_eds.get(title, []), ccf_eds.get(title, []))
        series.append(build_series(title, eds, "ai", tier, FIELD_AI.get(slug, "ml"),
                                   rank, rates, programs, {}, today))

    manual = (yaml.safe_load((DATA / "neuro.yml").read_text()) or []) + \
             (yaml.safe_load((DATA / "workshops.yml").read_text()) or [])
    for e in manual:
        DISPLAY[canon(e["title"])] = e["title"]
        eds = merge_editions([{
            "year": int(e["year"]), "start": str(e.get("start", "")), "end": str(e.get("end", "")),
            "date_text": e.get("date", ""), "city": e.get("city", ""), "country": e.get("country", ""),
            "venue": e.get("venue", ""), "link": e.get("link", ""), "src": "manual",
            "deadlines": valid([{"type": d.get("type", "abstract"), "label": d.get("label", ""),
                                 "date": str(d["date"])[:10], "t": str(d["date"])[11:19], "tz": d.get("timezone", ""),
                                 "status": d.get("status", "confirmed")} for d in e.get("deadlines") or []]),
        }], [{
            "year": int(p["year"]), "start": "", "end": "", "date_text": p.get("date", ""),
            "city": p.get("place", ""), "country": "", "venue": p.get("place", ""),
            "link": e.get("link", ""), "src": "manual",
            "deadlines": valid([{"type": "abstract", "label": "Abstract deadline",
                                 "date": str(p["deadline"])[:10], "t": "", "tz": "", "status": "confirmed"}]
                               if p.get("deadline") else []),
        } for p in e.get("past") or []])
        s = build_series(canon(e["title"]), eds, "neuro", int(e["tier"]), e["field"],
                         rank, rates, programs, e, today)
        s["id"], s["link"] = e["id"], e["link"]
        s["kind"] = e.get("kind", "conference")
        s["parent"] = e.get("parent", "")
        if s["kind"] != "conference":
            s["group"] = next((x["group"] for x in series if x["title"] == e.get("parent")), "ai")
        series.append(s)

    for s in series:                                     # ISO 날짜가 없으면 자유 문장에서 유도
        for e in s["editions"]:
            if not e["start"]:
                e["start"], e["end"] = parse_range(e["date_text"], e["year"])
                e["date_src"] = "text" if e["start"] else "none"
            else:
                e.setdefault("date_src", "iso")

    for s in series:                                     # 회차마다 좌표를 붙인다(지도 뷰)
        for e in s["editions"]:
            place = ", ".join(x for x in [e.get("city", ""), e.get("country", "")] if x) or e.get("venue", "")
            hit = geo.get(place.strip())
            e["place"] = place.strip()
            e["lat"], e["lon"] = (hit["lat"], hit["lon"]) if hit else (None, None)

    impact = yaml.safe_load((DATA / "impact.yml").read_text())
    venues = yaml.safe_load((DATA / "venues.yml").read_text())
    for s in series:
        # 발표 계층과 별도 트랙은 업스트림이 안 나른다. 투고처를 고를 때는 총 채택률보다 결정적이다.
        v = venues.get(s["title"]) or {}
        s["tiers"] = v.get("tiers", [])
        s["tier_note"] = v.get("tier_note", "")
        s["tier_counts"] = v.get("tier_counts", [])
        s["tracks"] = v.get("tracks", [])
        # 리뷰 공개 수준 = open / partial / closed. 투고처를 고를 때 트랙만큼 갈리는 축이다.
        s["review"] = v.get("review")
        # 업스트림이 아직 안 실어 온 회차 일정을 공식 페이지 직독분으로 채운다.
        for extra_dl in v.get("deadlines", []):
            ed = next((e for e in s["editions"] if e["year"] == extra_dl["year"]), None)
            if ed is None:
                continue
            row = {"type": extra_dl["type"], "label": extra_dl.get("label", extra_dl["type"]),
                   "date": str(extra_dl["date"])[:10], "t": str(extra_dl["date"])[11:19],
               "tz": extra_dl.get("timezone", ""),
                   "status": "confirmed"}
            if not any(d["type"] == row["type"] and d["date"] == row["date"] for d in ed["deadlines"]):
                ed["deadlines"] = sorted(ed["deadlines"] + [row], key=lambda d: d["date"])
        # 손으로 확인한 수치(근거 URL 동반)가 집계기보다 우선한다. 같은 해가 둘 다 있으면 덮는다.
        for tc in s["tier_counts"]:
            if not (tc.get("submitted") and tc.get("accepted")):
                continue
            row = {"year": tc["year"], "submitted": tc["submitted"], "accepted": tc["accepted"],
                   "rate": tc.get("rate") or round(tc["accepted"] / tc["submitted"], 4),
                   "source": tc["source"]}
            s["history"] = [h for h in s["history"] if h["year"] != row["year"]] + [row]
        s["history"].sort(key=lambda h: h["year"])
        # 규모 막대는 history 의 최신 해를 쓴다. 위에서 해를 더했으면 다시 잡아야 한다.
        if s["history"] and s["group"] == "ai":
            h = s["history"][-1]
            s["scale"] = {"metric": "submitted", "value": h["submitted"],
                          "year": h["year"], "source": h["source"]}

    for s in series:
        # 손으로 학회를 더하지 않는다. 두 외부 정본이 동의하는 것만 메이저다.
        s["h5"] = impact["h5"].get(s["title"])
        s["annual"] = annual(s["editions"])
        s["major"] = (s["rank"].get("core") == "A*" and s["annual"]
                      and (s["h5"] or 0) >= MAJOR_H5)

    for s in series:                                     # 도시/국가는 차기 회차 것을 대표로
        nx = next((x for x in s["editions"] if x["year"] == s["next"]), None) or (s["editions"][-1] if s["editions"] else {})
        s.update(city=nx.get("city", ""), country=nx.get("country", ""), venue=nx.get("venue", ""),
                 date_text=nx.get("date_text", ""), start=nx.get("start", ""), end=nx.get("end", ""),
                 deadlines=nx.get("deadlines", []), next_year=nx.get("year"),
                 # 사이클 뷰는 '전형 개최월'을 쓴다 — 차기 회차가 없는 학회도 자리를 갖는다
                 start_month=s["typical"]["meeting_month"],
                 # 트랙 이름도 검색어에 넣는다 — "포지션"·"Findings" 로 바로 걸러진다
                 search=" ".join([s["title"], s["full_name"], nx.get("city", ""),
                                  nx.get("country", ""), s["field"],
                                  s["rank"].get("core", ""),
                                  {"open": "공개리뷰 openreview", "partial": "부분공개",
                                   "closed": "비공개"}.get((s["review"] or {}).get("level"), "")]
                                 + [t["name"] for t in s["tracks"]]).lower())

    data = {"generated": today.isoformat(), "series": series,
            "world": json.loads((DATA / "world.json").read_text()),
            "sources": yaml.safe_load((DATA / "sources.yml").read_text()),
            "counts": {"hf": len(hf_eds), "ccf": len(ccf_eds), "rates": len(rates)}}
    # 날짜 단위로 찍는다. 초 단위면 데이터가 그대로여도 .ics 가 매 빌드 달라져서, Actions 가
    # 밀어야 할 변경이 없는데도 커밋을 만들고 그 커밋 때문에 다음 푸시가 매번 막힌다(260910 실측).
    stamp = today.strftime("%Y%m%dT000000Z")
    (ROOT / "docs" / "deadlines.ics").write_text(build_ics(series, stamp), newline="")
    # 위젯·단축어가 읽을 기계가독 사본. 뷰어는 인라인 데이터를 쓰므로 이 파일에 의존하지 않는다.
    (ROOT / "docs" / "data.json").write_text(json.dumps(
        {"generated": data["generated"],
         "series": [{k: s[k] for k in ("id","title","group","tier","field","link","city","country",
                                        "date_text","start","end","next","deadlines","typical")}
                    for s in series]}, ensure_ascii=False, separators=(",", ":")))
    tpl = (ROOT / "template.html").read_text()
    assert "__DATA__" in tpl, "template.html 에 __DATA__ 자리표시자가 없다"
    html = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    (ROOT / "docs" / "index.html").write_text(html)
    # Claude Artifact 는 head/body 를 자기가 감싸므로 껍데기만 벗긴 조각도 같이 낸다(템플릿은 하나).
    (ROOT / "docs" / "artifact.html").write_text(
        html[html.index("<title>"):html.index("</head>")] +
        html[html.index("<body>") + 6:html.rindex("</body>")])
    return data


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--offline", action="store_true", help="캐시된 업스트림 tarball 사용")
    p.add_argument("--check", action="store_true", help="빌드 후 assert 검사")
    a = p.parse_args()
    d = build(a.offline)
    if a.check:
        from checks import check   # 순환 import 를 피해 여기서 부른다
        check(d)
    print(f"docs/index.html  ({len(d['series'])} series, generated {d['generated']})")
