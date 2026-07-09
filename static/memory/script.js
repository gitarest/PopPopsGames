"use strict";

let state = null;
let clearing = false;  // prevent rapid flips while mismatch timeout is running

const els = {
  board:       document.getElementById("board"),
  moves:       document.getElementById("moves"),
  matched:     document.getElementById("matched"),
  par:         document.getElementById("par"),
  result:      document.getElementById("result"),
  newGame:     document.getElementById("new-game"),
  scorePlayer: document.getElementById("score-player"),
  scoreComp:   document.getElementById("score-hangman"),
  nameBtn:     document.getElementById("name-btn"),
  nameInput:   document.getElementById("name-input"),
  nameList:    document.getElementById("name-list"),
  themeFarm:   document.getElementById("theme-farm"),
  themeZoo:    document.getElementById("theme-zoo"),
  levelEasy:   document.getElementById("level-easy"),
  levelMedium: document.getElementById("level-medium"),
  levelHard:   document.getElementById("level-hard"),
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
  state = await (await fetch("/memory/state")).json();
  render(state);
}

async function flipCard(index) {
  if (clearing) return;
  state = await postJSON("/memory/flip", { index });
  render(state);
  if (state.mismatch) {
    clearing = true;
    setTimeout(async () => {
      state = await postJSON("/memory/clear", {});
      clearing = false;
      render(state);
    }, 900);
  }
}

async function newGame(theme, level) {
  clearing = false;
  state = await postJSON("/memory/new", {
    theme: theme || state?.theme || "farm",
    level: level || state?.level || "medium",
  });
  render(state);
}

async function setName(name) {
  state = await postJSON("/name", { name });
  render(state);
}

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------

function render(s) {
  // Stats
  els.moves.textContent   = s.moves;
  els.matched.textContent = s.matched;
  els.par.textContent     = s.par;
  els.scorePlayer.textContent = s.score.player;
  els.scoreComp.textContent   = s.score.hangman;

  // Theme buttons
  els.themeFarm.classList.toggle("active", s.theme === "farm");
  els.themeZoo.classList.toggle("active",  s.theme === "zoo");

  // Level buttons
  els.levelEasy.classList.toggle("active",   s.level === "easy");
  els.levelMedium.classList.toggle("active", s.level === "medium");
  els.levelHard.classList.toggle("active",   s.level === "hard");

  // Board
  els.board.innerHTML = "";
  s.cards.forEach((card, i) => {
    const btn = document.createElement("button");
    btn.className = "card " + card.state;
    btn.textContent = card.emoji || "";
    btn.setAttribute("aria-label", card.state === "hidden" ? "Hidden card" : card.emoji);
    if (s.mismatch && s.cards.filter(c => c.state === "revealed").indexOf(card) !== -1) {
      btn.classList.add("mismatch");
    }
    if (card.state === "hidden" && !s.over) {
      btn.addEventListener("click", () => flipCard(i));
    }
    els.board.appendChild(btn);
  });

  // Result banner
  if (s.over) {
    const won = s.moves <= s.par;
    els.result.textContent = won
      ? `🎉 You matched all pairs in ${s.moves} moves — under par!`
      : `All matched in ${s.moves} moves — par is ${s.par}. Keep practicing!`;
    els.result.className = "result " + (won ? "win" : "loss");
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

els.newGame.addEventListener("click",    () => newGame(state?.theme, state?.level));
els.themeFarm.addEventListener("click",  () => newGame("farm",  state?.level));
els.themeZoo.addEventListener("click",   () => newGame("zoo",   state?.level));
els.levelEasy.addEventListener("click",  () => newGame(state?.theme, "easy"));
els.levelMedium.addEventListener("click",() => newGame(state?.theme, "medium"));
els.levelHard.addEventListener("click",  () => newGame(state?.theme, "hard"));

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

loadState();
