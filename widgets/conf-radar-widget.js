// 학회 레이더 — 아이폰 홈화면 위젯 (Scriptable 용)
//
// 왜 Scriptable 인가: iOS 홈화면 위젯은 WidgetKit(네이티브 Swift)으로만 만들 수 있고
// PWA 는 위젯을 낼 수 없다. Scriptable 은 무료 앱이면서 JS 로 위젯을 그려주므로
// Xcode·개발자 계정·서명·재서명 로테이션을 전부 건너뛴다.
//
// 설치
//   1. App Store 에서 Scriptable 설치
//   2. 앱에서 + → 이 파일 내용 붙여넣기 → 이름 "학회 레이더" 로 저장
//   3. 홈화면 길게 누르기 → + → Scriptable → 중간 크기 위젯 추가
//   4. 위젯 길게 누르기 → "위젯 편집" → Script = 학회 레이더, When Interacting = Run Script
//
// 데이터는 사이트가 매일 갱신하는 data.json 을 그대로 읽는다. 위젯 쪽에 로직이 없다.

const DATA_URL = "https://kafkapple.github.io/conf-radar/data.json";
const SITE_URL = "https://kafkapple.github.io/conf-radar/";
const SUBMIT = ["abstract", "paper", "submission", "supplementary", "abstract_late"];
const TIER_MAX = 1;        // 1 = T1 만, 2 = T1+T2
const CACHE = FileManager.local().joinPath(FileManager.local().cacheDirectory(), "conf-radar.json");

const today = new Date(new Date().toDateString());
const dday = iso => Math.floor((new Date(iso + "T23:59:59") - today) / 864e5);

async function load() {
  const fm = FileManager.local();
  try {
    const d = await new Request(DATA_URL).loadJSON();
    fm.writeString(CACHE, JSON.stringify(d));      // 오프라인 대비 캐시
    return d;
  } catch (e) {
    if (fm.fileExists(CACHE)) return JSON.parse(fm.readString(CACHE));
    throw e;
  }
}

const data = await load();
const rows = data.series
  .filter(s => s.tier <= TIER_MAX)
  .map(s => {
    const d = (s.deadlines || []).filter(x => SUBMIT.includes(x.type) && dday(x.date) >= 0)
                                 .sort((a, b) => a.date.localeCompare(b.date))[0];
    return d ? { s, d, n: dday(d.date) } : null;
  })
  .filter(Boolean)
  .sort((a, b) => a.n - b.n);

const w = new ListWidget();
w.url = SITE_URL;
w.backgroundColor = new Color("#0d1014");
w.setPadding(12, 13, 12, 13);

const head = w.addStack();
const title = head.addText("학회 마감");
title.font = Font.semiboldSystemFont(12);
title.textColor = new Color("#8a94a2");
head.addSpacer();
const when = head.addText(data.generated.slice(5));
when.font = Font.mediumSystemFont(10);
when.textColor = new Color("#6b7684");
w.addSpacer(7);

if (!rows.length) {
  const t = w.addText("다가오는 마감 없음");
  t.font = Font.systemFont(13);
  t.textColor = new Color("#8a94a2");
}

const N = config.widgetFamily === "small" ? 3 : (config.widgetFamily === "large" ? 8 : 4);
for (const { s, d, n } of rows.slice(0, N)) {
  const row = w.addStack();
  row.centerAlignContent();

  const dd = row.addText(n === 0 ? "오늘" : `D-${n}`);
  dd.font = Font.semiboldRoundedSystemFont(12);
  dd.textColor = new Color(n <= 14 ? "#f07a70" : "#8a94a2");
  dd.lineLimit = 1;
  row.addSpacer(8);

  const name = row.addText(s.title);
  name.font = Font.semiboldSystemFont(13);
  // 학회 계열을 색으로 구분 — 사이트와 같은 규칙(파랑 AI / 주황 뇌과학)
  name.textColor = new Color(s.group === "neuro" ? "#e0a24e" : "#7fa3ee");
  name.lineLimit = 1;

  if (config.widgetFamily !== "small") {
    row.addSpacer();
    const date = row.addText(d.date.slice(2).replace(/-/g, "."));
    date.font = Font.regularSystemFont(11);
    date.textColor = new Color("#6b7684");
    date.lineLimit = 1;
  }
  w.addSpacer(5);
}
w.addSpacer();

if (config.runsInWidget) Script.setWidget(w);
else await w.presentMedium();
Script.complete();
