#!/usr/bin/env python3
"""캘린더 내보내기 — 시리즈를 RFC 5545 .ics 로 만든다.

build.py 에서 떼어냈다(260910). 하는 일이 다르고(달력 규격 맞추기) 이 파일만 따로 고칠 일이
많다 — 접기 규칙·알림·시간대는 학회 데이터와 아무 상관이 없다.
"""
from __future__ import annotations

from datetime import date, timedelta

SUBMIT = {"abstract", "paper", "submission", "supplementary", "abstract_late"}


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
