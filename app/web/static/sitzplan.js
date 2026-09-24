// Seating plan (specification 5.6, 10).
//
// The plan the server sends back IS the confirmation -- it is rendered from
// the stored state, so a seat that moved on screen moved in the database.
// This file only covers the cases where no such answer arrives: the request
// is in flight, the connection dropped, the server refused.
//
// The quick entry of participation grades (mode "noten") gets the same
// treatment per field, as the serial entry does per row: several selects can
// be in flight at once, and each has to say for itself whether it was saved.

(function () {
  "use strict";

  // Ids of quick-entry fields whose request has not been answered yet.
  var offen = new Set();

  function zustandsfeld() {
    return document.querySelector("#sitzplan .sitzzustand");
  }

  function melde(text, art) {
    var feld = zustandsfeld();
    if (!feld) return;
    feld.textContent = text;
    feld.dataset.zustand = art;
  }

  function mitarbeitsfeldVon(ereignis) {
    var ziel = ereignis.target;
    return ziel && ziel.closest ? ziel.closest(".mitarbeitsfeld") : null;
  }

  function betrifftSitzplan(ereignis) {
    var ziel = ereignis.target;
    return !!(ziel && ziel.closest && ziel.closest("#sitzplan"));
  }

  function feldzustand(form, text, art) {
    var feld = form.querySelector(".feldzustand");
    if (feld) {
      feld.textContent = text;
      feld.dataset.zustand = art;
    }
    form.classList.toggle("fehlgeschlagen", art === "fehler");
    form.classList.toggle("sendet", art === "sendet");
    form.classList.remove("gespeichert");
  }

  // A quick-entry field failed. The field says so; the line above the grid
  // carries the reason, which does not fit under a photo.
  function feldFehler(form, grund) {
    offen.delete(form.id);
    feldzustand(form, "NICHT gespeichert", "fehler");
    melde("NICHT gespeichert – " + grund, "fehler");
  }

  document.body.addEventListener("htmx:beforeRequest", function (ereignis) {
    var form = mitarbeitsfeldVon(ereignis);
    if (form) {
      offen.add(form.id);
      feldzustand(form, "…", "sendet");
      return;
    }
    if (!betrifftSitzplan(ereignis)) return;
    melde("speichert …", "sendet");
  });

  // Connection gone: nothing was written, and it has to look that way.
  document.body.addEventListener("htmx:sendError", function (ereignis) {
    var form = mitarbeitsfeldVon(ereignis);
    if (form) return feldFehler(form, "keine Verbindung");
    if (!betrifftSitzplan(ereignis)) return;
    melde("NICHT gespeichert – keine Verbindung", "fehler");
  });

  // No answer within the configured limit -- the connection may be gone
  // without the phone having said so.
  document.body.addEventListener("htmx:timeout", function (ereignis) {
    var form = mitarbeitsfeldVon(ereignis);
    if (form) return feldFehler(form, "keine Antwort");
    if (!betrifftSitzplan(ereignis)) return;
    melde("NICHT gespeichert – keine Antwort", "fehler");
  });

  // The server answered and refused. Its sentence says why, so it is shown
  // instead of a generic one; htmx does not swap a 4xx by itself.
  document.body.addEventListener("htmx:responseError", function (ereignis) {
    if (!betrifftSitzplan(ereignis)) return;
    var antwort = ereignis.detail && ereignis.detail.xhr
      ? ereignis.detail.xhr.responseText
      : "";
    var text = antwort.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
    var form = mitarbeitsfeldVon(ereignis);
    if (form) return feldFehler(form, text || "vom Server abgewiesen");
    melde("NICHT gespeichert – " + (text || "vom Server abgewiesen"), "fehler");
  });

  // The swapped-in field carries the confirmation; only the bookkeeping is
  // left. Matched by id, because an outerHTML swap replaces the element.
  document.body.addEventListener("htmx:afterSwap", function (ereignis) {
    var ziel = ereignis.target;
    if (ziel && ziel.id) offen.delete(ziel.id);
  });

  // Leaving with a grade that was never confirmed would be the silent loss
  // the specification calls the worst conceivable failure (10).
  window.addEventListener("beforeunload", function (ereignis) {
    if (offen.size === 0 && !document.querySelector(".mitarbeitsfeld.fehlgeschlagen")) {
      return;
    }
    ereignis.preventDefault();
    ereignis.returnValue = "";
  });
})();
