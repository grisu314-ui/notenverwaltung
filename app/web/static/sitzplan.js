// Seating plan (specification 5.6, 10).
//
// The plan the server sends back IS the confirmation -- it is rendered from
// the stored state, so a seat that moved on screen moved in the database.
// This file only covers the cases where no such answer arrives: the request
// is in flight, the connection dropped, the server refused.

(function () {
  "use strict";

  function zustandsfeld() {
    return document.querySelector("#sitzplan .sitzzustand");
  }

  function melde(text, art) {
    var feld = zustandsfeld();
    if (!feld) return;
    feld.textContent = text;
    feld.dataset.zustand = art;
  }

  function betrifftSitzplan(ereignis) {
    var ziel = ereignis.target;
    return !!(ziel && ziel.closest && ziel.closest("#sitzplan"));
  }

  document.body.addEventListener("htmx:beforeRequest", function (ereignis) {
    if (!betrifftSitzplan(ereignis)) return;
    melde("speichert …", "sendet");
  });

  // Connection gone: nothing was written, and it has to look that way.
  document.body.addEventListener("htmx:sendError", function (ereignis) {
    if (!betrifftSitzplan(ereignis)) return;
    melde("NICHT gespeichert – keine Verbindung", "fehler");
  });

  // The server answered and refused. Its sentence says why, so it is shown
  // instead of a generic one; htmx does not swap a 4xx by itself.
  document.body.addEventListener("htmx:responseError", function (ereignis) {
    if (!betrifftSitzplan(ereignis)) return;
    var antwort = ereignis.detail && ereignis.detail.xhr
      ? ereignis.detail.xhr.responseText
      : "";
    var text = antwort.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
    melde("NICHT gespeichert – " + (text || "vom Server abgewiesen"), "fehler");
  });
})();
