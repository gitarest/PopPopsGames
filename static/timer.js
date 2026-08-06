"use strict";

/**
 * Shared game timer: starts on the player's first interaction with the page,
 * stops when the caller calls stop() (typically when the puzzle/game ends).
 * Purely a client-side display — not reported to the server or used for scoring.
 *
 * Usage:
 *   const timer = createGameTimer(document.getElementById("timer"));
 *   timer.armAutoStart();       // starts on first click/keydown/touch
 *   ...
 *   if (s.over) timer.stop();   // in render(), once the game is won/finished
 *   ...
 *   timer.reset();              // on New Game — clears display, re-arm below
 *   timer.armAutoStart();
 */
function createGameTimer(displayEl) {
  let startTime = null;
  let stopTime = null;
  let intervalHandle = null;
  let armedEvents = [];

  function formatTime(totalSeconds) {
    const m = Math.floor(totalSeconds / 60);
    const s = totalSeconds % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  function elapsedSeconds() {
    if (startTime === null) return 0;
    const end = stopTime !== null ? stopTime : Date.now();
    return Math.floor((end - startTime) / 1000);
  }

  function render() {
    if (displayEl) displayEl.textContent = formatTime(elapsedSeconds());
  }

  function start() {
    if (startTime !== null) return;  // already started (or already stopped)
    startTime = Date.now();
    intervalHandle = setInterval(render, 1000);
    render();
  }

  function stop() {
    if (startTime === null || stopTime !== null) return;
    stopTime = Date.now();
    clearInterval(intervalHandle);
    intervalHandle = null;
    render();
  }

  function disarm() {
    armedEvents.forEach(([evt, fn]) => document.removeEventListener(evt, fn));
    armedEvents = [];
  }

  function armAutoStart() {
    disarm();
    const trigger = () => { start(); disarm(); };
    ["click", "keydown", "touchstart"].forEach(evt => {
      document.addEventListener(evt, trigger);
      armedEvents.push([evt, trigger]);
    });
  }

  function reset() {
    disarm();
    clearInterval(intervalHandle);
    intervalHandle = null;
    startTime = null;
    stopTime = null;
    render();
  }

  render();
  return { start, stop, reset, armAutoStart, elapsedSeconds, formatTime };
}
