"""Paramètres de l'application, enregistrés dans %APPDATA%\\Musicotheque\\settings.json."""
import json
import os
import shutil
import sys
from pathlib import Path

APP_NAME = "Musicothèque"
AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".wma"}


def app_dir() -> Path:
    """Dossier du programme (là où se trouve bin/ avec ffmpeg, fpcalc, cyanrip)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    d = Path(base) / "Musicotheque"
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup_path():
    """Ajoute bin/ au PATH pour trouver ffmpeg, fpcalc et cyanrip."""
    b = app_dir() / "bin"
    if b.is_dir():
        os.environ["PATH"] = str(b) + os.pathsep + os.environ.get("PATH", "")
    fp = shutil.which("fpcalc")
    if fp:
        os.environ.setdefault("FPCALC", fp)


def tool(name: str) -> str | None:
    return shutil.which(name)


DEFAULTS = {
    "library_root": str(Path.home() / "Music" / "Musicothèque"),
    "watched_folders": [],
    "acoustid_key": "",
    "rename_pattern": "{artist}/{album}/{track:02d} - {title}",
    "mp3_bitrate": 320,
    "dup_delete": True,      # supprimer automatiquement les doublons (le meilleur exemplaire est gardé)
    "convert_wav": True,     # transformer les WAV / AIFF / OGG / WMA en MP3 lors du rangement
    "remote_enabled": True,  # télécommande depuis un téléphone (version Raspberry Pi / tactile)
    "remote_port": 8080,
    "remote_pin": "",
    "remote_tokens": [],
    "volume": 0.8,
    "eq_preset": "Plat",
    "eq_gains": [0.0] * 10,
    "balance": 0.0,
    "surround": 0.0,
    "reverb_mix": 0.0,
    "reverb_room": 0.5,
    "bass_boost": 0.0,
    "ambiance": "Aucune",
    "shuffle": False,
    "repeat": "none",
    "cd_drive": "",
}


class Settings(dict):
    def __init__(self):
        super().__init__(DEFAULTS)
        self.path = data_dir() / "settings.json"
        try:
            self.update(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    def save(self):
        self.path.write_text(json.dumps(self, indent=2, ensure_ascii=False), encoding="utf-8")


settings = Settings()
