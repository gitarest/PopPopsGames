"use strict";

let state = null;
let levelsBuilt = false;
let selected = null;      // {index, seg} of the picked-up stick, or null
let demoing = false;      // true while a demo loop (Show Me or Solve One For Me) is running
let demoGeneration = 0;   // bumped whenever a demo loop should be superseded/stopped

// Segment coordinates for each cell kind (standard 7-segment digit layout).
const DIGIT_COORDS = {
  a: [10, 5, 30, 5],
  b: [34, 8, 34, 32],
  c: [34, 38, 34, 62],
  d: [10, 65, 30, 65],
  e: [6, 38, 6, 62],
  f: [6, 8, 6, 32],
  g: [10, 35, 30, 35],
};
const OPERATOR_COORDS = {
  h: [4, 12, 20, 12],
  v: [12, 4, 12, 20],
};
const EQUALS_BARS = [[4, 10, 20, 10], [4, 20, 20, 20]];

const els = {
  levelToggle: document.getElementById("level-toggle"),
  status:      document.getElementById("status"),
  equation:    document.getElementById("equation"),
  moves:       document.getElementById("moves"),
  result:      document.getElementById("result"),
  newGame:     document.getElementById("new-game"),
  scorePlayer: document.getElementById("score-player"),
  scoreComp:   document.getElementById("score-hangman"),
  nameBtn:     document.getElementById("name-btn"),
  nameInput:   document.getElementById("name-input"),
  nameList:    document.getElementById("name-list"),
  showMe:      document.getElementById("show-me"),
  resetBtn:    document.getElementById("reset-puzzle"),
  giveUpBtn:   document.getElementById("give-up"),
  solveBtn:    document.getElementById("solve-for-me"),
  solveDialog: document.getElementById("solve-dialog"),
  solveForm:   document.getElementById("solve-form"),
  solveInput:  document.getElementById("solve-input"),
  solveError:  document.getElementById("solve-error"),
  solveCancel: document.getElementById("solve-cancel"),
};

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

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
  state = await (await fetch("/matchstick/state")).json();
  render(state);
}

async function moveStick(fromIndex, fromSeg, toIndex, toSeg) {
  state = await postJSON("/matchstick/move", {
    from_index: fromIndex, from_seg: fromSeg, to_index: toIndex, to_seg: toSeg,
  });
  render(state);
}

function stopDemo() {
  demoing = false;
  demoGeneration++;
}

async function newGame(level) {
  stopDemo();
  selected = null;
  state = await postJSON("/matchstick/new", { level: level || state?.level });
  render(state);
}

async function resetPuzzle() {
  stopDemo();
  selected = null;
  state = await postJSON("/matchstick/reset", {});
  render(state);
}

async function giveUp() {
  stopDemo();
  selected = null;
  state = await postJSON("/matchstick/give_up", {});
  render(state);
  if (state.solution && state.solution.length > 0) {
    const moveWord = state.solution.length === 1 ? "move" : "moves";
    runDemoLoop(
      state.original_slots,
      state.solution,
      `You gave up — it takes ${state.solution.length} ${moveWord} to fix. Tap New Game or Reset to stop.`
    );
  }
}

async function setName(name) {
  state = await postJSON("/name", { name });
  render(state);
}

// ---------------------------------------------------------------------------
// Interaction
// ---------------------------------------------------------------------------

function onStickClick(index, seg, lit) {
  if (state.over) return;
  if (selected === null) {
    if (lit) selected = { index, seg };
    renderEquationOnly();
    return;
  }
  if (selected.index === index && selected.seg === seg) {
    selected = null;  // put it back down where it was
    renderEquationOnly();
    return;
  }
  if (lit) {
    selected = { index, seg };  // pick up this one instead
    renderEquationOnly();
    return;
  }
  // Placing the picked-up stick here.
  const from = selected;
  selected = null;
  moveStick(from.index, from.seg, index, seg);
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

function makeSvg(viewBox) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", viewBox);
  return svg;
}

const SVG_NS = "http://www.w3.org/2000/svg";

function makeStick([x1, y1, x2, y2], lit, clickable) {
  const g = document.createElementNS(SVG_NS, "g");
  g.classList.add("stick-group");
  if (clickable) g.classList.add("clickable");

  // Shaft stops short of the tip so the head circle visually caps it.
  const shaftX = x1 + (x2 - x1) * 0.8;
  const shaftY = y1 + (y2 - y1) * 0.8;
  const shaft = document.createElementNS(SVG_NS, "line");
  shaft.setAttribute("x1", x1);
  shaft.setAttribute("y1", y1);
  shaft.setAttribute("x2", shaftX);
  shaft.setAttribute("y2", shaftY);
  shaft.classList.add("stick-shaft", lit ? "lit" : "unlit");
  g.appendChild(shaft);

  const head = document.createElementNS(SVG_NS, "circle");
  head.setAttribute("cx", x2);
  head.setAttribute("cy", y2);
  head.setAttribute("r", 3.5);
  head.classList.add("stick-head", lit ? "lit" : "unlit");
  g.appendChild(head);

  if (clickable) {
    // Wide invisible hit-area so small matchstick targets stay tappable on phones.
    const hit = document.createElementNS(SVG_NS, "line");
    hit.setAttribute("x1", x1);
    hit.setAttribute("y1", y1);
    hit.setAttribute("x2", x2);
    hit.setAttribute("y2", y2);
    hit.classList.add("stick-hit");
    g.appendChild(hit);
  }

  return g;
}

/**
 * Draws the equation from `slots` into #equation. In interactive mode, digit
 * and operator sticks get click handlers and reflect the current `selected`
 * pickup; in demo mode (interactive=false) nothing is clickable and a single
 * stick can be flagged via `flash` to pulse gold, for the "Show Me" replay.
 */
function buildEquationCells(slots, { interactive, flash }) {
  els.equation.innerHTML = "";
  slots.forEach((slot, index) => {
    const cell = document.createElement("div");
    cell.className = "cell " + slot.kind;

    const drawSeg = (svg, coords, seg, lit) => {
      const stick = makeStick(coords, lit, interactive);
      if (interactive && selected && selected.index === index && selected.seg === seg) {
        stick.classList.add("selected");
      }
      if (flash && flash.index === index && flash.seg === seg) {
        stick.classList.add("demo-flash");
      }
      if (interactive) {
        stick.addEventListener("click", () => onStickClick(index, seg, lit));
      }
      svg.appendChild(stick);
    };

    if (slot.kind === "digit") {
      const svg = makeSvg("0 0 40 70");
      Object.entries(DIGIT_COORDS).forEach(([seg, coords]) => drawSeg(svg, coords, seg, slot.segments.includes(seg)));
      cell.appendChild(svg);
    } else if (slot.kind === "operator") {
      const svg = makeSvg("0 0 24 24");
      Object.entries(OPERATOR_COORDS).forEach(([seg, coords]) => drawSeg(svg, coords, seg, slot.segments.includes(seg)));
      cell.appendChild(svg);
    } else {
      const svg = makeSvg("0 0 24 30");
      EQUALS_BARS.forEach(coords => svg.appendChild(makeStick(coords, true, false)));
      cell.appendChild(svg);
    }

    els.equation.appendChild(cell);
  });

  fitEquationWidth();
}

/**
 * Long equations (e.g. "25 + 32 = 27") can be wider than a phone screen at
 * the doubled stick size. Rather than wrapping mid-equation, shrink the whole
 * row uniformly (via transform: scale) just enough to fit in one line.
 *
 * #equation deliberately has no CSS width — it sizes to its own content
 * (which can exceed the .game column's width). Comparing against the
 * *parent's* clientWidth (not #equation's own) is what makes this work:
 * scaling an element whose own box already equals its content shrinks the
 * whole thing uniformly to fit. Scaling a box that's fixed-width with
 * overflowing children inside it (the first version of this) doesn't help —
 * the box and its overflow shrink by the same factor, so the fraction that
 * overflows (and gets clipped) never changes.
 *
 * Also avoids els.equation.scrollWidth for the "natural" measurement: with
 * justify-content:center on an overflowing nowrap flex row, overflow spills
 * evenly onto both sides, and scrollWidth only accounts for the "end" side.
 * Summing the children's own widths sidesteps that.
 */
function fitEquationWidth() {
  els.equation.style.transform = "none";
  const children = Array.from(els.equation.children);
  if (children.length === 0) return;
  const gap = parseFloat(getComputedStyle(els.equation).columnGap) || 0;
  const natural = children.reduce((sum, el) => sum + el.offsetWidth, 0) + gap * (children.length - 1);
  const available = els.equation.parentElement.clientWidth;
  const scale = available > 0 && natural > available ? available / natural : 1;
  els.equation.style.transform = scale < 1 ? `scale(${scale})` : "none";
}

function renderEquationOnly() {
  buildEquationCells(state.slots, { interactive: true, flash: null });
}

/**
 * Loops a solution demo (flash pickup, flash place, apply, pause per move,
 * then a longer pause on the fully-solved equation) forever, until superseded
 * by another runDemoLoop() call or stopped via stopDemo() (New Game, Reset).
 * `solutionMoves` is a list of {from_index, from_seg, to_index, to_seg}.
 * Neither Show Me nor Solve One For Me get disabled while this runs — either
 * one can be clicked again at any time to switch to a different demo.
 */
async function runDemoLoop(originalSlots, solutionMoves, statusText) {
  if (!solutionMoves || solutionMoves.length === 0) return;
  const myGen = ++demoGeneration;
  demoing = true;
  const moveWord = solutionMoves.length === 1 ? "move" : "moves";
  els.status.textContent = statusText
    || `Solvable in ${solutionMoves.length} ${moveWord} — showing how. Tap New Game or Reset to stop.`;

  const stillCurrent = () => demoing && myGen === demoGeneration;

  while (stillCurrent()) {
    const demo = originalSlots.map(s => ({ kind: s.kind, segments: [...s.segments] }));

    for (const move of solutionMoves) {
      if (!stillCurrent()) break;
      buildEquationCells(demo, { interactive: false, flash: { index: move.from_index, seg: move.from_seg } });
      await sleep(900);

      if (!stillCurrent()) break;
      buildEquationCells(demo, { interactive: false, flash: { index: move.to_index, seg: move.to_seg } });
      await sleep(900);

      if (!stillCurrent()) break;
      demo[move.from_index].segments = demo[move.from_index].segments.filter(seg => seg !== move.from_seg);
      demo[move.to_index].segments = [...demo[move.to_index].segments, move.to_seg];
      buildEquationCells(demo, { interactive: false, flash: null });
      await sleep(700);
    }

    if (!stillCurrent()) break;
    await sleep(1200);  // pause on the fully-solved equation before looping again
  }
}

function showMe() {
  if (!state || !state.over || !state.solution || state.solution.length === 0) return;
  runDemoLoop(state.original_slots, state.solution);
}

async function solveForMe(equationText) {
  els.solveError.hidden = true;
  const data = await postJSON("/matchstick/solve", { equation: equationText });
  if (!data.ok) {
    els.solveError.textContent = data.error;
    els.solveError.hidden = false;
    return;
  }
  els.solveDialog.close();
  if (data.moves_needed === 0) {
    stopDemo();
    els.status.textContent = "That equation is already correct — nothing to fix!";
    return;
  }
  const moveWord = data.moves_needed === 1 ? "move" : "moves";
  runDemoLoop(
    data.original_slots,
    data.solution,
    `That takes ${data.moves_needed} ${moveWord} to fix — showing how. Tap New Game or Reset to stop.`
  );
}

function render(s) {
  buildLevelToggle(s.levels);
  els.levelToggle.querySelectorAll(".level-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.level === s.level);
  });

  els.moves.textContent = s.moves_used;
  els.scorePlayer.textContent = s.score.player;
  els.scoreComp.textContent   = s.score.hangman;

  renderEquationOnly();

  els.showMe.classList.toggle("actions-inactive", !s.over);

  if (s.over) {
    els.status.textContent = "";
    if (s.gave_up) {
      els.result.textContent = "No worries — here's the solution!";
      els.result.className = "result";
    } else {
      const onPar = s.moves_used <= s.par_moves;
      els.result.textContent = onPar
        ? `🎉 Fixed it in ${s.moves_used} move${s.moves_used === 1 ? "" : "s"} — nice!`
        : `Fixed it in ${s.moves_used} moves. The goal was ${s.par_moves} — try New Game for another shot!`;
      els.result.className = "result win";
    }
    els.result.hidden = false;
  } else {
    els.status.textContent = selected
      ? "Now tap an empty spot to place the stick."
      : "Move one matchstick to fix the equation!";
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
els.showMe.addEventListener("click", showMe);
els.resetBtn.addEventListener("click", resetPuzzle);
els.giveUpBtn.addEventListener("click", giveUp);

function openSolveDialog() {
  els.solveError.hidden = true;
  els.solveInput.value = "";

  const rect = els.solveBtn.getBoundingClientRect();
  const dialogWidth = Math.min(340, window.innerWidth * 0.9);
  const estimatedHeight = 240;  // rough; dialog content is roughly fixed-size

  let left = rect.left + rect.width / 2 - dialogWidth / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - dialogWidth - 8));

  let top = rect.bottom + 8;
  if (top + estimatedHeight > window.innerHeight) {
    top = Math.max(8, rect.top - estimatedHeight - 8);
  }

  els.solveDialog.style.position = "fixed";
  els.solveDialog.style.margin = "0";
  els.solveDialog.style.left = `${left}px`;
  els.solveDialog.style.top = `${top}px`;

  els.solveDialog.showModal();
  els.solveInput.focus();
}

els.solveBtn.addEventListener("click", openSolveDialog);

els.solveCancel.addEventListener("click", () => {
  els.solveDialog.close();
});

els.solveForm.addEventListener("submit", e => {
  e.preventDefault();
  const text = els.solveInput.value.trim();
  solveForMe(text);
});

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

loadState();
