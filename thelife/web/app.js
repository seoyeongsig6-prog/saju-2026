/* The Life — 프런트엔드 */
const $ = (s) => document.querySelector(s);
const api = async (path, opts = {}) => {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" }, ...opts,
  });
  return r.json();
};

let STATE = null;

/* 달력 날짜 대신 '삶의 N일차'. 한 달을 넘으면 개월로 접는다 */
function dayLabel(n) {
  n = Math.max(1, n || 1);
  if (n <= 30) return `${n}일차`;
  const m = Math.floor((n - 1) / 30), d = ((n - 1) % 30) + 1;
  return `${m}개월 ${d}일차`;
}

/* ---------- 부팅 ---------- */
async function boot() {
  STATE = await api("/api/state");
  if (STATE && STATE.detail) {  // 서버 오류 — 원인을 그대로 보여준다 (디버그)
    notice(`${STATE.error}\n\n${STATE.detail}\n${(STATE.trace || []).join("\n")}`);
    return;
  }
  if (!STATE.avatar) {
    showCreate();
  } else {
    showMain();
  }
}

/* ---------- 생성 화면 ---------- */
async function showCreate() {
  $("#view-main").classList.add("hidden");
  $("#view-create").classList.remove("hidden");
  const data = await api("/api/presets");
  const list = $("#preset-list");
  list.innerHTML = "";
  data.presets.forEach((p) => {
    const b = document.createElement("button");
    b.className = "chip";
    b.textContent = `${p.name} · ${p.goal.length > 14 ? p.goal.slice(0, 14) + "…" : p.goal}`;
    b.onclick = () => {
      $("#c-name").value = p.name;
      $("#c-goal").value = p.goal;
      $("#c-name").scrollIntoView({ behavior: "smooth", block: "center" });
    };
    list.appendChild(b);
  });
}

$("#btn-more").onclick = () => {
  const f = $("#more-fields");
  const open = f.classList.toggle("hidden");
  $("#btn-more").textContent = open ? "자세히 정하기 ▾ (선택)" : "자세히 정하기 ▴";
};

$("#btn-custom").onclick = async () => {
  const form = {
    name: $("#c-name").value.trim(),
    age: $("#c-age").value.trim(),
    occupation: $("#c-occupation").value.trim(),
    era: $("#c-era").value.trim(),
    persona: $("#c-persona").value.trim(),
    goal: $("#c-goal").value.trim(),
  };
  if (!form.name) { notice("이름을 알려주세요. 누구의 삶이든 좋아요."); return; }
  $("#btn-custom").disabled = true;
  $("#btn-custom").textContent = "그의 세계를 짓는 중… (10초쯤 걸려요)";
  const r = await api("/api/avatar/create", { method: "POST", body: JSON.stringify(form) });
  $("#btn-custom").disabled = false;
  $("#btn-custom").textContent = "이 삶을 시작한다";
  if (r.blocked) { notice(r.message); return; }
  if (!r.ok) {
    notice((r.error || "잠시 후 다시 시도해 주세요.") + (r.detail ? `\n\n${r.detail}` : ""));
    return;
  }
  boot();
};

/* ---------- 메인 화면 ---------- */
function showMain() {
  $("#view-create").classList.add("hidden");
  $("#view-main").classList.remove("hidden");
  renderHeader();
  openPane("now");
  loadNow();
}

function renderHeader() {
  const s = STATE;
  $("#h-name").textContent = s.avatar.name;
  $("#h-goal").textContent = `시즌 ${s.season.no} 목표 — ${s.season.goal}`;
  $("#h-day").textContent = `${dayLabel(s.season.day_count)}의 삶 · ${s.vtime}`;
  $("#h-luck").textContent = s.gauge.luck;
  const slots = $("#h-slots");
  slots.innerHTML = "";
  for (let i = 0; i < 3; i++) {
    const d = document.createElement("span");
    d.className = "slot" + (i < 3 - s.season.interventions_left ? " used" : "");
    slots.appendChild(d);
  }
  const total = s.season.milestones.length;
  $("#h-progress").style.width = `${Math.min(100, (s.season.milestone_idx / total) * 100)}%`;
  const u = $("#unread");
  if (s.unread > 0) { u.textContent = s.unread; u.classList.remove("hidden"); }
  else u.classList.add("hidden");
  $("#mockmark").textContent = s.mock_mode ? "목업 모드" : "";
  if (s.season.status === "done") openPane("story");
}

/* ---------- 탭 ---------- */
document.querySelectorAll(".tab").forEach((t) => {
  t.onclick = () => openPane(t.dataset.pane);
});
function openPane(name) {
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.pane === name));
  ["now", "feed", "dash", "story"].forEach((p) =>
    $(`#pane-${p}`).classList.toggle("hidden", p !== name));
  if (name === "feed") loadFeed();
  if (name === "dash") loadDash();
  if (name === "story") loadStory();
  if (name === "now") { loadNow(); loadHunches(); }
}

/* ---------- 상태 (대시보드) ---------- */
function fmtMoney(n, unit) {
  return `${Number(n).toLocaleString("ko-KR")}${unit}`;
}
function sparkline(hist, key, w = 150, h = 36) {
  if (!hist || hist.length < 2) return "";
  const vals = hist.map((r) => r[key]);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const pts = vals.map((v, i) =>
    `${(i / (vals.length - 1)) * w},${h - 4 - ((v - min) / span) * (h - 8)}`).join(" ");
  const up = vals[vals.length - 1] >= vals[0];
  return `<svg viewBox="0 0 ${w} ${h}" class="spark"><polyline points="${pts}"
    fill="none" stroke="${up ? "var(--accent)" : "var(--bad)"}" stroke-width="2"/></svg>`;
}
async function loadDash() {
  const d = await api("/api/dashboard");
  const box = $("#dash-body");
  if (!d || !d.name) { box.innerHTML = ""; return; }
  const hist = d.history || [];
  const prev = hist.length > 1 ? hist[hist.length - 2] : null;
  const moneyDiff = prev ? d.money - prev.money : 0;
  const arrow = moneyDiff > 0 ? `<span class="up">▲ ${fmtMoney(moneyDiff, "")}</span>`
    : moneyDiff < 0 ? `<span class="down">▼ ${fmtMoney(-moneyDiff, "")}</span>` : `<span class="flat">—</span>`;
  const total = d.milestones.length || 1;

  box.innerHTML = `
    <div class="stat-grid">
      <div class="stat wide">
        <div class="stat-label">재산</div>
        <div class="stat-value">${fmtMoney(d.money, d.money_unit)} ${arrow}</div>
        ${sparkline(hist, "money")}
      </div>
      <div class="stat">
        <div class="stat-label">체력</div>
        <div class="stat-value">${d.health}</div>
        <div class="hbar"><div class="hbar-fill ${d.health < 40 ? "low" : ""}" style="width:${d.health}%"></div></div>
      </div>
      <div class="stat">
        <div class="stat-label">지금의 마음</div>
        <div class="stat-value mood">${d.mood}</div>
      </div>
      <div class="stat">
        <div class="stat-label">이겨낸 것 / 잃은 것</div>
        <div class="stat-value">${d.overcome} <span class="dim">/</span> <span class="down">${d.scars}</span></div>
      </div>
      <div class="stat">
        <div class="stat-label">목표까지</div>
        <div class="stat-value">${d.milestone_idx}<span class="dim">/${total}</span></div>
        <div class="hbar"><div class="hbar-fill gold" style="width:${(d.milestone_idx / total) * 100}%"></div></div>
      </div>
    </div>

    <div class="story-h">곁의 사람들</div>
    <div class="cast-list">
      ${d.cast.map((m) => `
        <div class="cast-row">
          <div class="cast-name">${m.name}<small> · ${m.role}</small></div>
          <div class="cast-meta">${m.days_ago === null ? "아직 소식 없음" : m.days_ago === 0 ? "오늘 만남" : m.days_ago + "일 전"}</div>
          <div class="abar"><div class="abar-fill" style="width:${m.affinity}%"></div></div>
          <div class="cast-note">${m.note || ""}</div>
        </div>`).join("")}
    </div>

    <div class="story-h">지금 그를 붙잡고 있는 것</div>
    ${d.conflicts.length === 0 ? `<p class="hint">지금은 고요합니다. 폭풍 전일 수도 있고요.</p>` :
      d.conflicts.map((cf) => `
      <div class="conf-row">
        <span>${cf.title}</span>
        <span class="stages">
          ${["seed", "rise", "climax"].map((s, i) =>
            `<span class="sdot ${["seed","rise","climax"].indexOf(cf.stage) >= i ? "on" : ""}"></span>`).join("")}
          <small>${cf.stage_label}</small>
        </span>
      </div>`).join("")}
  `;
}

/* ---------- 지금 (스트리밍) ---------- */
let streaming = false;
async function loadNow() {
  if (streaming) return;
  streaming = true;
  const box = $("#now-scene");
  box.innerHTML = "";
  $("#now-time").textContent = `${dayLabel(STATE.season.day_count)} ${STATE.vtime} — 지금 이 순간`;
  try {
    const r = await fetch("/api/now");
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop();
      lines.forEach((ln) => addSceneLine(box, ln));
    }
    if (buf.trim()) addSceneLine(box, buf);
  } finally {
    streaming = false;
    STATE = await api("/api/state");
    renderHeader();
  }
}

function addSceneLine(box, line) {
  line = line.trim();
  if (!line) return;
  const m = line.match(/^(\p{L}[\p{L}\d ]{0,11}):\s*["“]?(.+?)["”]?$/u);
  const el = document.createElement("div");
  if (m) {
    const isMe = STATE && m[1].trim() === STATE.avatar.name;
    el.className = "bubble" + (isMe ? " me" : "");
    el.innerHTML = `<span class="who">${m[1].trim()}</span>${m[2]}`;
  } else {
    el.className = "narr";
    el.textContent = line;
  }
  box.appendChild(el);
  el.scrollIntoView({ behavior: "smooth", block: "end" });
}
$("#btn-peek").onclick = loadNow;

/* ---------- 예감 ---------- */
async function loadHunches() {
  const d = await api("/api/hunches");
  const area = $("#hunch-area");
  area.innerHTML = "";
  (d.open || []).forEach((h) => {
    const el = document.createElement("div");
    el.className = "hunch-open";
    el.innerHTML = `⏳ <b>${h.title}</b> — ${h.direction === "good" ? "이겨낼 것이다" : "쉽지 않을 것이다"}에 행운 ${h.luck}을 맡겨둠`;
    area.appendChild(el);
  });
  (d.offerable || []).forEach((o) => {
    const el = document.createElement("div");
    el.className = "hunch-card";
    el.innerHTML = `
      <div class="hunch-head">예감이 스칩니다</div>
      <div class="hunch-title">${o.title} <small>· ${o.stage_label}</small></div>
      <div class="hunch-hint">${o.hint || ""}</div>
      <div class="hunch-luck">행운
        <label><input type="radio" name="hl-${o.conflict_id}" value="10" checked>10</label>
        <label><input type="radio" name="hl-${o.conflict_id}" value="30">30</label>
        <label><input type="radio" name="hl-${o.conflict_id}" value="50">50</label>
        <span class="dim">— 맞으면 두 배로</span>
      </div>
      <div class="hunch-btns">
        <button data-dir="good">이겨낼 것이다</button>
        <button data-dir="bad">이번엔 어렵겠다</button>
      </div>`;
    el.querySelectorAll(".hunch-btns button").forEach((b) => {
      b.onclick = async () => {
        const luck = el.querySelector(`input[name="hl-${o.conflict_id}"]:checked`).value;
        const r = await api("/api/hunch", { method: "POST",
          body: JSON.stringify({ conflict_id: o.conflict_id, direction: b.dataset.dir, luck: Number(luck) }) });
        if (!r.ok) { notice(r.error); return; }
        STATE = await api("/api/state");
        renderHeader();
        loadHunches();
      };
    });
    area.appendChild(el);
  });
}

/* ---------- 그동안 ---------- */
async function loadFeed() {
  const data = await api("/api/feed");
  const box = $("#feed-list");
  box.innerHTML = "";
  let lastDay = null;
  data.events.forEach((e) => {
    if (e.day_no !== lastDay) {
      const sep = document.createElement("div");
      sep.className = "day-sep";
      sep.textContent = dayLabel(e.day_no);
      box.appendChild(sep);
      lastDay = e.day_no;
    }
    const c = document.createElement("div");
    c.className = `card k-${e.kind}` + (e.read ? "" : " unread");
    c.innerHTML = `<h4>${e.title || ""}</h4><p>${e.body || ""}</p>`;
    box.appendChild(c);
  });
  STATE = await api("/api/state");
  renderHeader();
}

/* ---------- 이야기 ---------- */
async function loadStory() {
  const d = await api("/api/story");
  const box = $("#story-body");
  box.innerHTML = "";
  const mh = document.createElement("div");
  mh.className = "story-h"; mh.textContent = `목표 — ${d.goal}`;
  box.appendChild(mh);
  d.milestones.forEach((m, i) => {
    const el = document.createElement("div");
    el.className = "mile" + (i < d.milestone_idx ? " done" : "");
    el.innerHTML = `<span class="dot">●</span><span>${m}</span>`;
    box.appendChild(el);
  });

  if (d.biography) {
    const bh = document.createElement("div");
    bh.className = "story-h"; bh.textContent = "완결된 이야기 — 전기";
    box.appendChild(bh);
    const bio = document.createElement("div");
    bio.className = "bio"; bio.textContent = d.biography;
    box.appendChild(bio);
    const wrap = document.createElement("div");
    wrap.className = "season-end";
    wrap.innerHTML = `
      <div class="story-h">이 삶을 이어갈까요?</div>
      <input id="next-goal" placeholder="다음 목표 (비우면 자동)">
      <button id="btn-cont" class="primary">이 아바타로 계속 (시즌 ${(STATE.season.no||1)+1})</button>
      <button id="btn-new">새로운 삶을 시작</button>`;
    box.appendChild(wrap);
    $("#btn-cont").onclick = async () => {
      await api("/api/season/next", { method: "POST",
        body: JSON.stringify({ mode: "continue", goal: $("#next-goal").value }) });
      boot();
    };
    $("#btn-new").onclick = async () => {
      await api("/api/season/next", { method: "POST", body: JSON.stringify({ mode: "new" }) });
      boot();
    };
    return;
  }

  const eh = document.createElement("div");
  eh.className = "story-h"; eh.textContent = "지금까지의 굵직한 순간들";
  box.appendChild(eh);
  d.episodes.forEach((e) => {
    const c = document.createElement("div");
    c.className = `card k-${e.kind}`;
    c.style.marginBottom = "10px";
    c.innerHTML = `<h4>${e.title} <small style="color:var(--dim)">${dayLabel(e.day_no)}</small></h4><p>${e.body || ""}</p>`;
    box.appendChild(c);
  });
}

/* ---------- 행운 모달 ---------- */
function openModal() {
  $("#m-left").textContent = STATE.season.interventions_left;
  $("#m-luck").textContent = STATE.gauge.luck;
  $("#m-ads").textContent = STATE.gauge.ads_left;
  $("#modal").classList.remove("hidden");
}
$("#btn-intervene").onclick = openModal;
$("#btn-gauge").onclick = openModal;
$("#btn-close").onclick = () => $("#modal").classList.add("hidden");

document.querySelectorAll(".size").forEach((b) => {
  b.onclick = async () => {
    const r = await api("/api/intervene", { method: "POST", body: JSON.stringify({ size: b.dataset.size }) });
    $("#modal").classList.add("hidden");
    if (!r.ok) { notice(r.error); return; }
    notice(`행운이 그의 세계로 스며듭니다.\n\n${r.body}`);
    STATE = await api("/api/state");
    renderHeader();
  };
});
$("#btn-ad").onclick = async () => {
  const r = await api("/api/ad", { method: "POST" });
  if (!r.ok) { notice(r.error); return; }
  STATE = await api("/api/state");
  renderHeader(); openModal();
};
$("#btn-buy").onclick = async () => {
  await api("/api/buy", { method: "POST" });
  STATE = await api("/api/state");
  renderHeader(); openModal();
};

/* ---------- 알림 ---------- */
function notice(text) {
  $("#notice-text").textContent = text;
  $("#notice").classList.remove("hidden");
}
$("#notice-close").onclick = () => $("#notice").classList.add("hidden");

/* ---------- 디버그 ---------- */
$("#btn-warp1").onclick = async () => { await api("/api/debug/timewarp", { method: "POST", body: JSON.stringify({ days: 1 }) }); boot(); };
$("#btn-warp7").onclick = async () => { await api("/api/debug/timewarp", { method: "POST", body: JSON.stringify({ days: 7 }) }); boot(); };
$("#btn-reset").onclick = async () => {
  if (!confirm("정말 이 삶을 떠나 새로 시작할까요?")) return;
  await fetch("/api/avatar", { method: "DELETE" });
  boot();
};

boot();
