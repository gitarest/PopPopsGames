"use strict";

const els = {
  status:       document.getElementById("status"),
  scorePlayer:  document.getElementById("score-player"),
  scoreHangman: document.getElementById("score-hangman"),
  tallyName:    document.getElementById("tally-name"),
  tallyPlayer:  document.getElementById("tally-player"),
  tallyDealer:  document.getElementById("tally-dealer"),
  tallyTies:    document.getElementById("tally-ties"),
  cardsLeft:    document.getElementById("cards-remaining"),
  dealerHand:   document.getElementById("dealer-hand"),
  playerHand:   document.getElementById("player-hand"),
  dealerValue:  document.getElementById("dealer-value"),
  playerValue:  document.getElementById("player-value"),
  btnHit:       document.getElementById("btn-hit"),
  btnStand:     document.getElementById("btn-stand"),
  btnDeal:      document.getElementById("btn-deal"),
  btnNew:       document.getElementById("btn-new"),
  nameBtn:      document.getElementById("name-btn"),
  nameInput:    document.getElementById("name-input"),
  nameList:     document.getElementById("name-list"),
};

let state = null;

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return res.json();
}

function cardEl(card) {
  const div = document.createElement("div");
  const isRed = card.suit === "♥" || card.suit === "♦";
  if (card.rank === "?") {
    div.className = "card hidden";
    div.textContent = "🂠";
  } else {
    div.className = "card" + (isRed ? " red" : "");
    div.innerHTML =
      `<span class="card-rank">${card.rank}</span>` +
      `<span class="card-suit">${card.suit}</span>`;
  }
  return div;
}

function renderHand(el, hand) {
  el.innerHTML = "";
  (hand || []).forEach(c => el.appendChild(cardEl(c)));
}

const STATUS_MSGS = {
  player:          "Your turn — Hit or Stand",
  player_blackjack:"21! You win! 🎉",
  dealer_blackjack:"Dealer has 21!",
  push_blackjack:  "Both have 21 — Push!",
  player_bust:     "Bust! You went over 21.",
  dealer_bust:     "Dealer busts — you win! 🎉",
  player_higher:   "You win! 🎉",
  dealer_higher:   "Dealer wins.",
  push:            "Push — it's a tie!",
};

const WIN_RESULTS  = new Set(["player_blackjack", "dealer_bust", "player_higher"]);
const LOSS_RESULTS = new Set(["dealer_blackjack", "player_bust", "dealer_higher"]);

function render(s) {
  state = s;

  if (s.score) {
    els.scorePlayer.textContent  = s.score.player  || 0;
    els.scoreHangman.textContent = s.score.hangman || 0;
  }
  els.nameBtn.textContent = s.name || "Guest";
  if (els.tallyName) els.tallyName.textContent = s.name || "Guest";

  els.tallyPlayer.textContent = s.player_wins  || 0;
  els.tallyDealer.textContent = s.computer_wins || 0;
  els.tallyTies.textContent   = s.ties          || 0;
  els.cardsLeft.textContent   = s.cards_remaining != null ? s.cards_remaining : "?";

  renderHand(els.dealerHand, s.dealer_hand);
  renderHand(els.playerHand, s.player_hand);

  els.dealerValue.textContent = s.dealer_value != null ? `(${s.dealer_value})` : "";
  els.playerValue.textContent = s.player_value != null ? `(${s.player_value})` : "";

  const statusEl = els.status;
  statusEl.className = "status";

  if (s.phase === "player") {
    statusEl.textContent = STATUS_MSGS.player;
  } else if (s.phase === "deck_over") {
    const pw = s.player_wins || 0, cw = s.computer_wins || 0;
    if (pw > cw) {
      statusEl.textContent = `Deck over — you won! (${pw}–${cw}) 🎉`;
      statusEl.classList.add("win");
    } else if (cw > pw) {
      statusEl.textContent = `Deck over — dealer wins. (${cw}–${pw})`;
      statusEl.classList.add("loss");
    } else {
      statusEl.textContent = `Deck over — it's a tie! (${pw}–${cw})`;
      statusEl.classList.add("draw");
    }
  } else if (s.round_result) {
    statusEl.textContent = STATUS_MSGS[s.round_result] || s.round_result;
    if (WIN_RESULTS.has(s.round_result))       statusEl.classList.add("win");
    else if (LOSS_RESULTS.has(s.round_result)) statusEl.classList.add("loss");
    else                                        statusEl.classList.add("draw");
  } else {
    statusEl.textContent = "Dealing…";
  }

  const isPlayer  = s.phase === "player";
  const isOver    = s.phase === "round_over";
  const isDeckOver = s.phase === "deck_over";
  const canDeal   = isOver && (s.cards_remaining >= 4);

  els.btnHit.disabled   = !isPlayer;
  els.btnStand.disabled = !isPlayer;
  els.btnDeal.disabled  = !canDeal;
  els.btnDeal.hidden    = isDeckOver;
}

els.btnHit.addEventListener("click",   async () => render(await postJSON("/blackjack/hit",   {})));
els.btnStand.addEventListener("click", async () => render(await postJSON("/blackjack/stand", {})));
els.btnDeal.addEventListener("click",  async () => render(await postJSON("/blackjack/deal",  {})));
els.btnNew.addEventListener("click",   async () => render(await postJSON("/blackjack/new",   {})));

// ---- Name editor (same pattern as other games) ----

async function setName(name) {
  await postJSON("/name", { name: name || "" });
  render(await (await fetch("/blackjack/state")).json());
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
  els.nameBtn.hidden  = true;
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

// ---- Page leave → finalize for scoring ----

function sendFinalize() {
  navigator.sendBeacon("/blackjack/finalize", JSON.stringify({}));
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") sendFinalize();
});
window.addEventListener("pagehide", sendFinalize);

// ---- Boot ----

async function loadState() {
  render(await (await fetch("/blackjack/state")).json());
}

loadState();
