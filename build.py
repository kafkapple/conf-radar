#!/usr/bin/env python3
"""conf-radar 빌드 — 업스트림 AI 학회 YAML + 자체 뇌과학 YAML 을 병합해 단일 HTML 을 만든다.

설계 메모:
- 스키마는 업스트림(huggingface/ai-deadlines)을 그대로 쓴다. 자체 스키마를 정의하지 않으므로 변환 코드가 없다.
- 데이터를 HTML 에 인라인한다. fetch() 를 쓰면 file:// 에서 CORS 로 죽고 서버가 필요해진다.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import tarfile
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
UPSTREAM_TARBALL = "https://codeload.github.com/huggingface/ai-deadlines/tar.gz/refs/heads/main"
# 투고/채택 수 시계열. 데이터 포인트마다 source URL 이 붙어 있어 출처 추적이 된다.
RATES_TARBALL = "https://codeload.github.com/ccfddl/ccf-deadlines/tar.gz/refs/heads/main"
RATES_DIR = "accept_rates/"
RATES_CACHE = ROOT / ".cache" / "rates.tar.gz"
# accept_rates 색인 키는 파일명이 아니라 YAML 안의 title 이다 (nips.yml 의 title 은 "NeurIPS").
# 파일명으로 맞추려다 NeurIPS 추세가 통째로 빠졌던 자리 — 제목으로 맞추고 예외만 별칭으로 둔다.
RATES_ALIAS = {"SIGGRAPH": "ACM SIGGRAPH"}
UPSTREAM_DIR = "src/data/conferences/"
CACHE = ROOT / ".cache" / "upstream.tar.gz"

# 티어 = 학회의 객관적 등급이 아니라 **이 사람의 관심 우선순위**다 (3D 비전 · 행동/뇌 계측).
# T1 = 반드시 챙김 / T2 = 관련 있음 / T3 = 참고. 기본 화면은 T1-2 만 보여준다.
TIER_AI = {
    1: ["neurips", "icml", "iclr", "cvpr", "iccv", "eccv", "siggraph"],
    2: ["aaai", "acl", "emnlp", "aistats", "colm", "miccai", "3dv", "wacv", "corl"],
    3: ["ijcai", "naacl", "uai", "colt", "kdd", "icassp", "interspeech", "icra", "iros", "rss"],
}
TRACKED_AI = {slug: t for t, slugs in TIER_AI.items() for slug in slugs}

# 분야 = 슬러그에서 직접 매핑. 업스트림 tags 는 학회마다 입도가 달라 그룹핑에 못 쓴다.
FIELD_AI = {
    **{k: "ml" for k in ["neurips", "icml", "iclr", "aistats", "colm", "uai", "colt", "aaai", "ijcai", "kdd"]},
    **{k: "vision" for k in ["cvpr", "iccv", "eccv", "3dv", "wacv", "siggraph"]},
    **{k: "nlp" for k in ["acl", "emnlp", "naacl", "interspeech", "icassp"]},
    **{k: "robotics" for k in ["icra", "iros", "rss", "corl"]},
    "miccai": "medical",
}

# papercopilot 통계 페이지가 실재하는 슬러그. 없는 슬러그는 진짜 404 를 낸다(soft-404 아님).
# 재확인: for s in <slug>; do curl -sLo/dev/null -w"%{http_code} $s\n" \
#   https://papercopilot.com/statistics/$s-statistics/; done
PAPERCOPILOT = {
    "neurips", "icml", "iclr", "cvpr", "iccv", "eccv", "siggraph", "aaai", "acl",
    "emnlp", "aistats", "colm", "3dv", "wacv", "corl", "ijcai", "uai", "kdd",
    "icra", "iros", "rss",
}
STALE_DAYS = 45  # 끝난 지 이만큼 지난 학회는 뺀다

# 업스트림이 새 마감 타입을 도입하면 뷰어의 SUBMIT 집합에서 조용히 빠져 학회가 사라진다
# (실제로 'submission' 을 빠뜨려 ICRA 가 사라졌다). 모르는 타입이면 빌드를 실패시킨다.
KNOWN_TYPES = {
    "abstract", "paper", "submission", "supplementary", "abstract_late",   # 제출 = 뷰어 SUBMIT
    "notification", "camera_ready", "registration", "review_release",
    "rebuttal_start", "rebuttal_end", "rebuttal_and_revision",
    "reviewer_registration", "commitment_deadline",
}


def fetch_upstream(offline: bool = False) -> list[dict]:
    """업스트림 리포를 tarball 한 번으로 받아 학회 YAML 만 뽑는다 (파일별 68회 요청 대신)."""
    if not offline or not CACHE.exists():
        CACHE.parent.mkdir(exist_ok=True)
        with urllib.request.urlopen(UPSTREAM_TARBALL, timeout=60) as r:
            CACHE.write_bytes(r.read())
    entries: list[dict] = []
    with tarfile.open(fileobj=io.BytesIO(CACHE.read_bytes())) as tf:
        for m in tf.getmembers():
            if UPSTREAM_DIR not in m.name or not m.name.endswith(".yml"):
                continue
            slug = Path(m.name).stem
            if slug not in TRACKED_AI:
                continue
            fh = tf.extractfile(m)
            assert fh is not None, f"tar member unreadable: {m.name}"
            for e in yaml.safe_load(fh.read()) or []:
                e["group"] = "ai"
                e["tier"] = TRACKED_AI[slug]
                e["field"] = FIELD_AI.get(slug, "ml")
                entries.append(e)
    return entries


def fetch_rates(offline: bool = False) -> dict[str, list[dict]]:
    """ccf-deadlines 의 투고/채택 시계열을 학회 제목(대문자) 기준으로 색인한다."""
    if not offline or not RATES_CACHE.exists():
        RATES_CACHE.parent.mkdir(exist_ok=True)
        with urllib.request.urlopen(RATES_TARBALL, timeout=90) as r:
            RATES_CACHE.write_bytes(r.read())
    out: dict[str, list[dict]] = {}
    with tarfile.open(fileobj=io.BytesIO(RATES_CACHE.read_bytes())) as tf:
        for m in tf.getmembers():
            if RATES_DIR not in m.name or not m.name.endswith(".yml"):
                continue
            fh = tf.extractfile(m)
            if fh is None:
                continue
            for e in yaml.safe_load(fh.read()) or []:
                rows = []
                for r in e.get("accept_rates") or []:
                    sub, acc = r.get("submitted"), r.get("accepted")
                    if not sub or not acc:
                        continue
                    # 업스트림 rate 필드는 소수점에 쉼표가 섞인 사례가 있어 직접 계산한다
                    rows.append({"year": int(r["year"]), "submitted": int(sub),
                                 "accepted": int(acc), "rate": round(acc / sub, 4),
                                 "source": r.get("source", "")})
                if rows:
                    out[str(e["title"]).upper()] = sorted(rows, key=lambda r: r["year"])
    return out


def load_neuro() -> list[dict]:
    entries = yaml.safe_load((ROOT / "data" / "neuro.yml").read_text()) or []
    for e in entries:
        e["group"] = "neuro"
    return entries


def enrich(c: dict, rates: dict[str, list[dict]]) -> dict:
    """규모·추세·외부 링크를 붙인다. 근거를 못 찾으면 채우지 않고 비워 둔다."""
    slug = c["id"].rstrip("0123456789")
    key = c["title"].upper()
    hist = rates.get(RATES_ALIAS.get(key, key), []) if c["group"] == "ai" else []
    c["history"] = hist
    if c["group"] == "ai" and hist:
        # 규모 = 최근 회차 투고 편수. 참가자 수와 단위가 다르므로 그룹을 넘어 비교하지 않는다.
        c["scale"] = {"metric": "submitted", "value": hist[-1]["submitted"],
                      "year": hist[-1]["year"], "source": hist[-1]["source"]}
    c.setdefault("scale", None)
    links = []
    if slug in PAPERCOPILOT:
        links.append(["통계·추세", f"https://papercopilot.com/statistics/{slug}-statistics/"])
    if c["group"] == "ai":
        links.append(["OpenReview", f"https://openreview.net/search?query={c['title']}"])
        links.append(["역대 수상 논문", "https://jeffhuang.com/best_paper_awards/"])
    c["links"] = links
    return c


def normalize(entries: list[dict], today: date) -> list[dict]:
    """필수 필드를 채우고, 끝난 학회를 떨어내고, 마감을 D-day 계산 가능한 형태로 편다."""
    cutoff = today - timedelta(days=STALE_DAYS)
    out = []
    for e in entries:
        end = e.get("end") or e.get("start")
        if not end:
            continue
        end_d = datetime.strptime(str(end), "%Y-%m-%d").date()
        if end_d < cutoff:
            continue
        dls = []
        for d in e.get("deadlines") or []:
            if not d.get("date"):
                continue
            dls.append({
                "type": d.get("type", "paper"),
                "label": d.get("label", d.get("type", "deadline")),
                "date": str(d["date"])[:10],
                "tz": d.get("timezone", ""),
                # 업스트림에는 status 가 없다 = 공식 공지된 확정값이라는 뜻
                "status": d.get("status", "confirmed"),
            })
        dls.sort(key=lambda d: d["date"])
        start_d = datetime.strptime(str(e.get("start", end)), "%Y-%m-%d").date()
        out.append({
            "id": e.get("id") or f"{e['title']}{e['year']}".lower(),
            "title": e["title"],
            "year": e["year"],
            "full_name": e.get("full_name", ""),
            "link": e.get("link", ""),
            "group": e["group"],
            "tier": int(e.get("tier", 3)),
            "field": e.get("field", "neuro" if e["group"] == "neuro" else "ml"),
            "tags": e.get("tags") or [],
            "scale": e.get("scale"),
            "city": e.get("city", ""),
            "country": e.get("country", ""),
            "venue": e.get("venue", ""),
            "date_text": e.get("date", ""),
            "start": start_d.isoformat(),
            "end": end_d.isoformat(),
            "start_month": start_d.month,
            "deadlines": dls,
            "source": e.get("source", e.get("link", "")),
            "verified": str(e.get("verified", "")),
        })
    out.sort(key=lambda c: (c["deadlines"][0]["date"] if c["deadlines"] else c["start"]))
    return out


def build(offline: bool = False) -> dict:
    today = date.today()
    upstream, neuro = fetch_upstream(offline), load_neuro()
    rates = fetch_rates(offline)
    confs = [enrich(c, rates) for c in normalize(upstream + neuro, today)]
    data = {
        "generated": today.isoformat(),
        "upstream_raw": len(upstream),   # 필터 전 개수 = fetch 성공 여부 판정용
        "rates_raw": len(rates),
        "conferences": confs,
        "sources": yaml.safe_load((ROOT / "data" / "sources.yml").read_text()),
    }
    tpl = (ROOT / "template.html").read_text()
    assert "__DATA__" in tpl, "template.html 에 __DATA__ 자리표시자가 없다"
    html = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    (ROOT / "docs" / "index.html").write_text(html)
    # Claude Artifact 는 <head>/<body> 를 자기가 감싸므로 그 껍데기만 벗긴 조각도 같이 낸다.
    # 템플릿을 두 벌 두지 않기 위해 기계적으로 잘라낸다 (SSOT = template.html 하나).
    head = html[html.index("<title>"):html.index("</head>")]
    body = html[html.index("<body>") + len("<body>"):html.rindex("</body>")]
    (ROOT / "docs" / "artifact.html").write_text(head + body)
    return data


def check(data: dict) -> None:
    """회귀 방지 assert. 조용히 빈 페이지가 나가는 것을 막는 최소 장치."""
    confs = data["conferences"]
    ai = [c for c in confs if c["group"] == "ai"]
    neuro = [c for c in confs if c["group"] == "neuro"]
    # 필터 후 개수로 판정하면 안 된다 — 업스트림에 차기 회차가 아직 없는 학회(ICML/ACL 등)가
    # 정상적으로 빠지므로 fetch 성공과 무관하게 개수가 출렁인다. fetch 자체는 raw 로 본다.
    assert data["upstream_raw"] >= 40, f"업스트림 fetch 실패 의심: raw {data['upstream_raw']}건"
    assert ai, "AI 학회가 0건 — 신선도 필터 또는 TRACKED_AI 확인"
    assert all(c["tier"] in (1, 2, 3) for c in confs), "tier 미지정 학회 존재"
    assert all(c["field"] for c in confs), "field 미지정 학회 존재"
    assert data["rates_raw"] >= 60, f"accept_rates fetch 실패 의심: {data['rates_raw']}건"  # 260902 실측 93건
    with_hist = {c["title"] for c in confs if c["history"]}
    # 이 넷이 빠지면 제목 매핑이 깨진 것이다 (실제로 NeurIPS 가 파일명 매칭 탓에 빠졌었다)
    must = {"NeurIPS", "CVPR", "ICLR", "SIGGRAPH"} & {c["title"] for c in confs}
    assert must <= with_hist, f"추세 누락: {sorted(must - with_hist)} — RATES_ALIAS 확인"
    for c in confs:
        for h in c["history"]:
            assert 0 < h["rate"] <= 1, f"{c['id']} {h['year']}: 채택률 {h['rate']}"
    assert data["sources"], "sources.yml 비어 있음"
    assert len(neuro) >= 5, f"neuro.yml 로드 실패 의심: {len(neuro)}건"
    for c in confs:
        assert c["title"] and c["start"] <= c["end"], f"날짜 역전: {c['id']}"
        for d in c["deadlines"]:
            assert d["status"] in {"confirmed", "estimated", "tba"}, f"{c['id']}: {d['status']}"
            assert d["type"] in KNOWN_TYPES, (
                f"{c['id']}: 모르는 마감 타입 '{d['type']}' — build.py KNOWN_TYPES 와 "
                f"template.html SUBMIT 을 같이 갱신할 것")
    print(f"OK  AI {len(ai)} · neuro {len(neuro)} · total {len(confs)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--offline", action="store_true", help="캐시된 업스트림 tarball 사용")
    p.add_argument("--check", action="store_true", help="빌드 후 assert 검사")
    a = p.parse_args()
    d = build(a.offline)
    if a.check:
        check(d)
    print(f"docs/index.html  ({len(d['conferences'])} conferences, generated {d['generated']})")
