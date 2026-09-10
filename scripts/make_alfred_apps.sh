#!/usr/bin/env bash
# Alfred 용 앱 번들 2개를 ~/Applications 에 만든다 (실행 · 종료).
#
# 이름은 영어다. Alfred 검색창에서 한글은 조합 중 매칭이 흔들리고, `conf` 세 글자가
# 셸 알리아스와 같은 단어라 두 표면에서 같은 것을 친다 (260910 사용자 지시).
#
# 왜 앱인가 — Alfred 워크플로와 커스텀 검색은 plist 안에 들어가고 그 파일은 사람이 만들어야
# 한다. 반면 Alfred 는 ~/Applications 를 기본으로 훑으므로, 앱 번들을 두면 설정 없이
# 이름만 쳐서 실행된다. 앱 이름을 한글로 둔 이유도 그것 — 「학회」 세 글자로 잡힌다.
#
# GUI 로 뜨는 앱은 로그인 셸을 안 거쳐 PATH 가 최소다. 그래서 안에서 PATH 를 직접 세운다.
# 옛 한글 이름 앱은 이름이 바뀌었으므로 여기서 지운다 — 안 지우면 Alfred 에 둘 다 남는다.
set -eu
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HOME/Applications"

make_app() {   # $1=앱 이름  $2=conf.sh 인자
    local app="$DEST/$1.app" arg="$2"
    rm -rf "$app"
    mkdir -p "$app/Contents/MacOS"
    cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>$1</string>
  <key>CFBundleDisplayName</key><string>$1</string>
  <key>CFBundleIdentifier</key><string>local.confradar.$(echo "$arg" | tr -c 'a-z' 'x')</string>
  <key>CFBundleExecutable</key><string>run</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSBackgroundOnly</key><true/>
</dict></plist>
PLIST
    cat > "$app/Contents/MacOS/run" <<RUN
#!/bin/sh
export PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
exec /bin/bash "$REPO/scripts/conf.sh" $arg
RUN
    chmod +x "$app/Contents/MacOS/run"
    echo "만듦: $app"
}

mkdir -p "$DEST"
rm -rf "$DEST/학회 레이더.app" "$DEST/학회 레이더 종료.app"     # 260910 개명 전 이름
make_app "Conference Radar" ""
make_app "Conference Radar Quit" "stop"
# Alfred 가 새 앱을 바로 찾도록 Spotlight 색인에 알린다.
/usr/bin/mdimport "$DEST" 2>/dev/null || true
echo "Alfred 에서 conf 로 검색 — Conference Radar / Conference Radar Quit"
