#!/usr/bin/env bash
# 학회 레이더 런처 — `conf` 알리아스가 이 파일을 부른다.
#
#   conf            메이저 5곳을 타임라인으로 — 마감→개최 막대를 한 화면에서 본다
#   conf list       메이저 5곳을 목록(D-day)으로
#   conf all        전체 목록으로 열기
#   conf web        공개 사이트(GitHub Pages) 타임라인 — 로컬 서버를 안 쓴다
#   conf update     업스트림 재수집 + 빌드 + 커밋·푸시 (공개 사이트 반영)
#   conf stop       로컬 서버 종료
#   conf status     로컬 서버 상태
#
# 왜 로컬 서버인가 — file:// 로 열면 서비스 워커가 등록되지 않아 오프라인 캐시가 죽는다.
# localhost 면 공개 사이트와 같은 조건으로 돈다.
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
    major|"")  serve "#major,cyc" ;;
    list)      serve "#major" ;;
    all)       serve "" ;;
    web)       open "$SITE#major,cyc" ;;
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
    *)  sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//' ;;
esac
