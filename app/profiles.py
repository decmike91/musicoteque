"""Profils audio personnalisés (égaliseur, ambiance, effets, audiogramme), enregistrés dans
%APPDATA%\\Musicotheque\\profils\\<nom>.json — un fichier par profil, facile à copier ou partager."""
import copy
import json
import re
from pathlib import Path

from .config import data_dir

# Fréquences d'un audiogramme standard (Hz)
AUDIOGRAM_FREQS = [125, 250, 500, 1000, 2000, 3000, 4000, 6000, 8000]
AUDIOGRAM_LABELS = ["125", "250", "500", "1k", "2k", "3k", "4k", "6k", "8k"]

DEFAULT_AUDIOGRAM = {
    "enabled": False,
    "left": [0] * len(AUDIOGRAM_FREQS),    # perte auditive en dB HL, oreille gauche
    "right": [0] * len(AUDIOGRAM_FREQS),   # oreille droite
    "strength": 0.5,                       # 0,5 = règle du demi-gain (correction classique)
    "max_gain": 25,                        # correction maximale en dB
}

DEFAULT_PROFILE = {
    "eq_enabled": True,
    "eq_preset": "Plat",
    "eq_gains": [0.0] * 10,
    "ambiance": "Aucune",
    "bass": 0,
    "surround": 0.0,
    "reverb_mix": 0.0,
    "reverb_room": 0.5,
    "balance": 0.0,
    "audiogram": DEFAULT_AUDIOGRAM,
}

BUILTIN = {
    "Par défaut": {},
    "Soirée": {"eq_preset": "Électro", "eq_gains": [6, 5, 1, 0, -2, 2, 1, 1, 4, 5], "ambiance": "Club",
               "bass": 4, "surround": 0.4, "reverb_mix": 0.22, "reverb_room": 0.45},
    "Écoute douce (nuit)": {"eq_preset": "Voix", "eq_gains": [-3, -2, -1, 1, 3, 4, 4, 3, 1, -1]},
    "Concert": {"eq_preset": "Rock", "eq_gains": [5, 4, 2, -1, -2, -1, 2, 3, 4, 4],
                "ambiance": "Salle de concert", "surround": 0.5, "reverb_mix": 0.3, "reverb_room": 0.75},
}


def normalize(p: dict | None) -> dict:
    """Complète un profil avec les valeurs par défaut (profils anciens ou incomplets)."""
    out = copy.deepcopy(DEFAULT_PROFILE)
    for k, v in (p or {}).items():
        if k == "audiogram" and isinstance(v, dict):
            out["audiogram"].update(copy.deepcopy(v))
        elif k in out:
            out[k] = copy.deepcopy(v)
    ag = out["audiogram"]
    for ear in ("left", "right"):
        vals = list(ag[ear])[: len(AUDIOGRAM_FREQS)]
        ag[ear] = vals + [0] * (len(AUDIOGRAM_FREQS) - len(vals))
    out["eq_gains"] = (list(out["eq_gains"]) + [0.0] * 10)[:10]
    return out


def profiles_dir() -> Path:
    d = data_dir() / "profils"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file(name: str) -> Path:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip() or "profil"
    return profiles_dir() / f"{safe}.json"


def list_profiles() -> list[str]:
    names = list(BUILTIN)
    for f in sorted(profiles_dir().glob("*.json")):
        try:
            n = json.loads(f.read_text(encoding="utf-8")).get("name", f.stem)
        except (OSError, ValueError):
            continue
        if n not in names:
            names.append(n)
    return names


def is_builtin(name: str) -> bool:
    return name in BUILTIN and not _file(name).exists()


def load_profile(name: str) -> dict:
    f = _file(name)
    if f.exists():
        try:
            return normalize(json.loads(f.read_text(encoding="utf-8")).get("settings"))
        except (OSError, ValueError):
            pass
    return normalize(BUILTIN.get(name, {}))


def save_profile(name: str, profile: dict) -> Path:
    f = _file(name)
    f.write_text(json.dumps({"name": name, "settings": normalize(profile)}, indent=2, ensure_ascii=False),
                 encoding="utf-8")
    return f


def delete_profile(name: str) -> bool:
    f = _file(name)
    if f.exists():
        f.unlink()
        return True
    return False


def export_profile(name: str, profile: dict, dest: str | Path):
    Path(dest).write_text(json.dumps({"name": name, "settings": normalize(profile)}, indent=2, ensure_ascii=False),
                          encoding="utf-8")


def import_profile(src: str | Path) -> str:
    data = json.loads(Path(src).read_text(encoding="utf-8"))
    name = data.get("name") or Path(src).stem
    save_profile(name, data.get("settings", data))
    return name


# ------------------------------------------------------------------ correction auditive
def audiogram_gains(ag: dict) -> tuple[list[float], list[float]]:
    """Gains de correction (dB) par fréquence, pour chaque oreille.
    gain = force × perte, plafonné ; on retire ensuite le gain commun aux deux oreilles
    (il équivaut à monter le volume) pour garder de la marge et éviter la saturation."""
    s, cap = float(ag.get("strength", 0.5)), float(ag.get("max_gain", 25))
    gl = [min(cap, max(0.0, s * float(v))) for v in ag["left"]]
    gr = [min(cap, max(0.0, s * float(v))) for v in ag["right"]]
    common = min(gl + gr)
    return [g - common for g in gl], [g - common for g in gr]
