"use strict";

const EMOJI = { rock: "✊", paper: "✋", scissors: "✌️" };
const WORDS  = ["Rock", "Paper", "Scissors", "Shoot!"];
const COLORS = ["#f87171", "#38bdf8", "#4ade80", "#fbbf24"];

let state = null;
let countdownTimer = null;
let countdownIndex = 0;

const els = {
  countdown:     document.getElementById("countdown"),
  countdownWord: document.getElementById("countdown-word"),
  resultArea:    document.getElementById("result-area"),
  playerEmoji:   document.getElementById("player-emoji"),
  computerEmoji: document.getElementById("computer-emoji"),
  resultText:    document.getElementById("result-text"),
  choiceBtns:    document.querySelectorAll(".choice-btn"),
  newGame:       document.getElementById("new-game"),
  scorePlayer:   document.getElementById("score-player"),
  scoreHangman:  document.getElementById("score-hangman"),
  nameBtn:       document.getElementById("name-btn"),
  nameInput:     document.getElementById("name-input"),
  nameList:      document.getElementById("name-list"),
};

// ---- Countdown animation ----

function showWord() {
  const el = els.countdownWord;
  el.textContent = WORDS[countdownIndex];
  el.style.color  = COLORS[countdownIndex];
  el.classList.remove("flash");
  void el.offsetWidth; // force reflow to restart the CSS animation
  el.classList.add("flash");
}

function startCountdown() {
  if (countdownTimer) return;
  countdownIndex = 0;
  showWord();
  countdownTimer = setInterval(() => {
    countdownIndex = (countdownIndex + 1) % WORDS.length;
    showWord();
  }, 600);
}

function stopCountdown() {
  clearInterval(countdownTimer);
  countdownTimer = null;
}

// ---- API helpers ----

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return res.json();
}

async function loadState() {
  render(await (await fetch("/rps/state")).json());
}

async function play(choice) {
  if (!state || state.over) return;
  stopCountdown();
  render(await postJSON("/rps/play", { choice }));
}

async function startNew() {
  stopCountdown();
  render(await postJSON("/rps/new", {}));
}

async function setName(name) {
  await postJSON("/name", { name: name || "" });
  render(await (await fetch("/rps/state")).json());
}

// ---- Render ----

function render(s) {
  state = s;

  if (s.score) {
    els.scorePlayer.textContent  = s.score.player;
    els.scoreHangman.textContent = s.score.hangman;
  }
  els.nameBtn.textContent = s.name || "Guest";

  if (s.over) {
    stopCountdown();
    els.countdown.hidden  = true;
    els.resultArea.hidden = false;

    els.playerEmoji.textContent   = EMOJI[s.player_choice]   || "";
    els.computerEmoji.textContent = EMOJI[s.computer_choice] || "";

    els.resultText.className = "result-text";
    if (s.result === "win") {
      els.resultText.textContent = "🎉 You win!";
      els.resultText.classList.add("win");
    } else if (s.result === "loss") {
      els.resultText.textContent = "💻 Computer wins!";
      els.resultText.classList.add("loss");
    } else {
      els.resultText.textContent = "🤝 It's a tie!";
      els.resultText.classList.add("tie");
    }

    els.choiceBtns.forEach(btn => {
      btn.disabled = true;
      btn.classList.toggle("chosen", btn.dataset.choice === s.player_choice);
    });
  } else {
    els.countdown.hidden  = false;
    els.resultArea.hidden = true;
    els.choiceBtns.forEach(btn => {
      btn.disabled = false;
      btn.classList.remove("chosen");
    });
    startCountdown();
  }
}

// ---- Event listeners ----

els.choiceBtns.forEach(btn => {
  btn.addEventListener("click", () => play(btn.dataset.choice));
});

els.newGame.addEventListener("click", startNew);

// ---- Inline name editor (same pattern as other game pages) ----

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
  els.nameBtn.hidden  = true;
  els.nameInput.hidden = false;
  renderNameList("");
  els.nameInput.focus();
}

function hideNameEditor() {
  els.nameInput.hidden = true;
  els.nameList.hidden  = true;
  els.nameBtn.hidden   = false;
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
