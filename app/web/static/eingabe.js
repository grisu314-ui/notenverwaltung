// Serial grade entry (specification 5.4, 10).
//
// The one job of this file: a row must never look saved when it is not. htmx
// swaps in the row the server rendered from the stored record, so a successful
// save confirms itself. Everything here handles the other cases -- the request
// is in flight, the connection dropped, the server refused.

(function () {
  "use strict";

  var offen = new Set();

  function zustand(zeile, text, art) {
    var feld = zeile.querySelector(".zustand");
    if (feld) {
      feld.textContent = text;
      feld.dataset.zustand = art;
    }
    zeile.classList.toggle("fehlgeschlagen", art === "fehler");
    zeile.classList.toggle("sendet", art === "sendet");
  }

  function zeileVon(ereignis) {
    var ziel = ereignis.target;
    return ziel && ziel.closest ? ziel.closest(".notenzeile") : null;
  }

  document.body.addEventListener("htmx:beforeRequest", function (ereignis) {
    var zeile = zeileVon(ereignis);
    if (!zeile) return;
    offen.add(zeile.id);
    zustand(zeile, "speichert …", "sendet");
  });

  // Connection gone: nothing was written, and it has to look that way.
  document.body.addEventListener("htmx:sendError", function (ereignis) {
    var zeile = zeileVon(ereignis);
    if (!zeile) return;
    zustand(zeile, "NICHT gespeichert – keine Verbindung", "fehler");
  });

  // No answer within the configured limit. The phone never reported the lost
  // connection -- observed in the classroom -- so the limit is what turns a
  // request that hangs into a visible failure.
  document.body.addEventListener("htmx:timeout", function (ereignis) {
    var zeile = zeileVon(ereignis);
    if (!zeile) return;
    zustand(zeile, "NICHT gespeichert – keine Antwort", "fehler");
  });

  // Server answered, but refused.
  document.body.addEventListener("htmx:responseError", function (ereignis) {
    var zeile = zeileVon(ereignis);
    if (!zeile) return;
    zustand(zeile, "NICHT gespeichert – vom Server abgewiesen", "fehler");
  });

  // The swapped-in row carries the confirmation; only the follow-up is left.
  document.body.addEventListener("htmx:afterSwap", function (ereignis) {
    var zeile = ereignis.target;
    if (!zeile || !zeile.classList || !zeile.classList.contains("notenzeile")) return;
    offen.delete(zeile.id);

    var zeilen = Array.prototype.slice.call(
      document.querySelectorAll(".notenzeile")
    );
    var naechste = zeilen[zeilen.indexOf(zeile) + 1];
    if (naechste) {
      var feld = naechste.querySelector("select");
      if (feld) feld.focus();
    }
  });

  // Leaving with a row that was never confirmed would be the silent loss the
  // specification calls the worst conceivable failure of this application.
  window.addEventListener("beforeunload", function (ereignis) {
    if (offen.size === 0 && !document.querySelector(".notenzeile.fehlgeschlagen")) {
      return;
    }
    ereignis.preventDefault();
    ereignis.returnValue = "";
  });
})();
