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

from sources import (DISPLAY, FIELD_AI, PAPERCOPILOT, TRACKED_AI, canon,
                     editions_from_ccf, editions_from_hf, fetch, month_of,
                     rates_from_ccf, valid)

ROOT = Path(__file__).parent
DATA = ROOT / "data"

SUBMIT = {"abstract", "paper", "submission", "supplementary", "abstract_late"}


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
            "world": json.loads((DATA / "world.json").read_text()),
            "sources": yaml.safe_load((DATA / "sources.yml").read_text()),
            "counts": {"hf": len(hf_eds), "ccf": len(ccf_eds), "rates": len(rates)}}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
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


def ics_escape(t: str) -> str:
    return str(t).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line: str) -> str:
    """RFC 5545 는 한 줄 75 옥텟 제한이다. 한글은 3바이트라 금방 넘고, 안 접으면
    캘린더 앱이 줄을 잘라 제목이 깨진다. 바이트 기준으로 접고 이어지는 줄은 공백으로 시작."""
    b = line.encode()
    if len(b) <= 73:
        return line
    out, cur = [], b
    while len(cur) > 73:
        cut = 73
        while cut > 0 and (cur[cut] & 0xC0) == 0x80:   # UTF-8 문자 중간에서 자르지 않는다
            cut -= 1
        out.append(cur[:cut].decode())
        cur = b" " + cur[cut:]
    out.append(cur.decode())
    return "\r\n".join(out)


def build_ics(series: list[dict], stamp: str) -> str:
    """구독용 캘린더. 아이폰에서 한 번 구독해 두면 Actions 가 갱신할 때마다 따라온다."""
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//conf-radar//KR", "CALSCALE:GREGORIAN",
         "METHOD:PUBLISH", "X-WR-CALNAME:학회 레이더", "X-WR-TIMEZONE:Asia/Seoul",
         "X-PUBLISHED-TTL:PT12H"]
    for s in series:
        for d in s["deadlines"]:
            if d["type"] not in SUBMIT:
                continue
            y, m, dd = d["date"].split("-")
            nxt = (date(int(y), int(m), int(dd)) + timedelta(days=1)).strftime("%Y%m%d")
            tag = "" if d["status"] == "confirmed" else (" (미공지)" if d["status"] == "tba" else " (추정)")
            L += ["BEGIN:VEVENT", f"UID:{s['id']}-{d['type']}-{d['date']}@conf-radar",
                  f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{y}{m}{dd}", f"DTEND;VALUE=DATE:{nxt}",
                  f"SUMMARY:🔴 {ics_escape(s['title'])} 마감{ics_escape(tag)}",
                  fold(f"DESCRIPTION:{ics_escape(d['label'])} · {ics_escape(s['date_text'])} "
                       f"{ics_escape(s['city'])}\\n{ics_escape(s['link'])}"),
                  f"URL:{s['link']}", "TRANSP:TRANSPARENT",
                  "BEGIN:VALARM", "TRIGGER:-P7D", "ACTION:DISPLAY",
                  f"DESCRIPTION:{ics_escape(s['title'])} 마감 1주 전", "END:VALARM",
                  "END:VEVENT"]
        if s["start"] and s["end"]:
            ey, em, ed = s["end"].split("-")
            nxt = (date(int(ey), int(em), int(ed)) + timedelta(days=1)).strftime("%Y%m%d")
            L += ["BEGIN:VEVENT", f"UID:{s['id']}-meeting@conf-radar", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{s['start'].replace('-','')}", f"DTEND;VALUE=DATE:{nxt}",
                  f"SUMMARY:📍 {ics_escape(s['title'])} {s.get('next') or ''}",
                  f"LOCATION:{ics_escape(s['venue'] or s['city'])}",
                  f"URL:{s['link']}", "TRANSP:TRANSPARENT", "END:VEVENT"]
    L.append("END:VCALENDAR")
    return "\r\n".join(fold(x) for x in L) + "\r\n"


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
