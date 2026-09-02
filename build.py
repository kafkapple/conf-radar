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
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

from sources import (DISPLAY, FIELD_AI, PAPERCOPILOT, TRACKED_AI, canon,
                     editions_from_ccf, editions_from_hf, fetch, month_of,
                     rates_from_ccf, valid)

ROOT = Path(__file__).parent
DATA = ROOT / "data"

SUBMIT = {"abstract", "paper", "submission", "supplementary", "abstract_late"}


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
        keep["deadlines"].sort(key=lambda d: d["date"])
        for k in ("date_text", "city", "venue", "link", "start", "end"):
            keep[k] = keep.get(k) or drop.get(k, "")
        by_year[y] = keep
    return sorted(by_year.values(), key=lambda e: e["year"])


SUBMIT = {"abstract", "paper", "submission", "supplementary", "abstract_late"}


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
    return {
        "id": slug if group == "ai" else extra.get("id", slug),
        "title": DISPLAY.get(title, title), "full_name": extra.get("full_name", ""), "group": group,
        "tier": tier, "field": field, "rank": rank.get(title, {}),
        "link": (nxt or eds[-1])["link"] if eds else extra.get("link", ""),
        "editions": eds, "next": nxt["year"] if nxt else None,
        "typical": typical(eds), "scale": scale, "history": hist,
        "programs": programs.get(title, []), "links": links,
        "source": extra.get("source", ""), "verified": str(extra.get("verified", "")),
    }


def build(offline: bool = False) -> dict:
    today = date.today()
    hf_tf, ccf_tf = fetch("hf", offline), fetch("ccf", offline)
    hf_eds = editions_from_hf(hf_tf)
    ccf_eds, rank = editions_from_ccf(ccf_tf)
    rates = rates_from_ccf(ccf_tf)
    programs = {canon(k): v for k, v in (yaml.safe_load((DATA / "programs.yml").read_text()) or {}).items()}

    series = []
    for slug, tier in sorted(TRACKED_AI.items()):
        title = next((t for t, es in hf_eds.items() if any(e.get("slug") == slug for e in es)), None)
        title = title or next((t for t in ccf_eds if t.lower().replace(" ", "") == slug), None)
        if title is None:
            continue
        eds = merge_editions(hf_eds.get(title, []), ccf_eds.get(title, []))
        series.append(build_series(title, eds, "ai", tier, FIELD_AI.get(slug, "ml"),
                                   rank, rates, programs, {}, today))

    for e in yaml.safe_load((DATA / "neuro.yml").read_text()) or []:
        DISPLAY[canon(e["title"])] = e["title"]
        eds = merge_editions([{
            "year": int(e["year"]), "start": str(e.get("start", "")), "end": str(e.get("end", "")),
            "date_text": e.get("date", ""), "city": e.get("city", ""), "country": e.get("country", ""),
            "venue": e.get("venue", ""), "link": e.get("link", ""), "src": "manual",
            "deadlines": valid([{"type": d.get("type", "abstract"), "label": d.get("label", ""),
                                 "date": str(d["date"])[:10], "tz": d.get("timezone", ""),
                                 "status": d.get("status", "confirmed")} for d in e.get("deadlines") or []]),
        }], [{
            "year": int(p["year"]), "start": "", "end": "", "date_text": p.get("date", ""),
            "city": p.get("place", ""), "country": "", "venue": p.get("place", ""),
            "link": e.get("link", ""), "src": "manual",
            "deadlines": valid([{"type": "abstract", "label": "Abstract deadline",
                                 "date": str(p["deadline"])[:10], "tz": "", "status": "confirmed"}]
                               if p.get("deadline") else []),
        } for p in e.get("past") or []])
        s = build_series(canon(e["title"]), eds, "neuro", int(e["tier"]), e["field"],
                         rank, rates, programs, e, today)
        s["id"], s["link"] = e["id"], e["link"]
        series.append(s)

    for s in series:                                     # 도시/국가는 차기 회차 것을 대표로
        nx = next((x for x in s["editions"] if x["year"] == s["next"]), None) or (s["editions"][-1] if s["editions"] else {})
        s.update(city=nx.get("city", ""), country=nx.get("country", ""), venue=nx.get("venue", ""),
                 date_text=nx.get("date_text", ""), start=nx.get("start", ""), end=nx.get("end", ""),
                 deadlines=nx.get("deadlines", []), next_year=nx.get("year"),
                 # 사이클 뷰는 '전형 개최월'을 쓴다 — 차기 회차가 없는 학회도 자리를 갖는다
                 start_month=s["typical"]["meeting_month"],
                 search=" ".join([s["title"], s["full_name"], nx.get("city", ""),
                                  nx.get("country", ""), s["field"],
                                  s["rank"].get("core", "")]).lower())

    data = {"generated": today.isoformat(), "series": series,
            "sources": yaml.safe_load((DATA / "sources.yml").read_text()),
            "counts": {"hf": len(hf_eds), "ccf": len(ccf_eds), "rates": len(rates)}}
    tpl = (ROOT / "template.html").read_text()
    assert "__DATA__" in tpl, "template.html 에 __DATA__ 자리표시자가 없다"
    html = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    (ROOT / "docs" / "index.html").write_text(html)
    # Claude Artifact 는 head/body 를 자기가 감싸므로 껍데기만 벗긴 조각도 같이 낸다(템플릿은 하나).
    (ROOT / "docs" / "artifact.html").write_text(
        html[html.index("<title>"):html.index("</head>")] +
        html[html.index("<body>") + 6:html.rindex("</body>")])
    return data


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
    for f in {"ml", "vision", "nlp", "robotics", "medical", "neuro", "neuroimaging", "cognitive"}:
        assert any(x["field"] == f and x["tier"] == 1 for x in s), f"분야 {f} 에 T1 학회가 없다"
    no_next = [x["title"] for x in s if not x["next"]]
    print(f"OK  AI {len(ai)} · neuro {len(neuro)} · 차기 미공지 {len(no_next)}건({', '.join(no_next[:6])})")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--offline", action="store_true", help="캐시된 업스트림 tarball 사용")
    p.add_argument("--check", action="store_true", help="빌드 후 assert 검사")
    a = p.parse_args()
    d = build(a.offline)
    if a.check:
        check(d)
    print(f"docs/index.html  ({len(d['series'])} series, generated {d['generated']})")
