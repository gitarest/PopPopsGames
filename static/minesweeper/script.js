"use strict";

let state = null;
let levelsBuilt = false;
let flagMode = false;

const els = {
  levelToggle: document.getElementById("level-toggle"),
  minesLeft:   document.getElementById("mines-left"),
  flagMode:    document.getElementById("flag-mode"),
  grid:        document.getElementById("grid"),
  result:      document.getElementById("result"),
  newGame:     document.getElementById("new-game"),
  scorePlayer: document.getElementById("score-player"),
  scoreComp:   document.getElementById("score-hangman"),
  nameBtn:     document.getElementById("name-btn"),
  nameInput:   document.getElementById("name-input"),
  nameList:    document.getElementById("name-list"),
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
  state = await (await fetch("/minesweeper/state")).json();
  render(state);
}

async function revealCell(row, col) {
  state = await postJSON("/minesweeper/reveal", { row, col });
  render(state);
}

async function flagCell(row, col) {
  state = await postJSON("/minesweeper/flag", { row, col });
  render(state);
}

async function newGame(level) {
  state = await postJSON("/minesweeper/new", { level: level || state?.level });
  render(state);
}

async function setName(name) {
  state = await postJSON("/name", { name });
  render(state);
}

// ---------------------------------------------------------------------------
// Interaction
// ---------------------------------------------------------------------------

function onCellClick(row, col) {
  if (!state || state.over) return;
  if (flagMode) {
    flagCell(row, col);
  } else {
    revealCell(row, col);
  }
}

function onCellRightClick(e, row, col) {
  e.preventDefault();
  if (!state || state.over) return;
  flagCell(row, col);
}

els.flagMode.addEventListener("click", () => {
  flagMode = !flagMode;
  els.flagMode.setAttribute("aria-pressed", String(flagMode));
  els.flagMode.textContent = flagMode ? "🚩 Flag Mode: On" : "🚩 Flag Mode: Off";
});

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

function render(s) {
  buildLevelToggle(s.levels);
  els.levelToggle.querySelectorAll(".level-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.level === s.level);
  });

  els.minesLeft.textContent = s.mines_total - s.flags_used;
  els.scorePlayer.textContent = s.score.player;
  els.scoreComp.textContent   = s.score.hangman;

  els.grid.style.gridTemplateColumns = `repeat(${s.cols}, 32px)`;
  els.grid.innerHTML = "";
  s.cells.forEach((row, r) => {
    row.forEach((cell, c) => {
      const div = document.createElement("div");
      let className = "cell";
      let content = "";

      if (cell.flagged) {
        className += " hidden flagged" + (cell.wrong_flag ? " wrong-flag" : "");
        content = "🚩";
      } else if (cell.revealed) {
        if (cell.mine) {
          const isHit = s.hit && s.hit[0] === r && s.hit[1] === c;
          className += " revealed mine" + (isHit ? " hit" : "");
          content = "💣";
        } else {
          className += " revealed" + (cell.count > 0 ? ` count-${cell.count}` : "");
          content = cell.count > 0 ? String(cell.count) : "";
        }
      } else {
        className += " hidden";
      }

      div.className = className;
      div.textContent = content;
      if (!cell.revealed) {
        div.addEventListener("click", () => onCellClick(r, c));
        div.addEventListener("contextmenu", e => onCellRightClick(e, r, c));
      }
      els.grid.appendChild(div);
    });
  });

  if (s.over) {
    els.result.textContent = s.won
      ? "🎉 You cleared the board!"
      : "💥 Boom! You hit a mine.";
    els.result.className = "result " + (s.won ? "win" : "loss");
    els.result.hidden = false;
  } else {
    els.result.hidden = true;
  }

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

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

loadState();
