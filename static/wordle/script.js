"use strict";

const MAX_GUESSES = 6;
const WORD_LENGTH = 5;

const els = {
  board:       document.getElementById("board"),
  status:      document.getElementById("status"),
  scorePlayer: document.getElementById("score-player"),
  scoreHangman:document.getElementById("score-hangman"),
  btnNew:      document.getElementById("btn-new"),
  nameBtn:     document.getElementById("name-btn"),
  nameInput:   document.getElementById("name-input"),
  nameList:    document.getElementById("name-list"),
  keyboard:    document.getElementById("keyboard"),
};

let state = null;
let currentInput = [];   // letters typed into the current row

// ---- Build board and keyboard on page load ----

function buildBoard() {
  els.board.innerHTML = "";
  for (let r = 0; r < MAX_GUESSES; r++) {
    const row = document.createElement("div");
    row.className = "board-row";
    row.id = "row-" + r;
    for (let c = 0; c < WORD_LENGTH; c++) {
      const tile = document.createElement("div");
      tile.className = "tile";
      tile.id = `tile-${r}-${c}`;
      row.appendChild(tile);
    }
    els.board.appendChild(row);
  }
}

function buildKeyboard() {
  // Create letter buttons for rows that have data-row
  document.querySelectorAll(".kb-row[data-row]").forEach(row => {
    // Pull out any pre-placed special keys (Enter, ⌫) to re-append after letters
    const special = [...row.querySelectorAll("button")];
    special.forEach(b => row.removeChild(b));

    row.dataset.row.split("").forEach(letter => {
      const btn = document.createElement("button");
      btn.className = "key";
      btn.dataset.key = letter;
      btn.textContent = letter;
      row.appendChild(btn);
    });

    // Re-append special keys at the end so they sit on the right
    special.forEach(b => row.appendChild(b));
  });
  // Single delegated listener covers all keys (static and dynamic)
  els.keyboard.addEventListener("click", e => {
    const btn = e.target.closest("[data-key]");
    if (btn) handleKey(btn.dataset.key);
  });
}

// ---- Render ----

function render(s) {
  state = s;

  els.scorePlayer.textContent  = s.score ? (s.score.player  || 0) : 0;
  els.scoreHangman.textContent = s.score ? (s.score.hangman || 0) : 0;
  els.nameBtn.textContent = s.name || "Guest";

  // Fill in submitted guesses
  s.guesses.forEach((g, r) => {
    g.result.forEach((res, c) => {
      const tile = document.getElementById(`tile-${r}-${c}`);
      tile.textContent = g.word[c];
      tile.className = "tile " + res;
    });
  });

  // Clear and re-apply current input row
  const curRow = s.attempts;
  if (curRow < MAX_GUESSES) {
    for (let c = 0; c < WORD_LENGTH; c++) {
      const tile = document.getElementById(`tile-${curRow}-${c}`);
      if (c < currentInput.length) {
        tile.textContent = currentInput[c];
        tile.className = "tile filled";
      } else {
        tile.textContent = "";
        tile.className = "tile";
      }
    }
  }

  // Clear future rows
  for (let r = curRow + 1; r < MAX_GUESSES; r++) {
    for (let c = 0; c < WORD_LENGTH; c++) {
      const tile = document.getElementById(`tile-${r}-${c}`);
      tile.textContent = "";
      tile.className = "tile";
    }
  }

  // Update keyboard key colors
  const letterStates = s.letter_states || {};
  document.querySelectorAll(".key[data-key]").forEach(btn => {
    const k = btn.dataset.key;
    if (k && k.length === 1) {
      btn.className = "key" + (letterStates[k] ? " " + letterStates[k] : "");
    }
  });

  // Status
  const statusEl = els.status;
  statusEl.className = "status";
  if (s.phase === "won") {
    statusEl.textContent = `You got it in ${s.attempts} ${s.attempts === 1 ? "guess" : "guesses"}! 🎉`;
    statusEl.classList.add("win");
    currentInput = [];
  } else if (s.phase === "lost") {
    statusEl.textContent = `The word was ${s.word}. Better luck next time!`;
    statusEl.classList.add("loss");
    currentInput = [];
  } else if (s.attempts === 0) {
    statusEl.textContent = "Guess the 5-letter word!";
  } else {
    statusEl.textContent = `${MAX_GUESSES - s.attempts} guess${MAX_GUESSES - s.attempts === 1 ? "" : "es"} remaining`;
  }
}

// ---- Input handling ----

function isGameOver() {
  return state && state.over;
}

function handleKey(key) {
  if (isGameOver()) return;
  if (key === "Backspace") {
    if (currentInput.length > 0) {
      currentInput.pop();
      renderCurrentRow();
    }
  } else if (key === "Enter") {
    if (currentInput.length === WORD_LENGTH) {
      submitGuess();
    } else {
      shakeCurrentRow();
    }
  } else if (/^[A-Za-z]$/.test(key)) {
    if (currentInput.length < WORD_LENGTH) {
      currentInput.push(key.toUpperCase());
      renderCurrentRow();
    }
  }
}

function renderCurrentRow() {
  if (!state) return;
  const curRow = state.attempts;
  if (curRow >= MAX_GUESSES) return;
  for (let c = 0; c < WORD_LENGTH; c++) {
    const tile = document.getElementById(`tile-${curRow}-${c}`);
    if (c < currentInput.length) {
      tile.textContent = currentInput[c];
      tile.className = "tile filled";
    } else {
      tile.textContent = "";
      tile.className = "tile";
    }
  }
}

function shakeCurrentRow() {
  if (!state) return;
  const row = document.getElementById("row-" + state.attempts);
  if (!row) return;
  row.style.animation = "none";
  row.offsetHeight;  // reflow
  row.style.animation = "shake 0.3s ease";
  setTimeout(() => { row.style.animation = ""; }, 350);
}

async function submitGuess() {
  const word = currentInput.join("");
  const saved = [...currentInput];
  currentInput = [];
  const s = await postJSON("/wordle/guess", { word });
  if (s.invalid_guess) {
    currentInput = saved;
    shakeCurrentRow();
    renderCurrentRow();
    els.status.textContent = "Not in word list";
    els.status.className = "status";
    return;
  }
  render(s);
}

// ---- Network ----

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return res.json();
}

// ---- Physical keyboard ----

document.addEventListener("keydown", e => {
  if (e.ctrlKey || e.altKey || e.metaKey) return;
  if (e.key === "Backspace") { e.preventDefault(); handleKey("Backspace"); }
  else if (e.key === "Enter") { e.preventDefault(); handleKey("Enter"); }
  else if (/^[A-Za-z]$/.test(e.key)) handleKey(e.key);
});

// ---- New game ----

els.btnNew.addEventListener("click", async () => {
  currentInput = [];
  const s = await postJSON("/wordle/new", {});
  render(s);
});

// ---- Name editor ----

async function setName(name) {
  await postJSON("/name", { name: name || "" });
  render(await (await fetch("/wordle/state")).json());
}

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
  const trimmed = filter.trim();
  const exactMatch = (state && state.names || []).some(
    n => n.toLowerCase() === trimmed.toLowerCase()
  );
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

// ---- Boot ----

buildBoard();
buildKeyboard();

async function loadState() {
  const s = await (await fetch("/wordle/state")).json();
  // Restore currentInput from last incomplete row if mid-game
  currentInput = [];
  render(s);
}

loadState();
