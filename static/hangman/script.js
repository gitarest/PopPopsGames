"use strict";

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");

const els = {
  word: document.getElementById("word"),
  status: document.getElementById("status"),
  wrong: document.getElementById("wrong"),
  max: document.getElementById("max"),
  keyboard: document.getElementById("keyboard"),
  newGame: document.getElementById("new-game"),
  levels: document.getElementById("levels"),
  scorePlayer: document.getElementById("score-player"),
  scoreHangman: document.getElementById("score-hangman"),
  nameBtn: document.getElementById("name-btn"),
  nameInput: document.getElementById("name-input"),
  nameList: document.getElementById("name-list"),
  parts: Array.from(document.querySelectorAll(".part")),
};

let state = null;

// Build the on-screen keyboard once.
const keyButtons = {};
for (const letter of LETTERS) {
  const btn = document.createElement("button");
  btn.textContent = letter;
  btn.addEventListener("click", () => guess(letter));
  els.keyboard.appendChild(btn);
  keyButtons[letter] = btn;
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return res.json();
}

// Remembers the player's last-used difficulty on this device, so it survives
// reloads and server restarts (sessions are in-memory and reset on restart).
const LEVEL_KEY = "hangman.level";

async function loadState() {
  const res = await fetch("/state");
  const s = await res.json();
  const pref = localStorage.getItem(LEVEL_KEY);
  // On a fresh, untouched game (e.g. a new session after a restart) restore the
  // remembered level. A game already in progress is left alone on reload.
  const fresh = s.guessed.length === 0 && s.wrong === 0 && !s.over;
  if (pref && s.levels.includes(pref) && pref !== s.level && fresh) {
    render(await postJSON("/new", { level: pref }));
  } else {
    render(s);
  }
}

async function guess(letter) {
  if (!state || state.over || state.guessed.includes(letter)) return;
  render(await postJSON("/guess", { letter }));
}

// Start a new game. Pass a level to switch difficulty; omit it to keep the
// session's current level. A chosen level is remembered for next time.
async function startNew(level) {
  if (level) localStorage.setItem(LEVEL_KEY, level);
  render(await postJSON("/new", level ? { level } : {}));
}

// Set (or clear) the player's name. Blank switches to guest play. Named scores
// are saved on the server and reload when you enter the same name again.
async function setName(name) {
  render(await postJSON("/name", { name: name || "" }));
}

// Build the difficulty buttons once, from the level list the server sends.
const levelButtons = {};
function buildLevels(levels) {
  if (Object.keys(levelButtons).length) return;
  for (const level of levels) {
    const btn = document.createElement("button");
    btn.textContent = level;
    btn.addEventListener("click", () => startNew(level));
    els.levels.appendChild(btn);
    levelButtons[level] = btn;
  }
}

function render(newState) {
  state = newState;
  const guessed = new Set(state.guessed);

  // Difficulty picker: build once, then highlight the active level.
  if (state.levels) buildLevels(state.levels);
  for (const [level, btn] of Object.entries(levelButtons)) {
    btn.classList.toggle("active", level === state.level);
  }

  // Session scoreboard. The player's side shows their name (or "Guest").
  if (state.score) {
    els.scorePlayer.textContent = state.score.player;
    els.scoreHangman.textContent = state.score.hangman;
  }
  els.nameBtn.textContent = state.name || "Guest";

  // Word display. If lost, fill in the missed letters in red.
  els.word.classList.toggle("lost", state.lost);
  els.word.innerHTML = "";
  state.masked.forEach((ch, i) => {
    const span = document.createElement("span");
    span.className = "letter";
    if (ch !== "_") {
      span.textContent = ch;
      span.classList.add("filled");
    } else if (state.lost && state.word) {
      span.textContent = state.word[i];
      span.classList.add("filled", "missed");
    }
    els.word.appendChild(span);
  });

  // Wrong-guess counter + drawing.
  els.wrong.textContent = state.wrong;
  els.max.textContent = state.max_wrong;
  els.parts.forEach((part) => {
    const n = Number(part.dataset.part);
    part.classList.toggle("show", n <= state.wrong);
  });

  // Keyboard: color and disable guessed letters; disable all when over.
  for (const letter of LETTERS) {
    const btn = keyButtons[letter];
    btn.classList.remove("correct", "wrong");
    if (guessed.has(letter)) {
      const hit = state.word ? state.word.includes(letter)
                             : state.masked.includes(letter);
      btn.classList.add(hit ? "correct" : "wrong");
      btn.disabled = true;
    } else {
      btn.disabled = state.over;
    }
  }

  // Status message.
  els.status.className = "status";
  if (state.won) {
    els.status.textContent = "🎉 You won!";
    els.status.classList.add("won");
  } else if (state.lost) {
    els.status.textContent = `💀 Out of guesses — the word was "${state.word}".`;
    els.status.classList.add("lost");
  } else {
    els.status.innerHTML = "&nbsp;";
  }
}

// Step to an adjacent difficulty (dir -1 = easier, +1 = harder), which starts
// a fresh game at that level. Clamps at the ends.
function stepLevel(dir) {
  if (!state || !state.levels) return;
  const i = state.levels.indexOf(state.level);
  const next = i + dir;
  if (next >= 0 && next < state.levels.length) startNew(state.levels[next]);
}

// Physical keyboard support.
document.addEventListener("keydown", (e) => {
  // Ignore game shortcuts while typing in the name field.
  if (e.target && e.target.tagName === "INPUT") return;
  if (e.key === "ArrowLeft")  { stepLevel(-1); return; }
  if (e.key === "ArrowRight") { stepLevel(1);  return; }
  const key = e.key.toUpperCase();
  if (key === "ENTER") { startNew(); return; }
  if (key.length === 1 && key >= "A" && key <= "Z") guess(key);
});

// Wrap in an arrow fn so the click Event isn't passed as the level argument.
els.newGame.addEventListener("click", () => startNew());

// Inline name editor: tapping the name opens an empty text input plus a
// dropdown of the *other* known players (alphabetical), so you can type a new
// name or click an existing one. A "Guest" entry lets a named player drop back
// to guest. Tapping away without typing keeps the current name.
let committing = false;

function commitName(value) {
  committing = true;   // tell the upcoming blur this isn't a cancel
  hideNameEditor();
  setName(value);      // "" => guest
}

function addNameOption(label, value) {
  const li = document.createElement("li");
  li.textContent = label;
  // mousedown (not click) fires before the input's blur, and preventDefault
  // keeps focus so the commit ordering stays predictable.
  li.addEventListener("mousedown", (e) => { e.preventDefault(); commitName(value); });
  els.nameList.appendChild(li);
}

// (Re)build the dropdown: a "Guest" entry (when currently named) plus the other
// players whose name starts with `filter`.
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
  els.nameInput.value = "";  // start empty, ready to type
  els.nameBtn.hidden = true;
  els.nameInput.hidden = false;
  renderNameList("");  // show the other known players, alphabetically
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
    if (v) commitName(v); else hideNameEditor();  // empty Enter just closes
  } else if (e.key === "Escape") {
    hideNameEditor();
  }
});

// On blur: commit typed text if any; an empty field means "tapped away without
// choosing", so keep the current name rather than dropping to guest.
els.nameInput.addEventListener("blur", () => {
  if (committing) { committing = false; return; }
  const v = els.nameInput.value.trim();
  hideNameEditor();
  if (v) setName(v);
});

loadState();
