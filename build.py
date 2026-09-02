#!/usr/bin/env python3
"""conf-radar 빌드 — 학회 '시리즈' 단위로 여러 출처를 합쳐 단일 HTML 을 만든다.

설계 메모:
- 단위는 회차(edition)가 아니라 시리즈(conference series)다. 차기 회차가 아직 공지되지 않은
  학회(ICML·ACL·ICCV 등)도 과거 회차에서 유도한 전형 시기와 함께 남는다. 회차 단위로 두고
  신선도로 걸러내면 이런 학회가 목록에서 통째로 사라진다.
- 스키마를 새로 만들지 않고 업스트림 것을 그대로 읽어 온다. 우리가 관리하는 데이터는
  data/*.yml 세 개뿐이다.
- 데이터를 HTML 에 인라인한다. fetch() 를 쓰면 file:// 에서 CORS 로 죽고 서버가 필요해진다.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import tarfile
import urllib.request
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
DATA = ROOT / "data"
CACHE = ROOT / ".cache"

SOURCES = {   # 이름: (tarball, 캐시파일)
    "hf":  ("https://codeload.github.com/huggingface/ai-deadlines/tar.gz/refs/heads/main", "hf.tar.gz"),
    "ccf": ("https://codeload.github.com/ccfddl/ccf-deadlines/tar.gz/refs/heads/main", "ccf.tar.gz"),
}

# ─────────────────────────────────────────────────────────────────────────────
# 티어 = 두 축의 조합이며, 객관 축은 내가 정하지 않는다.
#   객관 축 = CORE 등급 (ccf-deadlines 가 실어 나르는 외부 정본)
#   개인 축 = 이 연구(3D 비전 · 행동/뇌 계측 · NeuroAI)와의 거리
# T1 = 두 축 모두 충족 — 분야 최상위(CORE A*, 또는 등급 미부여 전문 학회 중 대표) **이면서**
#      실제 투고 또는 필독 대상. 분야마다 최소 1개는 T1 이 있도록 보장한다.
# T2 = 한 축만 충족.  T3 = 둘 다 아니지만 마감 캘린더에는 남긴다.
TIER_AI = {
    1: ["neurips", "icml", "iclr", "aaai", "colm", "aistats",          # 머신러닝
        "cvpr", "iccv", "eccv", "3dv", "wacv", "siggraph",             # 비전·3D
        "acl", "emnlp", "naacl",                                       # 언어
        "icra", "corl",                                                # 로보틱스
        "miccai"],                                                     # 의료영상
    2: ["ijcai", "iros", "rss", "uai", "colt", "kdd", "icassp", "interspeech"],
}
TRACKED_AI = {slug: t for t, slugs in TIER_AI.items() for slug in slugs}

FIELD_AI = {
    **{k: "ml" for k in ["neurips", "icml", "iclr", "aistats", "colm", "uai", "colt", "aaai", "ijcai", "kdd"]},
    **{k: "vision" for k in ["cvpr", "iccv", "eccv", "3dv", "wacv", "siggraph"]},
    **{k: "nlp" for k in ["acl", "emnlp", "naacl", "interspeech", "icassp"]},
    **{k: "robotics" for k in ["icra", "iros", "rss", "corl"]},
    "miccai": "medical",
}

# 두 업스트림이 같은 학회를 다른 이름으로 부른다. 파일명이 아니라 YAML 안의 title 로 맞춘다
# (nips.yml 의 title 은 "NeurIPS" 다 — 파일명으로 맞추려다 NeurIPS 이력이 통째로 빠졌었다).
CANON = {"ACM SIGGRAPH": "SIGGRAPH", "NIPS": "NEURIPS"}

# papercopilot 통계 페이지가 실재하는 슬러그. 없는 슬러그는 진짜 404 를 낸다(soft-404 아님).
# 재확인: curl -sLo/dev/null -w"%{http_code}\n" https://papercopilot.com/statistics/<slug>-statistics/
PAPERCOPILOT = {
    "neurips", "icml", "iclr", "cvpr", "iccv", "eccv", "siggraph", "aaai", "acl",
    "emnlp", "aistats", "colm", "3dv", "wacv", "corl", "ijcai", "uai", "kdd",
    "icra", "iros", "rss",
}

MONTHS = ("january february march april may june july august september october "
          "november december").split()

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def valid(dls: list[dict]) -> list[dict]:
    """ccf 는 마감을 'TBD' 로 두기도 한다. 날짜가 아닌 값이 통과하면 월 계산에서 터진다."""
    return sorted([d for d in dls if ISO.match(d.get("date", ""))], key=lambda d: d["date"])

# ─────────────────────────────────────────────────────────────────────────────
def fetch(name: str, offline: bool) -> tarfile.TarFile:
    url, fn = SOURCES[name]
    path = CACHE / fn
    if not offline or not path.exists():
        CACHE.mkdir(exist_ok=True)
        with urllib.request.urlopen(url, timeout=120) as r:
            path.write_bytes(r.read())
    return tarfile.open(fileobj=io.BytesIO(path.read_bytes()))


def yaml_docs(tf: tarfile.TarFile, needle: str):
    """tar 안에서 경로에 needle 이 든 YAML 을 전부 읽어 dict 를 흘려보낸다."""
    for m in tf.getmembers():
        if needle not in m.name or not m.name.endswith((".yml", ".yaml")):
            continue
        fh = tf.extractfile(m)
        if fh is None:
            continue
        try:
            docs = yaml.safe_load(fh.read())
        except yaml.YAMLError:
            continue
        for d in (docs if isinstance(docs, list) else [docs]):
            if isinstance(d, dict):
                yield Path(m.name).stem, d


def canon(title: str) -> str:
    """색인 키. 대소문자 표기가 출처마다 달라(hf 'Interspeech' vs ccf 'INTERSPEECH')
    대문자로 통일한다 — 이걸 안 하면 같은 학회가 두 시리즈로 갈라져 이력이 반쪽이 된다."""
    u = str(title).upper()
    return CANON.get(u, u)


def month_of(text: str) -> int | None:
    """'June 19 - June 24, 2022' → 6. 자유 문장에서 첫 월 이름만 집는다."""
    m = re.search(r"[A-Za-z]{3,}", text or "")
    while m:
        for i, name in enumerate(MONTHS, 1):
            if name.startswith(m.group(0).lower()[:3]) and m.group(0).lower()[:3] == name[:3]:
                return i
        m = re.search(r"[A-Za-z]{3,}", text, m.end())
    return None


# ─────────────────────────────────────────────────────────────────────────────
DISPLAY: dict[str, str] = {}   # 대문자 키 → 화면 표기


def editions_from_hf(tf) -> dict[str, list[dict]]:
    """차기 회차 상세. 마감 종류가 세분화되어 있어 D-day 계산의 정본으로 쓴다."""
    out: dict[str, list[dict]] = {}
    for slug, e in yaml_docs(tf, "src/data/conferences/"):
        if slug not in TRACKED_AI or "year" not in e:
            continue
        dls = [{"type": d.get("type", "paper"), "label": d.get("label", d.get("type", "")),
                "date": str(d["date"])[:10], "tz": d.get("timezone", ""), "status": "confirmed"}
               for d in (e.get("deadlines") or []) if d.get("date")]
        DISPLAY.setdefault(canon(e["title"]), str(e["title"]))
        out.setdefault(canon(e["title"]), []).append({
            "year": int(e["year"]), "start": str(e.get("start", "")), "end": str(e.get("end", "")),
            "date_text": e.get("date", ""), "city": e.get("city", ""), "country": e.get("country", ""),
            "venue": e.get("venue", ""), "link": e.get("link", ""),
            "deadlines": valid(dls), "src": "hf",
            "slug": slug,
        })
    return out


def editions_from_ccf(tf) -> tuple[dict[str, list[dict]], dict[str, dict]]:
    """다년 이력 + CORE/CCF 등급. 전형 시기를 유도할 표본은 여기서 나온다."""
    eds: dict[str, list[dict]] = {}
    rank: dict[str, dict] = {}
    for _, e in yaml_docs(tf, "/conference/"):
        if "title" not in e or "confs" not in e:
            continue
        t = canon(e["title"])
        DISPLAY.setdefault(t, str(e["title"]))
        if e.get("rank"):
            rank[t] = {k: v for k, v in e["rank"].items() if v and v != "N"}
        for c in e["confs"] or []:
            dls = []
            for tl in c.get("timeline") or []:
                for key, label in (("abstract_deadline", "Abstract deadline"), ("deadline", "Paper deadline")):
                    if tl.get(key):
                        dls.append({"type": "abstract" if "abstract" in key else "paper",
                                    "label": label, "date": str(tl[key])[:10],
                                    "tz": c.get("timezone", ""), "status": "confirmed"})
            eds.setdefault(t, []).append({
                "year": int(c["year"]), "start": "", "end": "",
                "date_text": c.get("date", ""), "city": c.get("place", ""), "country": "",
                "venue": c.get("place", ""), "link": c.get("link", ""),
                "deadlines": valid(dls), "src": "ccf",
            })
    return eds, rank


def rates_from_ccf(tf) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for _, e in yaml_docs(tf, "accept_rates/"):
        rows = []
        for r in e.get("accept_rates") or []:
            sub, acc = r.get("submitted"), r.get("accepted")
            if sub and acc:
                # 업스트림 rate 필드는 소수점에 쉼표가 섞인 사례가 있어 직접 계산한다
                rows.append({"year": int(r["year"]), "submitted": int(sub), "accepted": int(acc),
                             "rate": round(acc / sub, 4), "source": r.get("source", "")})
        if rows:
            out[canon(e["title"])] = sorted(rows, key=lambda r: r["year"])
    return out


# ─────────────────────────────────────────────────────────────────────────────
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
