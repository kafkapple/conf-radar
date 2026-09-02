#!/usr/bin/env python3
"""업스트림 읽기 전담 — tarball 을 받아 학회 회차·등급·투고수를 뽑는다.

여기는 '가져오기'만 한다. 합치기·유도·렌더는 build.py 가 맡는다.
경계를 나눈 시점 = 업스트림이 세 개째로 늘어난 때(260902).
"""
from __future__ import annotations

import io
import re
import tarfile
import urllib.request
from pathlib import Path

import yaml

CACHE = Path(__file__).parent / ".cache"

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
