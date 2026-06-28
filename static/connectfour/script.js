"use strict";

const ROWS = 6;
const COLS = 7;

let state     = null;
let hoverCol  = null;
let dropping  = false; // true while drop animation is playing
let dropSpeed = 550;   // ms per cell — kept in sync with the speed slider

// Build the board DOM once on load.
const boardEl    = document.getElementById("board");
const dropBtnsEl = document.getElementById("drop-btns");

for (let c = 0; c < COLS; c++) {
  const btn = document.createElement("button");
  btn.className   = "drop-btn";
  btn.dataset.col = c;
  // No text — styled as a small circular checker
  dropBtnsEl.appendChild(btn);
}

for (let r = 0; r < ROWS; r++) {
  for (let c = 0; c < COLS; c++) {
    const cell       = document.createElement("div");
    cell.className   = "cell";
    cell.dataset.row = r;
    cell.dataset.col = c;
    boardEl.appendChild(cell);
  }
}

const dropBtns = [...dropBtnsEl.querySelectorAll(".drop-btn")];
const cells    = [...boardEl.querySelectorAll(".cell")];

const els = {
  status:       document.getElementById("status"),
  scorePlayer:  document.getElementById("score-player"),
  scoreHangman: document.getElementById("score-hangman"),
  nameBtn:      document.getElementById("name-btn"),
  nameInput:    document.getElementById("name-input"),
  nameList:     document.getElementById("name-list"),
  newGame:      document.getElementById("new-game"),
  levelBtns:    document.getElementById("level-btns"),
};

// ---- Helpers ----

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function getCell(r, c) {
  return boardEl.querySelector(`.cell[data-row="${r}"][data-col="${c}"]`);
}

// ---- API helpers ----

async function postJSON(url, body) {
  const res = await fetch(url, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(body || {}),
  });
  return res.json();
}

async function loadState() {
  render(await (await fetch("/connectfour/state")).json());
}

async function startNew(level) {
  if (dropping) return;
  render(await postJSON("/connectfour/new", level ? { level } : {}));
}

async function setName(name) {
  await postJSON("/name", { name: name || "" });
  render(await (await fetch("/connectfour/state")).json());
}

// ---- Drop animation ----

// Animate a piece falling from row 0 down to finalRow in the given column.
// pieceClass is "player" or "computer".
async function animateDrop(col, finalRow, pieceClass) {
  const STEP_MS = dropSpeed;
  let prevCell = null;
  for (let r = 0; r <= finalRow; r++) {
    const cell = getCell(r, col);
    if (!cell) continue;
    if (prevCell) prevCell.className = "cell"; // clear previous cell
    cell.className = `cell ${pieceClass}`;      // show piece at current row
    prevCell = cell;
    await sleep(STEP_MS);
  }
  // Leave final cell showing the piece; render() will set it permanently
}

async function dropCol(col) {
  if (!state || state.over || dropping) return;
  dropping = true;
  hoverCol = null;
  dropBtns.forEach(btn => { btn.disabled = true; });

  // Capture board state before the move so we can compute animations
  const oldBoard = state.board.map(row => [...row]);

  // Find where player's piece will land (lowest empty row in col)
  let playerRow = -1;
  for (let r = ROWS - 1; r >= 0; r--) {
    if (!oldBoard[r][col]) { playerRow = r; break; }
  }

  // POST to server — both player and computer moves happen server-side
  const newState = await postJSON("/connectfour/drop", { col });

  // Animate the player's piece falling
  await animateDrop(col, playerRow, "player");

  // Find where the computer played by diffing intermediate vs final board.
  // Intermediate = oldBoard + player piece at (playerRow, col).
  let compCol = -1, compRow = -1;
  for (let c = 0; c < COLS; c++) {
    for (let r = 0; r < ROWS; r++) {
      const intermediate = (c === col && r === playerRow) ? "P" : oldBoard[r][c];
      if (newState.board[r][c] === "C" && intermediate !== "C") {
        compCol = c;
        compRow = r;
      }
    }
  }

  // Animate the computer's piece falling (if it moved)
  if (compCol !== -1) {
    await animateDrop(compCol, compRow, "computer");
  }

  dropping = false;
  render(newState);
}

// ---- Hover preview ----

function updateHoverPreview() {
  cells.forEach(c => c.classList.remove("preview"));
  if (!state || state.over || hoverCol === null || dropping) return;
  for (let r = ROWS - 1; r >= 0; r--) {
    if (!state.board[r][hoverCol]) {
      const cell = getCell(r, hoverCol);
      if (cell && !cell.classList.contains("player") && !cell.classList.contains("computer")) {
        cell.classList.add("preview");
      }
      break;
    }
  }
}

// ---- Level buttons ----

function renderLevelBtns(levels, current) {
  if (els.levelBtns.childElementCount !== levels.length) {
    els.levelBtns.innerHTML = "";
    levels.forEach(lvl => {
      const btn = document.createElement("button");
      btn.className     = "level-btn";
      btn.textContent   = lvl.charAt(0).toUpperCase() + lvl.slice(1);
      btn.dataset.level = lvl;
      btn.addEventListener("click", () => startNew(lvl));
      els.levelBtns.appendChild(btn);
    });
  }
  [...els.levelBtns.querySelectorAll(".level-btn")].forEach(btn => {
    btn.classList.toggle("active", btn.dataset.level === current);
  });
}

// ---- Render ----

function render(s) {
  state = s;

  if (s.score) {
    els.scorePlayer.textContent  = s.score.player;
    els.scoreHangman.textContent = s.score.hangman;
  }
  els.nameBtn.textContent = s.name || "Guest";

  if (s.levels) renderLevelBtns(s.levels, s.level);

  const winSet = new Set((s.winning_cells || []).map(([r, c]) => `${r},${c}`));

  cells.forEach(cell => {
    const r     = +cell.dataset.row;
    const c     = +cell.dataset.col;
    const piece = s.board[r][c];
    const isWin = winSet.has(`${r},${c}`);
    cell.className = "cell";
    if (piece === "P") { cell.classList.add("player"); if (isWin) cell.classList.add("win"); }
    else if (piece === "C") { cell.classList.add("computer"); if (isWin) cell.classList.add("win"); }
  });

  dropBtns.forEach(btn => {
    const col    = +btn.dataset.col;
    btn.disabled = s.over || s.board[0][col] !== null;
  });

  const statusEl = els.status;
  statusEl.className = "status";
  if (s.over) {
    if      (s.winner === "P") { statusEl.textContent = "You win! 🎉";   statusEl.classList.add("win"); }
    else if (s.winner === "C") { statusEl.textContent = "Computer wins!"; statusEl.classList.add("loss"); }
    else                       { statusEl.textContent = "It's a draw!";   statusEl.classList.add("draw"); }
  } else {
    statusEl.textContent = "Your turn — drop a piece";
  }

  updateHoverPreview();
}

// ---- Drop button and board cell events ----

dropBtns.forEach((btn, col) => {
  btn.addEventListener("click",      () => dropCol(col));
  btn.addEventListener("mouseenter", () => { hoverCol = col; updateHoverPreview(); });
  btn.addEventListener("mouseleave", () => { hoverCol = null; updateHoverPreview(); });
});

cells.forEach(cell => {
  const col = +cell.dataset.col;
  cell.addEventListener("click",      () => dropCol(col));
  cell.addEventListener("mouseenter", () => { hoverCol = col; updateHoverPreview(); });
  cell.addEventListener("mouseleave", () => { hoverCol = null; updateHoverPreview(); });
});

// ---- New game ----

els.newGame.addEventListener("click", () => startNew(state && state.level));

// ---- Speed slider ----

const speedSlider = document.getElementById("speed-slider");

function applySpeed(val) {
  // Invert: slider left (0.1) = slow (1.0s), slider right (1.0) = fast (0.1s)
  const speed = +(1.1 - val).toFixed(2);
  dropSpeed = Math.round(speed * 1000);
  document.documentElement.style.setProperty("--flash-duration", `${(speed * 3).toFixed(2)}s`);
}

speedSlider.addEventListener("input", () => applySpeed(+speedSlider.value));
applySpeed(+speedSlider.value); // initialize from HTML default

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
  li.addEventListener("mousedown", e => { e.preventDefault(); commitName(value); });
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
  els.nameInput.value  = "";
  els.nameBtn.hidden   = true;
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
els.nameInput.addEventListener("input",  () => renderNameList(els.nameInput.value));

els.nameInput.addEventListener("keydown", e => {
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
