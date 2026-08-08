"use strict";

let state = null;
let levelsBuilt = false;

const els = {
  levelToggle: document.getElementById("level-toggle"),
  result:      document.getElementById("result"),
  enemyGrid:   document.getElementById("enemy-grid"),
  playerGrid:  document.getElementById("player-grid"),
  enemyLeft:   document.getElementById("enemy-left"),
  yourLeft:    document.getElementById("your-left"),
  enemyFleetList:  document.getElementById("enemy-fleet-list"),
  playerFleetList: document.getElementById("player-fleet-list"),
  randomize:   document.getElementById("randomize"),
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
  state = await (await fetch("/battleship/state")).json();
  render(state);
}

async function fireAt(row, col) {
  state = await postJSON("/battleship/fire", { row, col });
  render(state);
}

async function randomizeFleet() {
  state = await postJSON("/battleship/randomize", {});
  render(state);
}

async function newGame(level) {
  state = await postJSON("/battleship/new", { level: level || state?.level });
  render(state);
}

async function setName(name) {
  state = await postJSON("/name", { name });
  render(state);
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

function buildGrid(container, cells, size, { interactive }) {
  container.style.gridTemplateColumns = `repeat(${size}, 28px)`;
  container.innerHTML = "";
  cells.forEach((row, r) => {
    row.forEach((cell, c) => {
      const div = document.createElement("div");
      let className = "cell";
      let content = "";

      if (cell.shot === "miss") {
        className += " miss";
      } else if (cell.sunk) {
        className += " sunk";
        content = "💀";
      } else if (cell.shot === "hit") {
        className += " hit";
        content = "🔥";
      } else if (cell.damaged) {
        className += " damaged";
      } else if (cell.ship) {
        className += " ship";
      } else if (interactive && !state.over) {
        className += " clickable";
      }

      div.className = className;
      div.textContent = content;
      if (interactive && !cell.shot && !state.over) {
        div.addEventListener("click", () => fireAt(r, c));
      }
      container.appendChild(div);
    });
  });
}

function buildFleetList(container, roster) {
  container.innerHTML = "";
  roster.forEach(ship => {
    const li = document.createElement("li");
    li.className = ship.status;
    const dot = document.createElement("span");
    dot.className = "dot";
    li.appendChild(dot);
    li.appendChild(document.createTextNode(ship.name));
    const len = document.createElement("span");
    len.className = "len";
    len.textContent = ship.length;
    li.appendChild(len);
    container.appendChild(li);
  });
}

function render(s) {
  buildLevelToggle(s.levels);
  els.levelToggle.querySelectorAll(".level-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.level === s.level);
  });

  els.scorePlayer.textContent = s.score.player;
  els.scoreComp.textContent   = s.score.hangman;
  els.enemyLeft.textContent   = s.ships_remaining.computer;
  els.yourLeft.textContent    = s.ships_remaining.player;

  buildGrid(els.enemyGrid, s.enemy_waters, s.board_size, { interactive: true });
  buildGrid(els.playerGrid, s.your_fleet, s.board_size, { interactive: false });

  buildFleetList(els.enemyFleetList, s.fleets.computer);
  buildFleetList(els.playerFleetList, s.fleets.player);

  els.randomize.disabled = s.first_shot_fired || s.over;

  if (s.over) {
    els.result.textContent = s.won
      ? "🎉 You sank the enemy fleet!"
      : "💥 Your fleet was destroyed.";
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
els.randomize.addEventListener("click", randomizeFleet);

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

loadState();
