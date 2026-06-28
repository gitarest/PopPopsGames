"use strict";

const els = {
  board: document.getElementById("board"),
  status: document.getElementById("status"),
  newGame: document.getElementById("new-game"),
  scorePlayer: document.getElementById("score-player"),
  scoreHangman: document.getElementById("score-hangman"),
  nameBtn: document.getElementById("name-btn"),
  nameInput: document.getElementById("name-input"),
  nameList: document.getElementById("name-list"),
};

let state = null;

// Build 9 board cells once.
const cells = [];
for (let i = 0; i < 9; i++) {
  const btn = document.createElement("button");
  btn.className = "ttt-cell";
  btn.setAttribute("aria-label", "cell " + i);
  btn.addEventListener("click", () => move(i));
  els.board.appendChild(btn);
  cells.push(btn);
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return res.json();
}

async function loadState() {
  render(await (await fetch("/ttt/state")).json());
}

async function move(cell) {
  if (!state || state.over || state.board[cell] !== null) return;
  render(await postJSON("/ttt/move", { cell }));
}

async function startNew() {
  render(await postJSON("/ttt/new", {}));
}

// After setting the name the server returns a Hangman payload; re-fetch the
// TTT state so the board is rendered from the right response shape.
async function setName(name) {
  await postJSON("/name", { name: name || "" });
  render(await (await fetch("/ttt/state")).json());
}

function render(s) {
  state = s;

  // Scoreboard
  if (s.score) {
    els.scorePlayer.textContent = s.score.player;
    els.scoreHangman.textContent = s.score.hangman;
  }
  els.nameBtn.textContent = s.name || "Guest";

  // Board cells
  const winSet = new Set(s.winning_line || []);
  cells.forEach((cell, i) => {
    const val = s.board[i];
    cell.className = "ttt-cell";
    cell.textContent = val === "X" ? "✕" : val === "O" ? "O" : "";
    if (val === "X") cell.classList.add("x");
    if (val === "O") cell.classList.add("o");
    if (val !== null) cell.classList.add("taken");
    if (winSet.has(i)) cell.classList.add("win");
    cell.disabled = s.over || val !== null;
  });

  // Status message
  els.status.className = "status";
  if (s.winner === "X") {
    els.status.textContent = "🎉 You win!";
    els.status.classList.add("won");
  } else if (s.winner === "O") {
    els.status.textContent = "💻 Computer wins!";
    els.status.classList.add("lost");
  } else if (s.winner === "draw") {
    els.status.textContent = "🤝 It's a draw!";
  } else {
    els.status.innerHTML = "&nbsp;";
  }
}

els.newGame.addEventListener("click", startNew);

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
