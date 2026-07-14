"use strict";

let state = null;
let tickHandle = null;
let levelsBuilt = false;

const els = {
  levelToggle: document.getElementById("level-toggle"),
  board:       document.getElementById("board"),
  nextPiece:   document.getElementById("next-piece"),
  lines:       document.getElementById("lines"),
  levelNum:    document.getElementById("level-num"),
  best:        document.getElementById("best"),
  result:      document.getElementById("result"),
  newGame:     document.getElementById("new-game"),
  scorePlayer: document.getElementById("score-player"),
  scoreComp:   document.getElementById("score-hangman"),
  nameBtn:     document.getElementById("name-btn"),
  nameInput:   document.getElementById("name-input"),
  nameList:    document.getElementById("name-list"),
  btnLeft:     document.getElementById("btn-left"),
  btnRight:    document.getElementById("btn-right"),
  btnRotate:   document.getElementById("btn-rotate"),
  btnSoft:     document.getElementById("btn-soft"),
  btnHard:     document.getElementById("btn-hard"),
};

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function postJSON(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return resp.json();
}

async function loadState() {
  state = await (await fetch("/tetris/state")).json();
  render(state);
  armTicker();
}

async function sendMove(action) {
  if (!state || state.over) return;
  state = await postJSON("/tetris/move", { action });
  render(state);
}

async function tick() {
  state = await postJSON("/tetris/tick", {});
  render(state);
}

async function newGame(level) {
  state = await postJSON("/tetris/new", { level: level || state?.level });
  render(state);
  armTicker();
}

async function setName(name) {
  state = await postJSON("/name", { name });
  render(state);
}

function armTicker() {
  if (tickHandle) clearInterval(tickHandle);
  if (state && !state.over) {
    tickHandle = setInterval(tick, 150);
  }
}

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------

function buildLevelToggle(levels) {
  if (levelsBuilt) return;
  levelsBuilt = true;
  els.levelToggle.innerHTML = "";
  levels.forEach(level => {
    const btn = document.createElement("button");
    btn.className = "level-btn";
    btn.textContent = level;
    btn.dataset.level = level;
    btn.addEventListener("click", () => newGame(level));
    els.levelToggle.appendChild(btn);
  });
}

function buildGrid(container, rows, cols) {
  container.innerHTML = "";
  for (let i = 0; i < rows * cols; i++) {
    const cell = document.createElement("div");
    cell.className = "cell";
    container.appendChild(cell);
  }
  return container.children;
}

function render(s) {
  buildLevelToggle(s.levels);
  els.levelToggle.querySelectorAll(".level-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.level === s.level);
  });

  els.lines.textContent    = s.lines;
  els.levelNum.textContent = s.level_num;
  els.best.textContent     = s.score.best || 0;
  els.scorePlayer.textContent = s.score.player;
  els.scoreComp.textContent   = s.score.hangman;

  // Board
  const rows = s.board.length, cols = s.board[0].length;
  const cells = buildGrid(els.board, rows, cols);
  s.board.forEach((row, r) => {
    row.forEach((color, c) => {
      cells[r * cols + c].style.background = color || "#0b1220";
    });
  });

  // Next piece preview (4x4)
  const nextCells = buildGrid(els.nextPiece, 4, 4);
  s.next_cells.forEach(([r, c]) => {
    nextCells[r * 4 + c].style.background = s.next_color;
  });

  // Result banner
  if (s.over) {
    els.result.textContent = `Game over — reached level ${s.level_num}, ${s.lines} lines cleared.`;
    els.result.className = "result loss";
    els.result.hidden = false;
    if (tickHandle) { clearInterval(tickHandle); tickHandle = null; }
  } else {
    els.result.hidden = true;
  }

  // Name button
  els.nameBtn.textContent = s.name || "Guest";
  renderNameList(s.names);
}

// ---------------------------------------------------------------------------
// Name editor (standard boilerplate)
// ---------------------------------------------------------------------------

function commitName() {
  const val = els.nameInput.value.trim();
  hideNameEditor();
  setName(val);
}

function addNameOption(name) {
  const li = document.createElement("li");
  li.textContent = name;
  li.addEventListener("mousedown", e => { e.preventDefault(); els.nameInput.value = name; commitName(); });
  els.nameList.appendChild(li);
}

function renderNameList(names) {
  els.nameList.innerHTML = "";
  addNameOption("Guest");
  (names || []).forEach(addNameOption);
}

function showNameEditor() {
  els.nameBtn.hidden   = true;
  els.nameInput.hidden = false;
  els.nameList.hidden  = false;
  els.nameInput.value  = state?.name || "";
  els.nameInput.focus();
}

function hideNameEditor() {
  els.nameBtn.hidden   = false;
  els.nameInput.hidden = true;
  els.nameList.hidden  = true;
}

els.nameBtn.addEventListener("click",  showNameEditor);
els.nameInput.addEventListener("blur", commitName);
els.nameInput.addEventListener("keydown", e => {
  if (e.key === "Enter")  { e.preventDefault(); commitName(); }
  if (e.key === "Escape") { hideNameEditor(); }
});

// ---------------------------------------------------------------------------
// Controls
// ---------------------------------------------------------------------------

els.newGame.addEventListener("click", () => newGame(state?.level));
els.btnLeft.addEventListener("click",   () => sendMove("left"));
els.btnRight.addEventListener("click",  () => sendMove("right"));
els.btnRotate.addEventListener("click", () => sendMove("rotate"));
els.btnSoft.addEventListener("click",   () => sendMove("soft_drop"));
els.btnHard.addEventListener("click",   () => sendMove("hard_drop"));

document.addEventListener("keydown", e => {
  const keyMap = {
    ArrowLeft: "left", ArrowRight: "right", ArrowUp: "rotate",
    ArrowDown: "soft_drop", " ": "hard_drop", Spacebar: "hard_drop",
  };
  const action = keyMap[e.key];
  if (!action) return;
  if (els.nameInput.hidden === false) return;  // don't hijack typing in the name box
  e.preventDefault();
  sendMove(action);
});

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

loadState();
