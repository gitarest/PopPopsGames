"use strict";

let state = null;
let clearing = false;   // true while a wrong-arrangement is being shown, before /clear resets it
let levelsBuilt = false;

const els = {
  levelToggle: document.getElementById("level-toggle"),
  answer:      document.getElementById("answer"),
  pool:        document.getElementById("pool"),
  wrong:       document.getElementById("wrong"),
  maxWrong:    document.getElementById("max-wrong"),
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
  state = await (await fetch("/wordscramble/state")).json();
  render(state);
}

async function placeTile(index) {
  if (clearing) return;
  state = await postJSON("/wordscramble/place", { index });
  render(state);
  if (state.wrong_flag) {
    clearing = true;
    setTimeout(async () => {
      state = await postJSON("/wordscramble/clear", {});
      clearing = false;
      render(state);
    }, 900);
  }
}

async function removeTile(index) {
  if (clearing) return;
  state = await postJSON("/wordscramble/remove", { index });
  render(state);
}

async function newGame(level) {
  clearing = false;
  state = await postJSON("/wordscramble/new", { level: level || state?.level });
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

function render(s) {
  buildLevelToggle(s.levels);
  els.levelToggle.querySelectorAll(".level-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.level === s.level);
  });

  els.wrong.textContent    = s.wrong;
  els.maxWrong.textContent = s.max_wrong;
  els.scorePlayer.textContent = s.score.player;
  els.scoreComp.textContent   = s.score.hangman;

  // Answer slots — one per letter, filled left-to-right in placement order.
  els.answer.innerHTML = "";
  s.letters.forEach((_, pos) => {
    const slot = document.createElement("div");
    const origIndex = s.answer_order[pos];
    if (origIndex !== undefined) {
      slot.className = "slot filled";
      slot.textContent = s.letters[origIndex];
      if (s.wrong_flag) slot.classList.add("wrong");
      if (s.over && s.won) slot.classList.add("won");
      if (!s.over && !s.wrong_flag) {
        slot.addEventListener("click", () => removeTile(origIndex));
      }
    } else {
      slot.className = "slot";
    }
    els.answer.appendChild(slot);
  });

  // Pool tiles — only letters not yet placed.
  els.pool.innerHTML = "";
  s.letters.forEach((letter, i) => {
    if (s.tile_state[i] !== "pool") return;
    const btn = document.createElement("button");
    btn.className = "tile";
    btn.textContent = letter;
    if (!s.over && !s.wrong_flag) {
      btn.addEventListener("click", () => placeTile(i));
    }
    els.pool.appendChild(btn);
  });

  // Result banner
  if (s.over) {
    els.result.textContent = s.won
      ? `🎉 You unscrambled ${s.word}!`
      : `The word was ${s.word}. Better luck next time!`;
    els.result.className = "result " + (s.won ? "win" : "loss");
    els.result.hidden = false;
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

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

loadState();
