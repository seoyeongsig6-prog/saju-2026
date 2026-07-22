/* The Novelist — 프런트엔드 */
const $ = (s) => document.querySelector(s);

let UID = localStorage.getItem("thelife_uid");
if (!UID) {
  UID = (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now());
  localStorage.setItem("thelife_uid", UID);
}
const api = async (path, opts = {}) => {
  const r = await fetch(path, {
    ...opts,
    headers: { "Content-Type": "application/json", "X-User-Id": UID, ...(opts.headers || {}) },
  });
  return r.json();
};

let WORK = null, CHAPTER = null;

function view(id) {
  ["w-home", "w-create", "w-work", "w-editor"].forEach((v) =>
    $(`#${v}`).classList.toggle("hidden", v !== id));
}
function notice(t) { $("#notice-text").textContent = t; $("#notice").classList.remove("hidden"); }
$("#notice-close").onclick = () => $("#notice").classList.add("hidden");
function busy(t) { $("#busy-text").textContent = t; $("#busy").classList.remove("hidden"); }
function unbusy() { $("#busy").classList.add("hidden"); }

/* ---------- 작품 목록 ---------- */
async function showHome() {
  view("w-home");
  const d = await api("/api/writer/works");
  const box = $("#w-list");
  box.innerHTML = "";
  (d.works || []).forEach((w) => {
    const el = document.createElement("button");
    el.className = "w-item";
    el.innerHTML = `<span class="del" data-id="${w.id}">✕</span><b>${w.title}</b>
      <small>${w.genre} · ${w.written}/${w.total_chapters}화</small>`;
    el.onclick = (ev) => {
      if (ev.target.classList.contains("del")) return delWork(w.id, w.title);
      openWork(w.id);
    };
    box.appendChild(el);
  });
}
async function delWork(id, title) {
  if (!confirm(`『${title}』을(를) 삭제할까요? 되돌릴 수 없어요.`)) return;
  await api(`/api/writer/works/${id}`, { method: "DELETE" });
  showHome();
}
$("#w-new").onclick = () => view("w-create");

/* ---------- 새 작품 — 작품설명서 파일로 ---------- */
$("#cb-go").onclick = async () => {
  const f = $("#c-brief-file").files[0];
  if (!f) { notice("작품설명서 파일을 먼저 선택해 주세요. (.txt .md .docx .pdf)"); return; }
  const fd = new FormData();
  fd.append("file", f);
  fd.append("genre", $("#cb-genre").value.trim());
  fd.append("total_chapters", Number($("#cb-total").value) || 25);
  busy("설명서를 정독하고 설계도를 만드는 중… (30초쯤)");
  const r = await fetch("/api/writer/works/from-brief", {
    method: "POST", body: fd, headers: { "X-User-Id": UID },
  }).then((x) => x.json()).catch((e) => ({ ok: false, error: String(e) }));
  unbusy();
  if (!r.ok) {
    notice((r.error || "실패했어요") + (r.detail ? `\n\n[원인] ${r.detail}` : ""));
    return;
  }
  if (r.outline_chapters >= 3) {
    notice(`계획서에서 ${r.outline_chapters}개 회차의 지정 내용을 찾았어요.\n` +
           `각 회차는 계획서에 적힌 그 화의 내용 그대로 집필됩니다.`);
  }
  openWork(r.id);
};

/* ---------- 새 작품 — 직접 입력 ---------- */
$("#c-go").onclick = async () => {
  const body = {
    genre: $("#c-genre").value.trim() || "현대 판타지",
    premise: $("#c-premise").value.trim(),
    ending: $("#c-ending").value.trim(),
    title: $("#c-title").value.trim(),
    style: $("#c-style").value.trim(),
    style_sample: $("#c-sample").value.trim(),
    total_chapters: Number($("#c-total").value) || 25,
  };
  if (!body.premise || !body.ending) { notice("로그라인과 결말은 작가만 정할 수 있어요. 두 칸을 채워주세요."); return; }
  busy("설계도를 만드는 중… 인물, 관계도, 15비트 플롯 (20초쯤)");
  const r = await api("/api/writer/works", { method: "POST", body: JSON.stringify(body) });
  unbusy();
  if (!r.ok) {
    notice((r.error || "실패했어요") + (r.detail ? `\n\n[원인] ${r.detail}` : "") +
      (r.trace ? `\n${r.trace.join("\n")}` : ""));
    return;
  }
  openWork(r.id);
};

/* ---------- 작품 화면 ---------- */
async function openWork(id) {
  const d = await api(`/api/writer/works/${id}`);
  if (!d.ok) { notice(d.error); return; }
  WORK = d.work;
  WORK.chapters = d.chapters;
  view("w-work");
  $("#wk-title").textContent = WORK.title;
  $("#wk-progress").textContent = `${d.chapters.length}/${WORK.total_chapters}화`;
  renderChapters();
  renderBible();
  wtab("chapters");
}

document.querySelectorAll(".wtab").forEach((t) => { t.onclick = () => wtab(t.dataset.wtab); });
function wtab(name) {
  document.querySelectorAll(".wtab").forEach((t) =>
    t.classList.toggle("active", t.dataset.wtab === name));
  $("#wt-chapters").classList.toggle("hidden", name !== "chapters");
  $("#wt-bible").classList.toggle("hidden", name !== "bible");
}

function renderChapters() {
  const box = $("#ch-list");
  box.innerHTML = "";
  if (!WORK.chapters.length) {
    box.innerHTML = `<p class="hint">아직 첫 회차가 없어요. 아래 버튼으로 1화를 시작하세요.<br>
      지시 없이 쓰면 플롯 지도대로, 지시를 넣으면 그 방향으로 씁니다.</p>`;
  }
  WORK.chapters.forEach((ch) => {
    const el = document.createElement("button");
    el.className = "ch-item";
    const o = (WORK.outline || []).find((x) => x.no === ch.no);
    const beat = WORK.beats[ch.beat_idx] || {};
    el.innerHTML = `<span class="ch-no">${ch.no}화</span> ${ch.title || ""}
      <small>${o ? "📋 계획서" : (beat.name || "")}</small>`;
    el.onclick = () => openChapter(ch.id);
    box.appendChild(el);
  });
}

function renderBible() {
  $("#bible-title").value = WORK.title || "";
  $("#bible-ending").value = WORK.ending || "";
  const bs = $("#brief-section");
  if (WORK.brief) {
    bs.classList.remove("hidden");
    $("#brief-body").textContent = WORK.brief;
  } else {
    bs.classList.add("hidden");
  }
  const spb = $("#style-profile-box");
  if (WORK.style_profile) {
    spb.classList.remove("hidden");
    spb.textContent = WORK.style_profile;
  } else {
    spb.classList.add("hidden");
  }
  $("#bible-sample").value = WORK.style_sample || "";
  const box = $("#bible-chars");
  box.innerHTML = "";
  WORK.characters.forEach((c, idx) => {
    const el = document.createElement("div");
    el.className = "b-char";
    el.innerHTML = `
      <button class="edit-ch" title="편집">✎</button>
      <b>${c.name}</b><span class="arch">${c.archetype || ""}</span>
      <p>${c.role || ""}<br>욕망 — ${c.want || ""} · 결핍 — ${c.need || ""}<br>비밀 — ${c.secret || ""}</p>`;
    el.querySelector(".edit-ch").onclick = () => editChar(el, idx);
    box.appendChild(el);
  });
  $("#bible-rels").innerHTML = WORK.relations.map((r) => `
    <div class="b-rel"><b>${r.a} ↔ ${r.b}</b> · ${r.type || ""} — ${r.tension || ""}</div>`).join("");
  const written = WORK.chapters.length;
  $("#bible-beats").innerHTML = WORK.beats.map((b, i) => {
    const lastBeat = written ? WORK.chapters[written - 1].beat_idx : -1;
    return `<div class="b-beat ${i <= lastBeat ? "done" : ""}">
      <span class="no">${i + 1}</span><b>${b.name}</b><span>${b.summary || ""}</span></div>`;
  }).join("");
}

/* ---------- 설정집 편집 ---------- */
function editChar(el, idx) {
  const c = WORK.characters[idx];
  el.innerHTML = `
    <div class="form">
      <div class="row2">
        <input id="ec-name" value="${c.name || ""}" placeholder="이름">
        <input id="ec-arch" value="${c.archetype || ""}" placeholder="원형">
      </div>
      <input id="ec-role" value="${c.role || ""}" placeholder="소개">
      <div class="row2">
        <input id="ec-want" value="${c.want || ""}" placeholder="외적 욕망">
        <input id="ec-need" value="${c.need || ""}" placeholder="내적 결핍">
      </div>
      <input id="ec-secret" value="${c.secret || ""}" placeholder="비밀">
      <div class="row2">
        <button class="primary" id="ec-save">저장</button>
        <button id="ec-cancel">취소</button>
      </div>
    </div>`;
  el.querySelector("#ec-cancel").onclick = () => renderBible();
  el.querySelector("#ec-save").onclick = async () => {
    const oldName = c.name;
    Object.assign(c, {
      name: el.querySelector("#ec-name").value.trim(),
      archetype: el.querySelector("#ec-arch").value.trim(),
      role: el.querySelector("#ec-role").value.trim(),
      want: el.querySelector("#ec-want").value.trim(),
      need: el.querySelector("#ec-need").value.trim(),
      secret: el.querySelector("#ec-secret").value.trim(),
    });
    if (oldName && c.name && oldName !== c.name) {
      // 이름이 바뀌면 관계도 속 이름도 따라간다
      WORK.relations.forEach((r) => {
        if (r.a === oldName) r.a = c.name;
        if (r.b === oldName) r.b = c.name;
      });
    }
    await saveBible();
    renderBible();
  };
}

async function saveBible() {
  const r = await api(`/api/writer/works/${WORK.id}/bible`, {
    method: "PUT",
    body: JSON.stringify({
      title: $("#bible-title").value.trim(),
      ending: $("#bible-ending").value.trim(),
      characters: WORK.characters, relations: WORK.relations, beats: WORK.beats,
    }),
  });
  if (!r.ok) notice(r.error || "저장 실패");
  else { WORK.title = $("#bible-title").value.trim(); $("#wk-title").textContent = WORK.title; }
}
$("#bible-save-core").onclick = async () => { await saveBible(); notice("저장했어요. 이후 회차부터 반영됩니다."); };

$("#bible-learn").onclick = async () => {
  const sample = $("#bible-sample").value.trim();
  if (sample.length < 300) { notice("문체를 배우려면 표본이 300자는 넘어야 해요."); return; }
  busy("문체를 학습하는 중… (15초쯤)");
  const r = await api(`/api/writer/works/${WORK.id}/style`, {
    method: "POST", body: JSON.stringify({ sample }),
  });
  unbusy();
  if (!r.ok) { notice(r.error + (r.detail ? `\n\n[원인] ${r.detail}` : "")); return; }
  WORK.style_profile = r.profile;
  WORK.style_sample = sample;
  renderBible();
  notice("문체를 배웠어요. 다음 회차부터 이 결로 씁니다.\n학습된 프로파일은 문체 섹션에서 확인하세요.");
};

$("#bible-revise").onclick = async () => {
  const directive = $("#bible-cmd").value.trim();
  if (!directive) { notice("무엇을 고칠지 알려주세요."); return; }
  busy("설정집을 고치는 중…");
  const r = await api(`/api/writer/works/${WORK.id}/bible/revise`, {
    method: "POST", body: JSON.stringify({ directive }),
  });
  unbusy();
  if (!r.ok) { notice((r.error || "실패") + (r.detail ? `\n\n[원인] ${r.detail}` : "")); return; }
  $("#bible-cmd").value = "";
  const d = await api(`/api/writer/works/${WORK.id}`);
  WORK = d.work; WORK.chapters = d.chapters;
  renderBible();
  notice("설정집을 고쳤어요. 이후 회차부터 반영됩니다.\n(이미 쓴 회차는 편집기에서 직접 고치거나 '다시 쓰기' 하세요)");
};

/* ---------- 회차 쓰기 ---------- */
$("#btn-write").onclick = async () => {
  busy(`${WORK.chapters.length + 1}화를 쓰는 중… (5,000자, 30초~1분)`);
  const r = await api(`/api/writer/works/${WORK.id}/chapters`, {
    method: "POST", body: JSON.stringify({ directive: $("#directive").value.trim() }),
  });
  unbusy();
  if (!r.ok) {
    notice((r.error || "실패했어요") + (r.detail ? `\n\n[원인] ${r.detail}` : "") +
      (r.trace ? `\n${r.trace.join("\n")}` : ""));
    return;
  }
  $("#directive").value = "";
  await openWork(WORK.id);
  openChapter(r.id);
};

/* ---------- 편집기 ---------- */
async function openChapter(id) {
  const d = await api(`/api/writer/chapters/${id}`);
  if (!d.ok) { notice("회차를 불러오지 못했어요"); return; }
  CHAPTER = d.chapter;
  view("w-editor");
  const beat = WORK.beats[CHAPTER.beat_idx] || {};
  $("#ed-beat").textContent = `${CHAPTER.no}화 · 비트: ${beat.name || ""}`;
  $("#ed-title").value = CHAPTER.title || "";
  $("#ed-body").value = CHAPTER.body || "";
  countChars();
}
$("#ed-body").addEventListener("input", countChars);
function countChars() {
  $("#ed-count").textContent = `${$("#ed-body").value.length.toLocaleString()}자`;
}
$("#ed-back").onclick = () => openWork(WORK.id);
$("#ed-save").onclick = async () => {
  const r = await api(`/api/writer/chapters/${CHAPTER.id}`, {
    method: "PUT",
    body: JSON.stringify({ title: $("#ed-title").value, body: $("#ed-body").value }),
  });
  notice(r.ok ? "저장했어요." : r.error);
};
$("#ed-copy").onclick = async () => {
  await navigator.clipboard.writeText($("#ed-body").value);
  notice("본문을 복사했어요. 연재 플랫폼에 붙여넣으세요.");
};
$("#ed-download").onclick = () => {
  const blob = new Blob([`${$("#ed-title").value}\n\n${$("#ed-body").value}`],
    { type: "text/plain;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${WORK.title}_${CHAPTER.no}화.txt`;
  a.click();
};
$("#ed-regen").onclick = async () => {
  const directive = prompt("다시 쓸 때의 지시 (비워도 됩니다):", CHAPTER.directive || "");
  if (directive === null) return;
  busy("다시 쓰는 중…");
  const r = await api(`/api/writer/chapters/${CHAPTER.id}/regenerate`, {
    method: "POST", body: JSON.stringify({ directive }),
  });
  unbusy();
  if (!r.ok) { notice(r.error); return; }
  openChapter(CHAPTER.id);
};
$("#ed-del").onclick = async () => {
  if (!confirm("이 회차를 삭제할까요?")) return;
  const r = await api(`/api/writer/chapters/${CHAPTER.id}`, { method: "DELETE" });
  if (!r.ok) { notice(r.error); return; }
  openWork(WORK.id);
};

showHome();
