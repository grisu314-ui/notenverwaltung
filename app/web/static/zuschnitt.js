// Square photo crop in the browser (specification 7).
//
// Deliberately without a library and deliberately without pinch-zoom: in a
// classroom the phone is held in one hand, and a slider is usable that way
// while two fingers are not. Dragging moves the image, the slider scales it.
//
// The canvas backing store is exactly the output size, so what is drawn is
// what gets uploaded -- no second resizing step that could disagree.

(function () {
  "use strict";

  var KANTE = 512;
  var QUALITAET = 0.8;

  var bereich = document.getElementById("fotoaufnahme");
  if (!bereich) return;

  var dateifeld = bereich.querySelector("input[type=file]");
  var flaeche = bereich.querySelector("canvas");
  var regler = bereich.querySelector("input[type=range]");
  var speichern = bereich.querySelector("[data-rolle=speichern]");
  var abbrechen = bereich.querySelector("[data-rolle=abbrechen]");
  var meldung = bereich.querySelector("[data-rolle=meldung]");
  var werkzeuge = bereich.querySelector("[data-rolle=werkzeuge]");
  var stift = flaeche.getContext("2d");

  var bild = null;
  var grundmass = 1;
  var versatz = { x: 0, y: 0 };
  var zieht = false;
  var zuletzt = { x: 0, y: 0 };

  function sagen(text, istFehler) {
    meldung.textContent = text;
    meldung.classList.toggle("fehler", Boolean(istFehler));
  }

  function zeichnen() {
    stift.fillStyle = "#ffffff";
    stift.fillRect(0, 0, KANTE, KANTE);
    if (!bild) return;
    var mass = grundmass * parseFloat(regler.value);
    var breite = bild.width * mass;
    var hoehe = bild.height * mass;
    stift.drawImage(bild, versatz.x, versatz.y, breite, hoehe);
  }

  function zentrieren() {
    var mass = grundmass * parseFloat(regler.value);
    versatz.x = (KANTE - bild.width * mass) / 2;
    versatz.y = (KANTE - bild.height * mass) / 2;
  }

  dateifeld.addEventListener("change", function () {
    var datei = dateifeld.files && dateifeld.files[0];
    if (!datei) return;
    var adresse = URL.createObjectURL(datei);
    var geladen = new Image();
    geladen.onload = function () {
      URL.revokeObjectURL(adresse);
      bild = geladen;
      // Start at "cover": the shorter side fills the square.
      grundmass = Math.max(KANTE / bild.width, KANTE / bild.height);
      regler.value = "1";
      zentrieren();
      zeichnen();
      werkzeuge.hidden = false;
      sagen("Ausschnitt wählen, dann speichern.", false);
    };
    geladen.onerror = function () {
      URL.revokeObjectURL(adresse);
      sagen("Die Datei konnte nicht gelesen werden.", true);
    };
    geladen.src = adresse;
  });

  regler.addEventListener("input", function () {
    if (!bild) return;
    zentrieren();
    zeichnen();
  });

  flaeche.addEventListener("pointerdown", function (ereignis) {
    if (!bild) return;
    zieht = true;
    zuletzt = { x: ereignis.clientX, y: ereignis.clientY };
    flaeche.setPointerCapture(ereignis.pointerId);
  });

  flaeche.addEventListener("pointermove", function (ereignis) {
    if (!zieht) return;
    // The canvas is displayed smaller than its backing store; move by the
    // same fraction of the picture, not by raw pixels.
    var faktor = KANTE / flaeche.getBoundingClientRect().width;
    versatz.x += (ereignis.clientX - zuletzt.x) * faktor;
    versatz.y += (ereignis.clientY - zuletzt.y) * faktor;
    zuletzt = { x: ereignis.clientX, y: ereignis.clientY };
    zeichnen();
  });

  ["pointerup", "pointercancel"].forEach(function (art) {
    flaeche.addEventListener(art, function () {
      zieht = false;
    });
  });

  abbrechen.addEventListener("click", function () {
    bild = null;
    dateifeld.value = "";
    werkzeuge.hidden = true;
    sagen("", false);
  });

  speichern.addEventListener("click", function () {
    if (!bild) return;
    speichern.disabled = true;
    sagen("speichert …", false);
    flaeche.toBlob(
      function (haeppchen) {
        if (!haeppchen) {
          speichern.disabled = false;
          sagen("Das Bild konnte nicht erzeugt werden.", true);
          return;
        }
        var paket = new FormData();
        paket.append("datei", haeppchen, "foto.jpg");
        fetch(bereich.dataset.ziel, { method: "POST", body: paket })
          .then(function (antwort) {
            if (antwort.ok) {
              window.location.reload();
              return;
            }
            speichern.disabled = false;
            sagen("NICHT gespeichert – der Server hat abgelehnt.", true);
          })
          .catch(function () {
            speichern.disabled = false;
            sagen("NICHT gespeichert – keine Verbindung.", true);
          });
      },
      "image/jpeg",
      QUALITAET
    );
  });
})();
