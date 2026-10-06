"use strict";

let state = null;
let levelsBuilt = false;
let busy = false;
let tileEls = [];      // tile id -> element, rebuilt when the board size changes
let builtSize = 0;
let builtImage = null; // image URL the tiles were last painted with
let croppedImage = null;
let solveRun = 0;      // bumped to cancel a Give Up replay in progress

const NUMBERS_KEY = "slidepuzzle.numbers";

const els = {
  levelToggle: document.getElementById("level-toggle"),
  peek:        document.getElementById("peek"),
  moves:       document.getElementById("moves"),
  numbers:     document.getElementById("numbers"),
  board:       document.getElementById("board"),
  result:      document.getElementById("result"),
  giveUp:      document.getElementById("give-up"),
  newGame:     document.getElementById("new-game"),
  scorePlayer: document.getElementById("score-player"),
  scoreComp:   document.getElementById("score-hangman"),
  nameBtn:     document.getElementById("name-btn"),
  nameInput:   document.getElementById("name-input"),
  nameList:    document.getElementById("name-list"),
};

const timer = createGameTimer(document.getElementById("timer"));

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
  state = await (await fetch("/slidepuzzle/state")).json();
  if (state.moves > 0 && !state.over) timer.start();
  render(state);
}

async function moveTile(index) {
  if (busy) return;
  busy = true;
  timer.start();
  try {
    state = await postJSON("/slidepuzzle/move", { index });
    render(state);
  } finally {
    busy = false;
  }
}

async function newGame(level) {
  solveRun++;
  timer.reset();
  state = await postJSON("/slidepuzzle/new", { level: level || state?.level });
  render(state);
}

async function giveUp() {
  if (!state || state.over) return;
  if (!confirm("Give up and watch Pop Pop solve it? The computer gets a point.")) return;
  const before = state.tiles.slice();
  timer.stop();
  state = await postJSON("/slidepuzzle/give_up", {});
  if (state.solution && state.solution.length) {
    await playSolution(before, state.solution, state.size);
  }
  render(state);
}

// Replay the server's solution one tile at a time. Long solutions (Hard can
// be 200+ moves) speed up so the whole thing takes about 20 seconds at most.
async function playSolution(tiles, clicks, size) {
  const run = ++solveRun;
  const delay = Math.max(70, Math.min(350, 20000 / clicks.length));
  els.board.style.setProperty("--slide", `${Math.min(150, delay - 20)}ms`);
  els.giveUp.disabled = true;
  els.result.className = "result solving";
  els.result.hidden = false;
  const blank = size * size - 1;
  for (let step = 0; step < clicks.length; step++) {
    await new Promise(r => setTimeout(r, delay));
    if (run !== solveRun) break;  // New Game was pressed
    const b = tiles.indexOf(blank);
    tiles[b] = tiles[clicks[step]];
    tiles[clicks[step]] = blank;
    placeTiles(tiles, size, false);
    els.result.textContent = `🤖 Solving… ${step + 1} / ${clicks.length} moves`;
  }
  if (run === solveRun) await new Promise(r => setTimeout(r, delay));
  els.board.style.removeProperty("--slide");
}

async function setName(name) {
  state = await postJSON("/name", { name });
  // The server swaps in the player's own picture if they haven't moved yet.
  state = await (await fetch("/slidepuzzle/state")).json();
  render(state);
}

// ---------------------------------------------------------------------------
// Picture: crop to a centred square so any photo shape works
// ---------------------------------------------------------------------------

function loadCroppedImage(url) {
  return new Promise(resolve => {
    const img = new Image();
    img.onload = () => {
      try {
        const side = Math.min(img.naturalWidth, img.naturalHeight) || 600;
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = 600;
        canvas.getContext("2d").drawImage(
          img,
          (img.naturalWidth - side) / 2, (img.naturalHeight - side) / 2, side, side,
          0, 0, 600, 600,
        );
        resolve(canvas.toDataURL("image/jpeg", 0.9));
      } catch (e) {
        resolve(url);  // canvas refused (e.g. odd SVG) — use the original
      }
    };
    img.onerror = () => resolve(null);
    img.src = url;
  });
}

async function ensureImage(url) {
  if (url === builtImage) return;
  builtImage = url;
  croppedImage = url ? await loadCroppedImage(url) : null;
  if (builtImage !== url) return;  // a newer image arrived while loading
  els.peek.src = croppedImage || "";
  els.peek.hidden = !croppedImage;
  tileEls.forEach(el => {
    el.firstChild.style.backgroundImage = croppedImage ? `url("${croppedImage}")` : "";
  });
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

function buildTiles(size) {
  els.board.innerHTML = "";
  els.board.style.setProperty("--size", size);
  tileEls = [];
  for (let id = 0; id < size * size; id++) {
    const tile = document.createElement("div");
    tile.className = "tile";
    const face = document.createElement("div");
    face.className = "tile-face";
    const row = Math.floor(id / size), col = id % size;
    face.style.backgroundSize = `${size * 100}% ${size * 100}%`;
    face.style.backgroundPosition =
      `${size > 1 ? (col / (size - 1)) * 100 : 0}% ${size > 1 ? (row / (size - 1)) * 100 : 0}%`;
    if (croppedImage) face.style.backgroundImage = `url("${croppedImage}")`;
    const num = document.createElement("span");
    num.className = "tile-num";
    num.textContent = id + 1;
    face.appendChild(num);
    tile.appendChild(face);
    tile.addEventListener("click", () => {
      const pos = state.tiles.indexOf(id);
      if (!state.over && pos >= 0) moveTile(pos);
    });
    els.board.appendChild(tile);
    tileEls.push(tile);
  }
  builtSize = size;
}

function placeTiles(tiles, size, done) {
  const blank = size * size - 1;
  tiles.forEach((id, pos) => {
    const el = tileEls[id];
    const row = Math.floor(pos / size), col = pos % size;
    el.style.left = `calc(4px + (100% - 8px) * ${col} / ${size})`;
    el.style.top  = `calc(4px + (100% - 8px) * ${row} / ${size})`;
    // The blank's piece only appears once the picture is complete.
    el.style.visibility = (id === blank && !done) ? "hidden" : "visible";
  });
  els.board.classList.toggle("done", done);
}

function render(s) {
  buildLevelToggle(s.levels);
  els.levelToggle.querySelectorAll(".level-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.level === s.level);
  });

  if (s.size !== builtSize) buildTiles(s.size);
  ensureImage(s.image);

  placeTiles(s.tiles, s.size, s.over);
  els.board.classList.toggle("won", s.won);

  els.moves.textContent = s.moves;
  els.scorePlayer.textContent = s.score.player;
  els.scoreComp.textContent   = s.score.hangman;
  els.giveUp.disabled = s.over;

  if (s.over) {
    timer.stop();
    const secs = timer.elapsedSeconds();
    els.result.textContent = s.won
      ? `🎉 You did it in ${s.moves} moves${secs ? " and " + timer.formatTime(secs) : ""}!`
      : s.solution
        ? `🤖 Solved in ${s.solution.length} moves. Try another one!`
        : "Here's the picture. Try another one!";
    els.result.className = "result " + (s.won ? "win" : "loss");
    els.result.hidden = false;
  } else {
    els.result.hidden = true;
  }

  els.nameBtn.textContent = s.name || "Guest";
  renderNameList(s.names);
}

// ---------------------------------------------------------------------------
// Numbers toggle (remembered per device)
// ---------------------------------------------------------------------------

function setNumbers(on) {
  els.board.classList.toggle("show-numbers", on);
  els.numbers.setAttribute("aria-pressed", String(on));
  try { localStorage.setItem(NUMBERS_KEY, on ? "1" : "0"); } catch (e) { /* ignore */ }
}

let numbersOn = false;
try { numbersOn = localStorage.getItem(NUMBERS_KEY) === "1"; } catch (e) { /* ignore */ }
setNumbers(numbersOn);
els.numbers.addEventListener("click", () => {
  numbersOn = !numbersOn;
  setNumbers(numbersOn);
});

// ---------------------------------------------------------------------------
// Keyboard: arrows slide the neighbouring tile into the gap
// ---------------------------------------------------------------------------

document.addEventListener("keydown", e => {
  if (!state || state.over || e.target === els.nameInput) return;
  const n = state.size;
  const b = state.tiles.indexOf(n * n - 1);
  const r = Math.floor(b / n), c = b % n;
  const target = {
    ArrowLeft:  c < n - 1 ? b + 1 : -1,
    ArrowRight: c > 0     ? b - 1 : -1,
    ArrowUp:    r < n - 1 ? b + n : -1,
    ArrowDown:  r > 0     ? b - n : -1,
  }[e.key];
  if (target === undefined) return;
  e.preventDefault();
  if (target >= 0) moveTile(target);
});

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
els.giveUp.addEventListener("click", giveUp);

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

loadState();
