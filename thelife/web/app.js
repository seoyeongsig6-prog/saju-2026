/* The Life — 프런트엔드 */
const $ = (s) => document.querySelector(s);
const api = async (path, opts = {}) => {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" }, ...opts,
  });
  return r.json();
};

let STATE = null;

/* ---------- 부팅 ---------- */
async function boot() {
  STATE = await api("/api/state");
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
    b.className = "preset";
    b.innerHTML = `<span class="cat">${p.type}</span><b>${p.name}</b>
      <small>${p.era}<br>목표 — ${p.goal}</small>`;
    b.onclick = async () => {
      b.disabled = true; b.querySelector("b").textContent = "세계를 만드는 중…";
      await api("/api/avatar/preset", { method: "POST", body: JSON.stringify({ scenario_id: p.id }) });
      boot();
    };
    list.appendChild(b);
  });
}

$("#btn-search").onclick = async () => {
  const name = $("#person-search").value.trim();
  if (!name) return;
  const r = await api("/api/search_person", { method: "POST", body: JSON.stringify({ name }) });
  const box = $("#search-result");
  if (r.found) {
    box.classList.add("hidden");
    await api("/api/avatar/preset", { method: "POST", body: JSON.stringify({ scenario_id: r.scenario_id }) });
    boot();
    return;
  }
  box.classList.remove("hidden");
  box.textContent = r.message;
  if (r.blocked) box.style.borderColor = "var(--accent)";
};

$("#btn-custom").onclick = async () => {
  const form = {
    name: $("#c-name").value.trim(),
    age: $("#c-age").value.trim() || "30",
    occupation: $("#c-occupation").value.trim() || "자유인",
    era: $("#c-era").value,
    persona: $("#c-persona").value.trim() || "성실하고 다정하다",
    goal: $("#c-goal").value.trim(),
  };
  if (!form.name || !form.goal) { notice("이름과 인생 목표를 알려주세요."); return; }
  $("#btn-custom").disabled = true;
  $("#btn-custom").textContent = "세계를 만드는 중…";
  const r = await api("/api/avatar/custom", { method: "POST", body: JSON.stringify(form) });
  $("#btn-custom").disabled = false;
  $("#btn-custom").textContent = "이 삶을 시작한다";
  if (r.blocked) { notice(r.message); return; }
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
  $("#h-day").textContent = `${s.season.day_count}일째의 삶 · ${s.vtime}`;
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
  ["now", "feed", "story"].forEach((p) =>
    $(`#pane-${p}`).classList.toggle("hidden", p !== name));
  if (name === "feed") loadFeed();
  if (name === "story") loadStory();
  if (name === "now") loadNow();
}

/* ---------- 지금 (스트리밍) ---------- */
let streaming = false;
async function loadNow() {
  if (streaming) return;
  streaming = true;
  const box = $("#now-scene");
  box.innerHTML = "";
  $("#now-time").textContent = `${STATE.vday} ${STATE.vtime} — 지금 이 순간`;
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

/* ---------- 그동안 ---------- */
async function loadFeed() {
  const data = await api("/api/feed");
  const box = $("#feed-list");
  box.innerHTML = "";
  let lastDay = null;
  data.events.forEach((e) => {
    if (e.day !== lastDay) {
      const sep = document.createElement("div");
      sep.className = "day-sep";
      sep.textContent = e.day;
      box.appendChild(sep);
      lastDay = e.day;
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
    c.innerHTML = `<h4>${e.title} <small style="color:var(--dim)">${e.day}</small></h4><p>${e.body || ""}</p>`;
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
