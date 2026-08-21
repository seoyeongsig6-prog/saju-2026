// 웹 자산(../web)을 네이티브 앱 www/ 로 굽는 빌드 스크립트.
//  1) ../web 를 www 로 복사
//  2) www/app-config.js 생성 — API 서버 주소 + RevenueCat 키/상품ID 주입
//  3) iap/iap.src.js 를 www/iap.js 로 번들 (RevenueCat 플러그인 포함)
//  4) www/writer.html 에 app-config.js, iap.js <script> 삽입 (원본 web/ 은 건드리지 않음)
//
// 설정은 환경변수로 덮어쓴다 (없으면 아래 기본값/placeholder 사용):
//   API_BASE       배포된 백엔드 주소 (예: https://thelife.onrender.com)
//   RC_IOS_KEY     RevenueCat iOS 공개 SDK 키 (appl_...)
//   RC_ANDROID_KEY RevenueCat Android 공개 SDK 키 (goog_...)
//   PRODUCT_MASTER MASTER 구독 상품 ID (App Store/Play에 등록한 값)
//   PRODUCT_PRO    프로 구독 상품 ID
import { cpSync, rmSync, existsSync, readFileSync, writeFileSync, mkdirSync,
         readdirSync, unlinkSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const here = dirname(fileURLToPath(import.meta.url));
const WEB = resolve(here, "..", "web");
const WWW = resolve(here, "www");

const cfg = {
  API_BASE:       process.env.API_BASE       || "https://thelife-mpj5.onrender.com",
  RC_IOS_KEY:     process.env.RC_IOS_KEY     || "appl_REPLACE_ME",
  RC_ANDROID_KEY: process.env.RC_ANDROID_KEY || "goog_REPLACE_ME",
  PRODUCT_MASTER: process.env.PRODUCT_MASTER || "novelist.master.monthly",
  PRODUCT_PRO:    process.env.PRODUCT_PRO    || "novelist.pro.monthly",
  ADMOB_IOS_BANNER: process.env.ADMOB_IOS_BANNER || "",
  ADMOB_IOS_INTERSTITIAL: process.env.ADMOB_IOS_INTERSTITIAL || "",
  ADMOB_ANDROID_BANNER: process.env.ADMOB_ANDROID_BANNER || "",
  ADMOB_ANDROID_INTERSTITIAL: process.env.ADMOB_ANDROID_INTERSTITIAL || "",
  ADMOB_IOS_APP_ID: process.env.ADMOB_IOS_APP_ID || "ca-app-pub-3940256099942544~1458002511",
  ADMOB_ANDROID_APP_ID: process.env.ADMOB_ANDROID_APP_ID || "ca-app-pub-3940256099942544~3347511713",
};

// 잘못된 서버나 테스트 키가 들어간 앱을 스토어에 올리는 사고를 빌드 단계에서 차단한다.
if (process.env.RELEASE_BUILD === "1") {
  const errors = [];
  if (!process.env.API_BASE || !/^https:\/\//.test(cfg.API_BASE) || /localhost|127\.0\.0\.1|REPLACE/i.test(cfg.API_BASE))
    errors.push("API_BASE에 운영 HTTPS 서버 주소가 필요합니다.");
  if (!/^appl_/.test(cfg.RC_IOS_KEY) || /REPLACE/i.test(cfg.RC_IOS_KEY))
    errors.push("RC_IOS_KEY에 RevenueCat iOS 공개 키가 필요합니다.");
  if (!/^goog_/.test(cfg.RC_ANDROID_KEY) || /REPLACE/i.test(cfg.RC_ANDROID_KEY))
    errors.push("RC_ANDROID_KEY에 RevenueCat Android 공개 키가 필요합니다.");
  for (const key of ["ADMOB_IOS_BANNER", "ADMOB_IOS_INTERSTITIAL", "ADMOB_ANDROID_BANNER", "ADMOB_ANDROID_INTERSTITIAL"])
    if (!/^ca-app-pub-/.test(cfg[key])) errors.push(`${key}에 AdMob 광고 단위 ID가 필요합니다.`);
  for (const key of ["ADMOB_IOS_APP_ID", "ADMOB_ANDROID_APP_ID"])
    if (!/^ca-app-pub-\d+~\d+$/.test(cfg[key]) || cfg[key].includes("3940256099942544"))
      errors.push(`${key}에 운영 AdMob 앱 ID가 필요합니다.`);
  if (errors.length) throw new Error("출시 빌드 중단:\n- " + errors.join("\n- "));
}

// 네이티브 SDK는 앱 ID를 웹 설정이 아니라 각 플랫폼 메타데이터에서 읽는다.
const androidStrings = resolve(here, "android", "app", "src", "main", "res", "values", "strings.xml");
if (existsSync(androidStrings)) {
  let s = readFileSync(androidStrings, "utf8");
  if (s.includes('name="admob_app_id"'))
    s = s.replace(/(<string name="admob_app_id">)[^<]*(<\/string>)/, `$1${cfg.ADMOB_ANDROID_APP_ID}$2`);
  else s = s.replace("</resources>", `    <string name="admob_app_id">${cfg.ADMOB_ANDROID_APP_ID}</string>\n</resources>`);
  writeFileSync(androidStrings, s);
}
const iosPlist = resolve(here, "ios", "App", "App", "Info.plist");
if (existsSync(iosPlist)) {
  let s = readFileSync(iosPlist, "utf8");
  if (s.includes("<key>GADApplicationIdentifier</key>"))
    s = s.replace(/(<key>GADApplicationIdentifier<\/key>\s*<string>)[^<]*(<\/string>)/,
      `$1${cfg.ADMOB_IOS_APP_ID}$2`);
  else s = s.replace("</dict>", `\t<key>GADApplicationIdentifier</key>\n\t<string>${cfg.ADMOB_IOS_APP_ID}</string>\n</dict>`);
  writeFileSync(iosPlist, s);
}

// 1) 웹 자산 복사
if (!existsSync(WEB)) { console.error("web/ 폴더를 찾을 수 없어요:", WEB); process.exit(1); }
rmSync(WWW, { recursive: true, force: true });
mkdirSync(WWW, { recursive: true });
cpSync(WEB, WWW, { recursive: true });

// 1-b) 웹은 자산을 /static/ 로 서빙하지만, 앱 www 안에서는 파일이 평면으로 놓인다.
//      모든 html 의 절대경로 /static/ 을 상대경로로 바꾼다.
for (const f of readdirSync(WWW)) {
  if (!f.endsWith(".html")) continue;
  const p = resolve(WWW, f);
  writeFileSync(p, readFileSync(p, "utf8")
    .replaceAll("/static/", "")
    .replaceAll('href="/privacy"', 'href="privacy.html"')
    .replaceAll('href="/terms"', 'href="terms.html"')
    .replaceAll('href="/delete-account"', 'href="delete-account.html"'));
}

// 2) app-config.js — writer.js 보다 먼저 로드되어 전역 설정을 심는다
writeFileSync(resolve(WWW, "app-config.js"),
  `/* 빌드 시 자동 생성 — 직접 수정 금지 */\n` +
  `window.NOVELIST_API_BASE=${JSON.stringify(cfg.API_BASE)};\n` +
  `window.NOVELIST_IAP_CONFIG=${JSON.stringify({
    iosKey: cfg.RC_IOS_KEY, androidKey: cfg.RC_ANDROID_KEY,
    products: { light: cfg.PRODUCT_MASTER, pro: cfg.PRODUCT_PRO },
  })};\n` +
  `window.NOVELIST_AD_CONFIG=${JSON.stringify({
    ios: { banner: cfg.ADMOB_IOS_BANNER, interstitial: cfg.ADMOB_IOS_INTERSTITIAL },
    android: { banner: cfg.ADMOB_ANDROID_BANNER, interstitial: cfg.ADMOB_ANDROID_INTERSTITIAL },
  })};\n`);

// 3) IAP 브리지 번들 (RevenueCat 플러그인을 포함해 window.NovelistIAP 로 노출)
await build({
  entryPoints: [resolve(here, "iap", "iap.src.js")],
  outfile: resolve(WWW, "iap.js"),
  bundle: true, format: "iife", target: "es2019", minify: true,
});

// 4) 앱의 진입 화면은 '더 노벨리스트'(writer.html) 다. Capacitor 는 www/index.html 을
//    로드하므로, 스크립트를 주입한 writer.html 을 index.html 로 굽는다.
let html = readFileSync(resolve(WWW, "writer.html"), "utf8");
if (!html.includes("app-config.js")) {          // app-config 는 writer.js 보다 먼저
  html = html.replace(/<script([^>]*)src=["']writer\.js["']([^>]*)>/,
    `<script src="app-config.js"></script>\n  <script$1src="writer.js"$2>`);
}
if (!html.includes("iap.js")) {                 // iap 브리지는 마지막에
  html = html.replace("</body>", `  <script src="iap.js"></script>\n</body>`);
}
writeFileSync(resolve(WWW, "index.html"), html);
unlinkSync(resolve(WWW, "writer.html"));         // 중복 방지 — 진입은 index.html 하나로

console.log("빌드 완료 → www/");
console.log("  API_BASE   :", cfg.API_BASE);
console.log("  RC iOS key :", cfg.RC_IOS_KEY.slice(0, 10) + "…");
console.log("  상품 ID    : MASTER=" + cfg.PRODUCT_MASTER + "  PRO=" + cfg.PRODUCT_PRO);
if (cfg.RC_IOS_KEY.includes("REPLACE") || !cfg.API_BASE)
  console.log("\n⚠  아직 placeholder 값이 있어요. README 의 '환경변수'를 채워 다시 빌드하세요.");
