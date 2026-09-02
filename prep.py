#!/usr/bin/env python3
"""가끔 돌려 캐시를 갱신하는 스크립트. 산출물(data/geo.yml, data/world.json)은 커밋한다.

빌드(build.py)는 이 캐시만 읽는다 — 매일 도는 CI 가 외부 지오코더에 의존하면 그쪽이 죽는 날
페이지가 통째로 깨진다. 새 도시가 생기면 여기서 한 번 돌려 캐시에 넣는다.

    python prep.py --world     세계 육지 윤곽 → SVG 경로 (Natural Earth 110m)
    python prep.py --geo       학회 개최지 → 위경도 (OpenStreetMap Nominatim, 1건/초)
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

DATA = Path(__file__).parent / "data"
LAND = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_land.geojson"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "conf-radar/1.0 (github.com/kafkapple/conf-radar)"

W, H = 1000, 500          # equirectangular 캔버스. 뷰어의 좌표계와 같아야 한다.
proj = lambda lon, lat: ((lon + 180) * W / 360, (90 - lat) * H / 180)


def build_world() -> None:
    with urllib.request.urlopen(LAND, timeout=60) as r:
        gj = json.load(r)
    paths, dropped = [], 0
    for feat in gj["features"]:
        g = feat["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            ring = poly[0]                                   # 외곽선만. 호수(구멍)는 이 축척에서 안 보인다
            pts = [proj(lon, lat) for lon, lat in ring]
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            if (max(xs)-min(xs)) < 2 and (max(ys)-min(ys)) < 2:
                dropped += 1                                 # 2px 미만 섬은 점 하나로 뭉개진다
                continue
            d = "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + "Z"
            paths.append(d)
    out = {"w": W, "h": H, "paths": paths,
           "source": LAND, "note": "Natural Earth 110m land, equirectangular, 소수점 1자리"}
    (DATA / "world.json").write_text(json.dumps(out, separators=(",", ":")))
    print(f"world.json  {len(paths)} paths ({dropped} 작은 섬 제외)  "
          f"{(DATA/'world.json').stat().st_size//1024} KB")


VIRTUAL = re.compile(r"\b(virtual|online|remote)\b", re.I)


def geocode(place: str) -> dict | None:
    # 온라인 회차는 좌표가 없다. Nominatim 은 "Virtual" 을 러시아의 실제 지명으로 찍어준다.
    if VIRTUAL.search(place):
        return None
    q = urllib.parse.urlencode({"q": place, "format": "json", "limit": 1})
    req = urllib.request.Request(f"{NOMINATIM}?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        hits = json.load(r)
    if not hits:
        parts = [x.strip() for x in place.split(",") if x.strip()]
        if len(parts) > 2:                                   # 긴 베뉴명 → 뒤쪽 "도시, 국가" 로 폴백
            return geocode(", ".join(parts[-2:]))
        return None
    h = hits[0]
    return {"lat": round(float(h["lat"]), 4), "lon": round(float(h["lon"]), 4),
            "matched": h.get("display_name", "")[:120]}


def build_geo() -> None:
    import build as B
    cache_path = DATA / "geo.yml"
    cache = yaml.safe_load(cache_path.read_text()) if cache_path.exists() else {}
    places = set()
    for s in B.build(offline=True)["series"]:
        for e in s["editions"]:
            p = ", ".join(x for x in [e.get("city", ""), e.get("country", "")] if x) or e.get("venue", "")
            if p.strip():
                places.add(p.strip())
    todo = sorted(places - set(cache))
    print(f"캐시 {len(cache)}건 · 신규 {len(todo)}건")
    for i, p in enumerate(todo, 1):
        try:
            hit = geocode(p)
        except Exception as ex:                              # 한 건 실패로 전체를 버리지 않는다
            print(f"  [{i}/{len(todo)}] {p}  ERROR {ex}")
            continue
        cache[p] = hit                                       # 못 찾으면 None 을 박아 재시도를 막는다
        print(f"  [{i}/{len(todo)}] {p}  →  {hit['lat'] if hit else 'MISS'}"
              f"{','+str(hit['lon']) if hit else ''}")
        cache_path.write_text(yaml.safe_dump(cache, allow_unicode=True, sort_keys=True))
        time.sleep(1.1)                                      # Nominatim 이용 정책 = 1초에 1건
    miss = [k for k, v in cache.items() if not v]
    print(f"geo.yml  {len(cache)}건 (미발견 {len(miss)}건{': '+', '.join(miss[:5]) if miss else ''})")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--world", action="store_true")
    p.add_argument("--geo", action="store_true")
    a = p.parse_args()
    if a.world:
        build_world()
    if a.geo:
        build_geo()
    if not (a.world or a.geo):
        p.error("--world 또는 --geo 중 하나는 필요하다")
