"use strict";

const els = {
  scorePlayer: document.getElementById("score-player"),
  scoreHangman: document.getElementById("score-hangman"),
  nameBtn: document.getElementById("name-btn"),
  nameInput: document.getElementById("name-input"),
  nameList: document.getElementById("name-list"),
};

let state = null;

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return res.json();
}

async function loadState() {
  render(await (await fetch("/state")).json());
}

async function setName(name) {
  render(await postJSON("/name", { name: name || "" }));
}

function render(s) {
  state = s;
  // Use total_score (sum across all games) for the launcher display.
  const sc = s.total_score || s.score;
  if (sc) {
    els.scorePlayer.textContent = sc.player;
    els.scoreHangman.textContent = sc.hangman;
  }
  els.nameBtn.textContent = s.name || "Guest";
}

// ----- Inline name editor (same as hangman game) -----
let committing = false;

function commitName(value) {
  committing = true;
  hideNameEditor();
  setName(value);
}

function addNameOption(label, value) {
  const li = document.createElement("li");
  li.textContent = label;
  li.addEventListener("mousedown", (e) => { e.preventDefault(); commitName(value); });
  els.nameList.appendChild(li);
}

function renderNameList(filter) {
  const current = (state && state.name) || "";
  const f = filter.trim().toLowerCase();
  els.nameList.innerHTML = "";
  if (current && "guest".startsWith(f)) addNameOption("Guest", "");
  for (const n of (state && state.names) || []) {
    if (n !== current && n.toLowerCase().startsWith(f)) addNameOption(n, n);
  }
  els.nameList.hidden = els.nameList.childElementCount === 0;
}

function showNameEditor() {
  els.nameInput.value = "";
  els.nameBtn.hidden = true;
  els.nameInput.hidden = false;
  renderNameList("");
  els.nameInput.focus();
}

function hideNameEditor() {
  els.nameInput.hidden = true;
  els.nameList.hidden = true;
  els.nameBtn.hidden = false;
}

els.nameBtn.addEventListener("click", showNameEditor);
els.nameInput.addEventListener("focus", () => renderNameList(els.nameInput.value));
els.nameInput.addEventListener("input", () => renderNameList(els.nameInput.value));

els.nameInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    const v = els.nameInput.value.trim();
    if (v) commitName(v); else hideNameEditor();
  } else if (e.key === "Escape") {
    hideNameEditor();
  }
});

els.nameInput.addEventListener("blur", () => {
  if (committing) { committing = false; return; }
  const v = els.nameInput.value.trim();
  hideNameEditor();
  if (v) setName(v);
});

loadState();
