"""전체 이력(첫 개최~현재) 로더. data/history.yml = 메이저 5곳, 수치는 출처 필수.

업스트림(ccf-deadlines)은 최근 3-6년만 싣는다. 그 앞은 학회 공식 페이지·DBLP 등을 사람이(또는 에이전트가)
읽어 data/history.yml 에 옮기고, 이 모듈이 빌드에 합친다. 출처 없는 수치는 assert 로 막는다.
"""
from pathlib import Path

import yaml

FILE = Path(__file__).parent / "data" / "history.yml"


def load(geo: dict) -> dict:
    raw = (yaml.safe_load(FILE.read_text()) or {}) if FILE.exists() else {}
    out = {}
    for conf, h in raw.items():
        h["editions"].sort(key=lambda e: e["year"])      # 조사 파일마다 오름차순·내림차순이 달라 여기서 맞춘다
        years = [e["year"] for e in h["editions"]]
        assert len(years) == len(set(years)), f"{conf}: 연도가 중복됐다"
        assert h["first_year"] == years[0], f"{conf}: first_year {h['first_year']} != 첫 회차 {years[0]}"
        assert h.get("first_year_source"), f"{conf}: first_year_source 없음"
        eds = []
        for e in h["editions"]:
            sub, acc = e.get("submitted"), e.get("accepted")
            if sub is not None or acc is not None:
                assert e.get("num_source"), f"{conf} {e['year']}: 수치에 num_source 없음"
            if sub and acc:
                assert acc <= sub, f"{conf} {e['year']}: 채택 {acc} > 투고 {sub}"
            # sites 가 빈 회차 = 개최지 출처를 못 찾은 해(ACL 1964-78 등). 빈 채로 두고 추정하지 않는다.
            sites = [{"place": p, "lat": (geo.get(p) or {}).get("lat"), "lon": (geo.get(p) or {}).get("lon")}
                     for p in e.get("sites") or []]
            eds.append({"year": e["year"], "sites": sites, "submitted": sub, "accepted": acc,
                        "rate": round(acc / sub, 4) if sub and acc else None,
                        "source": e.get("num_source") or e.get("loc_source", "")})
        out[conf] = {"first_year": h["first_year"], "first_source": h["first_year_source"], "editions": eds}
    return out
