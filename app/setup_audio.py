"""Prépare les sorties audio sous Linux (Raspberry Pi, Orange Pi, mini-PC…).

Crée une sortie nommée « Musicotheque_… » par carte son (ALSA) ou par sortie PipeWire
(bureau, enceintes Bluetooth), dans ~/.asoundrc, pour que le logiciel puisse envoyer le son
sur plusieurs sorties en même temps. Les noms lisibles sont enregistrés dans
~/.config/Musicotheque/peripheriques.json.

Utilisation : python3 -m app.setup_audio      (relancer après avoir branché une carte son)
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

from .config import data_dir

PREFIX = "Musicotheque_"
BEGIN, END = "# >>> Musicotheque (généré automatiquement)", "# <<< Musicotheque"

FRIENDLY = {
    "Headphones": "Prise jack (casque / ampli)",
    "vc4hdmi": "HDMI", "vc4hdmi0": "HDMI 1", "vc4hdmi1": "HDMI 2",
    "b1": "HDMI", "HDMI": "HDMI",
}


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:40] or "sortie"


def alsa_cards() -> list[tuple[str, str]]:
    """[(identifiant, nom long)] depuis /proc/asound/cards."""
    return [(cid, name) for _, cid, name in _cards()]


def _cards():
    out = []
    try:
        txt = Path("/proc/asound/cards").read_text()
    except OSError:
        return out
    for m in re.finditer(r"^\s*(\d+)\s+\[(\S+)\s*\]:\s*\S+\s*-\s*(.+)$", txt, re.M):
        out.append((int(m.group(1)), m.group(2), m.group(3).strip()))
    return out


def playback_devices(card_num: int) -> list[tuple[int, str]]:
    """Sorties d'une carte : certaines cartes (Amlogic du Banana Pi M5, Rockchip…) ont la prise
    jack et le HDMI sur deux « devices » d'une même carte."""
    out = []
    try:
        txt = Path("/proc/asound/pcm").read_text()
    except OSError:
        return [(0, "")]
    for ln in txt.splitlines():
        m = re.match(r"^(\d+)-(\d+):\s*([^:]*):\s*([^:]*):(.*)$", ln)
        if m and int(m.group(1)) == card_num and "playback" in m.group(5):
            out.append((int(m.group(2)), (m.group(4).strip() or m.group(3).strip())))
    return out or [(0, "")]


def device_name(dev: int, pcm: str) -> str:
    low = pcm.lower()
    if "hdmi" in low:
        return "HDMI"
    if any(k in low for k in ("headphone", "analog", "codec", "jack", "acodec")):
        return "prise jack"
    if "spdif" in low or "iec958" in low:
        return "S/PDIF"
    return f"sortie {dev + 1}"


def card_label(cid: str, longname: str) -> str:
    if cid in FRIENDLY:
        return FRIENDLY[cid]
    if "hifiberry" in cid.lower() or "hifiberry" in longname.lower():
        return f"HiFiBerry ({longname})"
    if "usb" in longname.lower() or cid.lower().startswith(("device", "usb")):
        return f"USB : {longname}"
    return longname


def pipewire_sinks() -> list[tuple[str, str]]:
    """[(nom du nœud, description)] si PipeWire/PulseAudio tourne (Raspberry Pi OS bureau)."""
    if not shutil.which("pactl"):
        return []
    try:
        info = subprocess.run(["pactl", "info"], capture_output=True, text=True, timeout=5)
        if info.returncode != 0 or "PipeWire" not in info.stdout:
            return []
        txt = subprocess.run(["pactl", "list", "sinks"], capture_output=True, text=True, timeout=5,
                             env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"}).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    sinks = []
    for block in txt.split("Sink #")[1:]:
        name = re.search(r"^\s*Name:\s*(.+)$", block, re.M)
        desc = re.search(r"^\s*Description:\s*(.+)$", block, re.M)
        if name:
            sinks.append((name.group(1).strip(), (desc.group(1).strip() if desc else name.group(1).strip())))
    return sinks


def build_config():
    """Retourne (texte asoundrc, {nom: libellé}, mode)."""
    lines, labels = [BEGIN], {}
    sinks = pipewire_sinks()
    if sinks:
        mode = "pipewire"
        for node, desc in sinks:
            name = PREFIX + _safe(desc)
            labels[name] = desc
            lines += [f'pcm.{name} {{', '    type pipewire', f'    playback_node "{node}"',
                      f'    hint.description "{desc}"', '}']
    else:
        mode = "alsa"
        for num, cid, longname in _cards():
            devs = playback_devices(num)
            for dev, pcm in devs:
                name = PREFIX + _safe(cid) + (f"_{dev}" if len(devs) > 1 else "")
                labels[name] = card_label(cid, longname) + (f" – {device_name(dev, pcm)}" if len(devs) > 1 else "")
                # HDMI du Raspberry Pi : format IEC958 obligatoire -> on passe par le greffon « hdmi »
                slave = f"hdmi:CARD={cid},DEV={dev}" if cid.startswith("vc4hdmi") else f"dmix:CARD={cid},DEV={dev}"
                lines += [f'pcm.{name} {{', '    type plug', f'    slave.pcm "{slave}"',
                          f'    hint.description "{labels[name]}"', '}']
    lines.append(END)
    return "\n".join(lines) + "\n", labels, mode


def install(home: Path | None = None) -> dict:
    home = home or Path.home()
    text, labels, mode = build_config()
    rc = home / ".asoundrc"
    old = rc.read_text() if rc.exists() else ""
    if old and BEGIN not in old and not (home / ".asoundrc.avant_musicotheque").exists():
        (home / ".asoundrc.avant_musicotheque").write_text(old)
    old = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", "", old, flags=re.S)
    rc.write_text(old.rstrip() + ("\n\n" if old.strip() else "") + text)
    (data_dir() / "peripheriques.json").write_text(json.dumps(labels, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"mode": mode, "sorties": labels}


if __name__ == "__main__":
    r = install()
    print(f"Mode : {r['mode']}")
    for k, v in r["sorties"].items():
        print(f"  {v:40s} -> {k}")
    if not r["sorties"]:
        print("Aucune carte son trouvée.")
