// window.NovelistIAP — 네이티브 인앱 결제 브리지 (RevenueCat).
// 이 파일만 esbuild 로 번들되어 www/iap.js 가 된다. 웹 프런트(writer.js)는
// window.NovelistIAP 의 존재 여부만 보고 결제를 호출하므로, 스토어·플러그인
// 버전에 종속되는 코드는 전부 여기에만 모여 있다.
import { Capacitor } from "@capacitor/core";
import {
  Purchases, LOG_LEVEL, PURCHASES_ERROR_CODE,
} from "@revenuecat/purchases-capacitor";

const CFG = window.NOVELIST_IAP_CONFIG || {};
const UID = localStorage.getItem("thelife_uid") || undefined;   // 서버 X-User-Id 와 동일하게

// tier -> 이 offering 안에서 찾을 상품 식별자
const PRODUCT = CFG.products || {};

let _offerings = null;

async function init() {
  if (!Capacitor.isNativePlatform()) return false;
  const apiKey = Capacitor.getPlatform() === "ios" ? CFG.iosKey : CFG.androidKey;
  if (!apiKey || apiKey.includes("REPLACE")) {
    console.warn("[IAP] RevenueCat 키가 설정되지 않았어요.");
    return false;
  }
  await Purchases.setLogLevel({ level: LOG_LEVEL.WARN });
  // appUserID 를 우리 기기 UUID 로 고정 → 서버가 RevenueCat 에서 같은 사용자로 조회 가능
  await Purchases.configure({ apiKey, appUserID: UID });
  return true;
}

async function offerings() {
  if (!_offerings) _offerings = (await Purchases.getOfferings()).offerings;
  return _offerings;
}

// tier 에 해당하는 RevenueCat 패키지를 찾는다 (상품 식별자로 매칭).
async function packageFor(tier) {
  const wanted = PRODUCT[tier];
  const offs = await offerings();
  const pools = [];
  if (offs.current) pools.push(offs.current);
  for (const k in (offs.all || {})) pools.push(offs.all[k]);
  for (const off of pools) {
    for (const p of (off.availablePackages || [])) {
      const pid = p.product && p.product.identifier;
      if (!wanted || pid === wanted) return p;   // 지정 상품 우선, 없으면 첫 패키지
    }
  }
  return null;
}

const ready = init().catch((e) => { console.warn("[IAP] init 실패", e); return false; });

window.NovelistIAP = {
  ready,
  async purchase(tier) {
    if (!(await ready)) return { ok: false, error: "결제를 사용할 수 없어요." };
    const pkg = await packageFor(tier);
    if (!pkg) return { ok: false, error: "상품을 찾을 수 없어요. 잠시 후 다시 시도해 주세요." };
    try {
      await Purchases.purchasePackage({ aPackage: pkg });
      return { ok: true };
    } catch (e) {
      if (e && (e.code === PURCHASES_ERROR_CODE.PURCHASE_CANCELLED_ERROR ||
                e.userCancelled)) return { cancelled: true };
      return { ok: false, error: (e && e.message) || "결제에 실패했어요." };
    }
  },
  async restore() {
    if (!(await ready)) return { ok: false };
    await Purchases.restorePurchases();
    return { ok: true };
  },
};
