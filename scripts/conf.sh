#!/usr/bin/env bash
# 학회 레이더 런처 — `conf` 알리아스가 이 파일을 부른다.
#
#   conf            공개 사이트를 메이저 타임라인으로 연다 — 띄우는 것이 없다
#   conf list       공개 사이트, 메이저 목록(D-day)
#   conf all        공개 사이트, 전체 목록
#   conf local      아직 안 민 변경을 로컬에서 본다 (:8897 서버가 뜬다 → conf stop 필요)
#   conf update     업스트림 재수집 + 빌드 + 커밋·푸시 (공개 사이트 반영)
#   conf stop       conf local 로 띄운 서버 종료
#   conf status     그 서버 상태
#
# 260910: 기본을 공개 사이트로 되돌렸다. 로컬 서버는 오프라인 때문에 넣었는데, 공개 사이트도
# 서비스 워커로 같은 오프라인 캐시를 쓰므로 한 번 열어 본 뒤로는 이득이 없었다. 상시 도는
# 프로세스와 "왜 종료해야 하나" 라는 질문만 남겼다. 서버는 미푸시 변경을 볼 때만 쓴다.
#
# 서버를 죽일 때 pgrep/pkill 로 패턴 매칭하지 않는다. 그 명령 자신이 패턴에 걸려
# 자기를 죽이거나 남의 프로세스를 죽인다(260803 pkill self-kill 사고). pid 파일만 믿는다.
set -eu

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${CONF_RADAR_PORT:-8897}"
PIDFILE="$REPO/.cache/server.pid"
SITE="https://kafkapple.github.io/conf-radar/"

listening(){ lsof -iTCP:"$PORT" -sTCP:LISTEN -n -P >/dev/null 2>&1; }

serve(){
    if ! listening; then
        [ -f "$REPO/docs/index.html" ] || { echo "conf: docs/index.html 이 없다 — conf update 먼저" >&2; exit 1; }
        mkdir -p "$REPO/.cache"
        # --directory 를 쓴다. `( cd .. && nohup ... & )` 로 감싸면 $! 가 서브셸 pid 라
        # pid 파일이 실제 서버가 아닌 껍데기를 가리키고, stop 이 서버를 못 죽인다(260910 실측).
        nohup python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$REPO/docs" >/dev/null 2>&1 &
        echo $! > "$PIDFILE"
        for _ in $(seq 40); do listening && break; done
        listening || { echo "conf: :$PORT 서버가 안 떴다" >&2; exit 1; }
        echo "conf: 서버 시작 :$PORT (끄기 = conf stop)"
    fi
    open "http://localhost:$PORT/$1"
}

case "${1:-major}" in
    major|"")  open "$SITE#major,cyc" ;;
    list)      open "$SITE#major,list" ;;
    all)       open "$SITE" ;;
    web)       open "$SITE#major,cyc" ;;          # 옛 이름 — 이제 기본과 같다
    local)     serve "#major,cyc" ;;
    stop)
        if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
            kill "$(cat "$PIDFILE")"; rm -f "$PIDFILE"
            for _ in $(seq 40); do listening || break; done
            listening && { echo "conf: :$PORT 가 아직 열려 있다" >&2; exit 1; }
            echo "conf: 서버 종료 (:$PORT)"
        elif listening; then
            echo "conf: :$PORT 를 다른 프로세스가 쓰고 있다 — 건드리지 않는다" >&2; exit 1
        else
            rm -f "$PIDFILE"; echo "conf: 실행 중인 서버 없음"
        fi ;;
    status)
        if listening; then
            echo "conf: 실행 중 http://localhost:$PORT/"
            [ -f "$PIDFILE" ] && echo "conf: pid $(cat "$PIDFILE")"
        else
            echo "conf: 안 떠 있음"
        fi ;;
    update)
        cd "$REPO"
        uv run python build.py --check
        git add docs
        git diff --cached --quiet || git commit -m "chore: rebuild $(date +%F)"
        git push origin main
        echo "conf: main 푸시 완료 — Actions 가 gh-pages 로 배포한다 ($SITE)" ;;
    *)  sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//' ;;
esac
