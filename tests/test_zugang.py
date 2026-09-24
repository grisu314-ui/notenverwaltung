"""The access path in front of the application (specification 2).

Tailscale, then the Caddy gate with basic auth, then the application in an
internal network without a way out. None of this is application code, and
none of it can be exercised without Docker -- the full path was tried by hand
against a running stack (docs/inbetriebnahme-truenas.md, "Abnahme").

What these tests hold in place are the lines whose loss would not show up in
normal use: a `ports:` entry that opens the application to the LAN, the
application back in the sidecar's namespace and thereby around the gate, or a
proxy target that loops back into the gate itself.

Read as text on purpose: PyYAML is not a dependency, and these are line-level
facts, not structure worth a parser.
"""

import re
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parent.parent
COMPOSE_DATEIEN = ("docker-compose.yml", "docker-compose.truenas.yml")


def _ohne_kommentare(text: str) -> str:
    return "\n".join(
        zeile for zeile in text.splitlines() if not zeile.lstrip().startswith("#")
    )


def _dienste(text: str) -> dict[str, str]:
    """Service name -> its block, split by indentation."""
    dienste: dict[str, list[str]] = {}
    aktuell = None
    in_services = False
    for zeile in _ohne_kommentare(text).splitlines():
        if not zeile.strip():
            continue
        if not zeile.startswith(" "):
            in_services = zeile.startswith("services:")
            aktuell = None
            continue
        if in_services and re.fullmatch(r"  [\w-]+:\s*", zeile):
            aktuell = zeile.strip().rstrip(":")
            dienste[aktuell] = []
        elif aktuell is not None:
            dienste[aktuell].append(zeile)
    return {name: "\n".join(block) for name, block in dienste.items()}


@pytest.fixture(params=COMPOSE_DATEIEN)
def compose(request) -> str:
    return (WURZEL / request.param).read_text(encoding="utf-8")


def test_kein_dienst_veroeffentlicht_einen_port(compose):
    """A `ports:` on the sidecar or the gate would open the application to the LAN."""
    assert re.search(r"^\s*ports\s*:", _ohne_kommentare(compose), re.M) is None


def test_es_gibt_genau_die_drei_dienste(compose):
    assert set(_dienste(compose)) == {"tailscale", "pforte", "notenverwaltung"}


def test_die_anwendung_ist_nur_ueber_die_pforte_erreichbar(compose):
    anwendung = _dienste(compose)["notenverwaltung"]

    assert "network_mode" not in anwendung
    assert re.search(r"^\s+intern:\s*$", anwendung, re.M)
    assert re.search(r"^\s+- anwendung\s*$", anwendung, re.M)


def test_die_pforte_haengt_im_netz_des_sidecars(compose):
    pforte = _dienste(compose)["pforte"]

    assert "network_mode: service:tailscale" in pforte
    assert "${PFORTE_USER:?" in pforte
    assert "${PFORTE_HASH:?" in pforte


def test_das_interne_netz_hat_keinen_ausgang(compose):
    """Specification 2, point 7: the application opens no outbound connection."""
    assert re.search(
        r"^networks:\s*\n  intern:\s*\n    internal: true\s*$",
        _ohne_kommentare(compose),
        re.M,
    )


def test_das_caddy_image_ist_festgenagelt(compose):
    pforte = _dienste(compose)["pforte"]
    image = re.search(r"image:\s*caddy:(\S+)", pforte)

    assert image is not None
    assert re.fullmatch(r"\d+\.\d+\.\d+-alpine", image.group(1))


def test_das_caddyfile_sperrt_und_leitet_an_den_alias_weiter():
    caddyfile = _ohne_kommentare((WURZEL / "caddy" / "Caddyfile").read_text("utf-8"))

    assert re.search(r"^\s*admin off\s*$", caddyfile, re.M)
    assert re.search(r"^\s*auto_https off\s*$", caddyfile, re.M)
    assert "{$PFORTE_USER} {$PFORTE_HASH}" in caddyfile
    # `notenverwaltung` resolves to the sidecar itself inside the gate's
    # namespace -- measured, see the comment in the Caddyfile.
    assert re.search(r"^\s*reverse_proxy anwendung:8000\s*$", caddyfile, re.M)
    assert "reverse_proxy notenverwaltung" not in caddyfile


def test_die_vorlage_setzt_den_hash_in_einfache_anfuehrungszeichen():
    """Unquoted, Compose would replace every `$2a`, `$14`, ... with nothing."""
    vorlage = (WURZEL / ".env.example").read_text(encoding="utf-8")

    assert re.search(r"^PFORTE_HASH='\$2a\$", vorlage, re.M)


def test_geheimnisse_und_zustand_bleiben_aus_repository_und_image():
    """On the NAS the working tree holds the state of the sidecar and the gate.

    Both contain credentials: the node key, the password hash.
    """
    git = (WURZEL / ".gitignore").read_text(encoding="utf-8").splitlines()
    docker = (WURZEL / ".dockerignore").read_text(encoding="utf-8").splitlines()

    for eintrag in (".env", "pforte/", "tailscale/"):
        assert eintrag in git, eintrag
    for eintrag in (".env", "pforte", "tailscale"):
        assert eintrag in docker, eintrag
