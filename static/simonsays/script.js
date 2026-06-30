"use strict";

const els = {
  status:       document.getElementById("status"),
  newGame:      document.getElementById("new-game"),
  levelBtns:    document.getElementById("level-btns"),
  scorePlayer:  document.getElementById("score-player"),
  scoreHangman: document.getElementById("score-hangman"),
  bestScore:    document.getElementById("best-score"),
  nameBtn:      document.getElementById("name-btn"),
  nameInput:    document.getElementById("name-input"),
  nameList:     document.getElementById("name-list"),
};

const LEVEL_KEY = "simonsays.level";

const SPEEDS = {
  easy:   { on: 900, gap: 400 },
  medium: { on: 600, gap: 200 },
  hard:   { on: 350, gap: 150 },
};

// Classic Simon tones (Hz): green G#4, red D#4, yellow B3, blue G#3
const TONES = { green: 415, red: 310, yellow: 252, blue: 209 };

const TAP_MS = 300;  // player tap flash — short and snappy regardless of level

let state           = null;
let animating       = false;
let inputEnabled    = false;
let waitingForWatch = false;  // true during the between-round pause
let countingDown    = false;  // true during the pre-game countdown

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function disableBtns(off) {
  document.querySelectorAll(".simon-btn").forEach(b => { b.disabled = off; });
}

// Web Audio
let _audioCtx = null;
function getAudioCtx() {
  if (!_audioCtx) _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  return _audioCtx;
}
function playTone(color, durationMs) {
  try {
    const ctx  = getAudioCtx();
    const osc  = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = "sine";
    osc.frequency.value = TONES[color] || 330;
    const t   = ctx.currentTime;
    const dur = durationMs / 1000;
    gain.gain.setValueAtTime(0.4, t);
    gain.gain.exponentialRampToValueAtTime(0.001, t + dur);
    osc.start(t);
    osc.stop(t + dur);
  } catch (e) { /* audio unavailable */ }
}

// Flash a button with tone — used by both computer and player
async function flashBtn(color, durationMs) {
  const btn = document.getElementById("btn-" + color);
  if (!btn) return;
  btn.classList.add("lit");
  playTone(color, durationMs);
  await sleep(durationMs);
  btn.classList.remove("lit");
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return res.json();
}

async function playSequence(sequence, level) {
  animating = true;
  inputEnabled = false;
  disableBtns(true);
  const { on, gap } = SPEEDS[level] || SPEEDS.easy;
  for (const color of sequence) {
    await flashBtn(color, on);
    await sleep(gap);
  }
  animating = false;
  const s = await postJSON("/simonsays/ready", {});
  render(s);
}

// 5-second countdown shown on first page load.
// Cancelled (returns early) if render() is called (e.g. New Game button).
async function startCountdown(s) {
  countingDown = true;
  disableBtns(true);
  inputEnabled = false;
  for (let i = 5; i >= 1; i--) {
    if (!countingDown) return;
    els.status.textContent = "Simon Says in " + i + "…";
    els.status.className = "status";
    await sleep(1000);
  }
  if (!countingDown) return;
  countingDown = false;
  els.status.textContent = "Round 1 — watch carefully…";
  playSequence(s.sequence, s.level);
}

// 1-second pause between rounds. Clicking during the pause = loss.
async function startWatchWithPause(s) {
  const round = s.rounds + 1;
  els.status.textContent = "Round " + round + " — get ready…";
  els.status.className = "status";
  waitingForWatch = true;
  disableBtns(false);
  await sleep(1000);
  if (!waitingForWatch) return;
  waitingForWatch = false;
  disableBtns(true);
  playSequence(s.sequence, s.level);
}

// Player clicked during the between-round pause → they lose
async function earlyClick(color) {
  if (!waitingForWatch) return;
  waitingForWatch = false;
  disableBtns(true);
  await flashBtn(color, TAP_MS);
  const s = await postJSON("/simonsays/early", {});
  render(s);
}

async function tapColor(color) {
  if (!inputEnabled || !state || state.phase !== "play") return;
  inputEnabled = false;
  await flashBtn(color, TAP_MS);
  const s = await postJSON("/simonsays/tap", { color });
  render(s);
}

async function startNew(level) {
  countingDown    = false;  // cancel countdown if active
  waitingForWatch = false;  // cancel between-round pause if active
  const lvl = level || (state && state.level) || localStorage.getItem(LEVEL_KEY) || "easy";
  render(await postJSON("/simonsays/new", { level: lvl }));
}

// On page load: always start a fresh game, then show the countdown.
// Named players: server restores their saved level.
// Guests: use localStorage level.
async function loadState() {
  const cur   = await (await fetch("/simonsays/state")).json();
  const saved = localStorage.getItem(LEVEL_KEY);
  const body  = (!cur.name && saved) ? { level: saved } : {};
  const s     = await postJSON("/simonsays/new", body);

  // Update scoreboard and level buttons without triggering the animation
  state = s;
  if (s.score) {
    els.scorePlayer.textContent  = s.score.player  || 0;
    els.scoreHangman.textContent = s.score.hangman || 0;
    els.bestScore.textContent    = s.score.best    || 0;
  }
  els.nameBtn.textContent = s.name || "Guest";
  if (s.levels) renderLevelBtns(s.levels, s.level);

  startCountdown(s);
}

function renderLevelBtns(levels, current) {
  if (!els.levelBtns) return;
  els.levelBtns.innerHTML = "";
  for (const lvl of levels) {
    const btn = document.createElement("button");
    btn.textContent = lvl.charAt(0).toUpperCase() + lvl.slice(1);
    btn.className = "level-btn" + (lvl === current ? " active" : "");
    btn.addEventListener("click", () => {
      localStorage.setItem(LEVEL_KEY, lvl);
      startNew(lvl);
    });
    els.levelBtns.appendChild(btn);
  }
}

function render(s) {
  state           = s;
  countingDown    = false;  // cancel countdown if a new state arrives
  waitingForWatch = false;

  // Scoreboard
  if (s.score) {
    els.scorePlayer.textContent  = s.score.player  || 0;
    els.scoreHangman.textContent = s.score.hangman || 0;
    els.bestScore.textContent    = s.score.best    || 0;
  }
  els.nameBtn.textContent = s.name || "Guest";

  // Level buttons
  if (s.levels) renderLevelBtns(s.levels, s.level);

  // Status + button state
  els.status.className = "status";
  const round = s.rounds + 1;

  if (s.phase === "over") {
    disableBtns(true);
    inputEnabled = false;
    els.status.textContent = "Game over — you completed " + s.rounds +
      " round" + (s.rounds === 1 ? "" : "s") + "!";
    els.status.classList.add("lost");
  } else if (s.phase === "play") {
    disableBtns(false);
    inputEnabled = true;
    els.status.textContent = "Round " + round + " — your turn!";
  } else if (s.phase === "watch") {
    disableBtns(true);
    inputEnabled = false;
    if (animating) return;
    if (s.rounds > 0) {
      startWatchWithPause(s);
    } else {
      // New game via button or level switch — start immediately, no countdown
      els.status.textContent = "Round 1 — watch carefully…";
      playSequence(s.sequence, s.level);
    }
  }
}

// Wire up color buttons
document.querySelectorAll(".simon-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    if (waitingForWatch) {
      earlyClick(btn.dataset.color);
    } else {
      tapColor(btn.dataset.color);
    }
  });
});

els.newGame.addEventListener("click", () => startNew());

// After setting name, re-fetch Simon state (name POST returns Hangman payload)
async function setName(name) {
  await postJSON("/name", { name: name || "" });
  render(await (await fetch("/simonsays/state")).json());
}

// ----- Inline name editor -----
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
  const trimmed = filter.trim();
  const exactMatch = (state && state.names || []).some(n => n.toLowerCase() === trimmed.toLowerCase());
  if (trimmed && !exactMatch && trimmed.toLowerCase() !== "guest") {
    addNameOption(`+ Add "${trimmed}"`, trimmed);
  } else if (!trimmed) {
    const li = document.createElement("li");
    li.textContent = "+ Add new player…";
    li.className = "name-add-hint";
    li.addEventListener("mousedown", e => { e.preventDefault(); els.nameInput.focus(); });
    els.nameList.appendChild(li);
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
