"use strict";

let state = null;
let levelsBuilt = false;
let selRow = null, selCol = null, selDir = "across";

const els = {
  levelToggle: document.getElementById("level-toggle"),
  hints:       document.getElementById("hints"),
  grid:        document.getElementById("grid"),
  cluesAcross: document.getElementById("clues-across"),
  cluesDown:   document.getElementById("clues-down"),
  result:      document.getElementById("result"),
  newGame:     document.getElementById("new-game"),
  btnReveal:   document.getElementById("btn-reveal"),
  scorePlayer: document.getElementById("score-player"),
  scoreComp:   document.getElementById("score-hangman"),
  nameBtn:     document.getElementById("name-btn"),
  nameInput:   document.getElementById("name-input"),
  nameList:    document.getElementById("name-list"),
  timer:       document.getElementById("timer"),
};

const timer = createGameTimer(els.timer);
timer.armAutoStart();

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
  state = await (await fetch("/crossword/state")).json();
  render(state);
}

async function setLetter(row, col, letter) {
  state = await postJSON("/crossword/letter", { row, col, letter });
  render(state);
}

async function clearLetter(row, col) {
  state = await postJSON("/crossword/clear", { row, col });
  render(state);
}

async function revealLetter(row, col) {
  state = await postJSON("/crossword/reveal", { row, col });
  render(state);
}

async function newGame(level) {
  selRow = selCol = null;
  timer.reset();
  state = await postJSON("/crossword/new", { level: level || state?.level });
  render(state);
  timer.armAutoStart();
}

async function setName(name) {
  state = await postJSON("/name", { name });
  render(state);
}

// ---------------------------------------------------------------------------
// Word-run helpers (derived client-side by scanning contiguous active cells —
// safe because every authored puzzle guarantees one word per contiguous run)
// ---------------------------------------------------------------------------

function isActive(cells, r, c) {
  return r >= 0 && r < cells.length && c >= 0 && c < cells[0].length && !cells[r][c].blocked;
}

function runLength(cells, row, col, dir) {
  if (!isActive(cells, row, col)) return 0;
  const [dr, dc] = dir === "across" ? [0, 1] : [1, 0];
  let r = row, c = col;
  while (isActive(cells, r - dr, c - dc)) { r -= dr; c -= dc; }
  let len = 0;
  while (isActive(cells, r, c)) { len++; r += dr; c += dc; }
  return len;
}

function wordCells(cells, row, col, dir) {
  const [dr, dc] = dir === "across" ? [0, 1] : [1, 0];
  let r = row, c = col;
  while (isActive(cells, r - dr, c - dc)) { r -= dr; c -= dc; }
  const out = [];
  while (isActive(cells, r, c)) { out.push([r, c]); r += dr; c += dc; }
  return out;
}

function numberToCell(cells) {
  const map = {};
  cells.forEach((row, r) => row.forEach((cell, c) => {
    if (cell.number != null) map[cell.number] = [r, c];
  }));
  return map;
}

// ---------------------------------------------------------------------------
// Selection
// ---------------------------------------------------------------------------

function selectCell(row, col, preferDir) {
  const cells = state.cells;
  if (!isActive(cells, row, col)) return;
  const acrossLen = runLength(cells, row, col, "across");
  const downLen   = runLength(cells, row, col, "down");

  if (row === selRow && col === selCol) {
    // Re-clicking the same cell toggles direction, if both exist.
    if (acrossLen >= 2 && downLen >= 2) {
      selDir = selDir === "across" ? "down" : "across";
    }
  } else {
    selRow = row; selCol = col;
    if (preferDir && (preferDir === "across" ? acrossLen : downLen) >= 2) {
      selDir = preferDir;
    } else if ((selDir === "across" ? acrossLen : downLen) < 2) {
      selDir = acrossLen >= 2 ? "across" : "down";
    }
  }
  renderGridOnly();
}

function selectClue(number, dir) {
  const map = numberToCell(state.cells);
  const pos = map[number];
  if (!pos) return;
  selRow = pos[0]; selCol = pos[1]; selDir = dir;
  renderGridOnly();
}

function advanceSelection() {
  const word = wordCells(state.cells, selRow, selCol, selDir);
  const idx = word.findIndex(([r, c]) => r === selRow && c === selCol);
  if (idx !== -1 && idx + 1 < word.length) {
    [selRow, selCol] = word[idx + 1];
  }
}

function retreatSelection() {
  const word = wordCells(state.cells, selRow, selCol, selDir);
  const idx = word.findIndex(([r, c]) => r === selRow && c === selCol);
  if (idx > 0) {
    [selRow, selCol] = word[idx - 1];
  }
}

function moveSelection(dRow, dCol) {
  if (selRow === null) return;
  const nr = selRow + dRow, nc = selCol + dCol;
  if (!isActive(state.cells, nr, nc)) return;
  selRow = nr; selCol = nc;
  selDir = dCol !== 0 ? "across" : "down";
  renderGridOnly();
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

function renderGridOnly() {
  const cells = state.cells;
  const inWord = selRow !== null ? new Set(wordCells(cells, selRow, selCol, selDir).map(([r, c]) => `${r},${c}`)) : new Set();
  els.grid.querySelectorAll(".cell").forEach(el => {
    const r = +el.dataset.row, c = +el.dataset.col;
    el.classList.toggle("selected", r === selRow && c === selCol);
    el.classList.toggle("in-word", inWord.has(`${r},${c}`) && !(r === selRow && c === selCol));
  });
}

function render(s) {
  buildLevelToggle(s.levels);
  els.levelToggle.querySelectorAll(".level-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.level === s.level);
  });

  els.hints.textContent = s.hints_used;
  els.scorePlayer.textContent = s.score.player;
  els.scoreComp.textContent   = s.score.hangman;

  // Grid
  els.grid.style.gridTemplateColumns = `repeat(${s.size}, 40px)`;
  els.grid.innerHTML = "";
  s.cells.forEach((row, r) => {
    row.forEach((cell, c) => {
      const div = document.createElement("div");
      div.className = "cell" + (cell.blocked ? " blocked" : "");
      div.dataset.row = r;
      div.dataset.col = c;
      if (!cell.blocked) {
        if (cell.number != null) {
          const num = document.createElement("span");
          num.className = "number";
          num.textContent = cell.number;
          div.appendChild(num);
        }
        const letter = document.createElement("span");
        letter.className = "letter";
        letter.textContent = cell.letter || "";
        div.appendChild(letter);
        div.addEventListener("click", () => selectCell(r, c));
      }
      els.grid.appendChild(div);
    });
  });

  if (selRow !== null && (state.cells[selRow][selCol].blocked)) {
    selRow = selCol = null;
  }
  renderGridOnly();

  // Clue lists
  renderClueList(els.cluesAcross, s.clues.across, "across");
  renderClueList(els.cluesDown,   s.clues.down,   "down");

  // Result banner
  if (s.over) {
    timer.stop();
    els.result.textContent = s.hints_used === 0
      ? "🎉 Puzzle solved — no hints needed!"
      : `Puzzle solved with ${s.hints_used} hint${s.hints_used === 1 ? "" : "s"} used.`;
    els.result.className = "result win";
    els.result.hidden = false;
  } else {
    els.result.hidden = true;
  }

  // Name button
  els.nameBtn.textContent = s.name || "Guest";
  renderNameList(s.names);
}

function renderClueList(el, clues, dir) {
  el.innerHTML = "";
  clues.forEach(clue => {
    const li = document.createElement("li");
    li.className = clue.solved ? "solved" : "";
    const num = document.createElement("span");
    num.className = "clue-number";
    num.textContent = clue.number + ".";
    li.appendChild(num);
    li.appendChild(document.createTextNode(clue.clue));
    li.addEventListener("click", () => selectClue(clue.number, dir));
    el.appendChild(li);
  });
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
els.btnReveal.addEventListener("click", () => {
  if (selRow !== null && !state.over) revealLetter(selRow, selCol);
});

document.addEventListener("keydown", e => {
  if (els.nameInput.hidden === false) return;  // don't hijack typing in the name box
  if (!state || state.over || selRow === null) return;

  if (/^[a-zA-Z]$/.test(e.key)) {
    e.preventDefault();
    setLetter(selRow, selCol, e.key.toUpperCase());
    advanceSelection();
    renderGridOnly();
  } else if (e.key === "Backspace") {
    e.preventDefault();
    const hadLetter = !!state.cells[selRow][selCol].letter;
    if (hadLetter) {
      clearLetter(selRow, selCol);
    } else {
      retreatSelection();
      clearLetter(selRow, selCol);
    }
  } else if (e.key === "ArrowLeft")  { e.preventDefault(); moveSelection(0, -1); }
  else if (e.key === "ArrowRight")   { e.preventDefault(); moveSelection(0, 1); }
  else if (e.key === "ArrowUp")      { e.preventDefault(); moveSelection(-1, 0); }
  else if (e.key === "ArrowDown")    { e.preventDefault(); moveSelection(1, 0); }
});

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

loadState();
