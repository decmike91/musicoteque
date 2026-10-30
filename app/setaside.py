"""Fichiers « mis de côté » : ceux qu'on n'a pas pu identifier ou compléter (accès refusé, fichier
ouvert dans un autre programme, illisible…). Ils sont sautés sans arrêter le traitement, et notés
dans mis_de_cote.json pour pouvoir les retrouver et réessayer plus tard."""
import json
import os
import threading
import time
from pathlib import Path

from .config import data_dir

_lock = threading.Lock()


def _file() -> Path:
    return data_dir() / "mis_de_cote.json"


def load() -> list[dict]:
    try:
        items = json.loads(_file().read_text(encoding="utf-8"))
        return [i for i in items if isinstance(i, dict) and i.get("path")]
    except (OSError, ValueError):
        return []


def _save(items):
    try:
        tmp = _file().with_suffix(".tmp")
        tmp.write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, _file())
    except OSError:
        pass


def short_reason(reason: str) -> str:
    reason = (reason or "").replace(" — fichier laissé en place", "")
    if reason.startswith("accès refusé ("):          # « accès refusé (a, b, ou c) » -> plus lisible dans une liste
        reason = "accès refusé : " + reason[len("accès refusé ("):].rstrip(")")
    return reason


def add(path, reason, step="identification"):
    path = str(path)
    reason = short_reason(reason)
    with _lock:
        items = [i for i in load() if i["path"] != path]
        items.append({"path": path, "reason": reason, "step": step, "date": time.strftime("%Y-%m-%d %H:%M")})
        _save(items)


def remove(paths):
    paths = {str(p) for p in paths}
    with _lock:
        items = load()
        kept = [i for i in items if i["path"] not in paths]
        if len(kept) != len(items):
            _save(kept)


def clear():
    with _lock:
        _save([])


def count() -> int:
    return len(load())


def paths() -> list[str]:
    return [i["path"] for i in load()]


UNLOCK_FAILED = ("accès refusé : la lecture seule n'a pas pu être retirée (droits insuffisants, fichier protégé "
                 "ou ouvert dans un autre programme, clé USB verrouillée)")
UNREADABLE = "illisible : accès refusé (droits insuffisants ou fichier ouvert dans un autre programme)"


def check_access(path, on_unlock=None) -> str | None:
    """None si le fichier peut être lu ET modifié ; sinon la raison, en clair.
    Un fichier en lecture seule est d'abord déverrouillé (attribut retiré), puis revérifié ;
    on_unlock(path) est appelé quand ce déverrouillage a réussi. Le contenu n'est jamais modifié."""
    from .organizer import friendly_error, make_writable
    p = str(path)
    if not os.path.exists(p):
        return "fichier introuvable (déplacé ou supprimé entre-temps)"
    try:
        with open(p, "rb") as f:
            f.read(16)
    except PermissionError:
        return UNREADABLE
    except OSError as e:
        return friendly_error(e)
    try:
        with open(p, "r+b"):
            return None
    except PermissionError:
        pass
    except OSError as e:
        return friendly_error(e)
    # accès en écriture refusé : on retire la lecture seule, puis on réessaie
    was_ro = is_read_only(p)
    make_writable(p)
    try:
        with open(p, "r+b"):
            pass
    except PermissionError:
        return UNLOCK_FAILED if was_ro else friendly_error(PermissionError(13, "denied"))
    except OSError as e:
        return friendly_error(e)
    if on_unlock:
        on_unlock(p)
    return None


def is_read_only(path) -> bool:
    import stat
    try:
        return not (os.stat(path).st_mode & stat.S_IWRITE)
    except OSError:
        return False


# ------------------------------------------------------------------ dossier tampon
BUFFER_NAME = "_Fichiers à vérifier"


def buffer_dir(base=None) -> Path:
    """Dossier tampon : là où vont les fichiers qui provoquent une erreur (tags endommagés…)."""
    if not base:
        from .config import settings
        base = settings["library_root"]
    return Path(base) / BUFFER_NAME


def is_access_error(e: BaseException) -> bool:
    """Accès refusé / fichier verrouillé : ces fichiers restent en place (ils ne pourraient pas être déplacés)."""
    errno_ = getattr(e, "errno", None) or getattr(getattr(e, "__context__", None), "errno", None)
    txt = str(e)
    return (isinstance(e, PermissionError) or errno_ in (1, 13) or "denied" in txt.lower()
            or "refusé" in txt.lower() or "[WinError 5]" in txt or "[WinError 32]" in txt)


def to_buffer(path, reason, base=None, copy=False) -> str | None:
    """Range le fichier dans le dossier tampon (nom rendu unique) et note la raison dans _raisons.txt.
    Renvoie le nouveau chemin, ou None si le fichier n'a pas pu y être placé (il reste alors en place)."""
    import shutil
    from .organizer import move_file
    src = Path(path)
    dest_dir = buffer_dir(base)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dst = dest_dir / src.name
        n = 2
        while dst.exists():
            dst = dest_dir / f"{src.stem} ({n}){src.suffix}"
            n += 1
        if copy:
            shutil.copy2(src, dst)
        elif not move_file(str(src), str(dst)):
            # copié mais l'original n'a pas pu être retiré : on garde la copie, l'original reste noté
            pass
    except OSError:
        return None
    reason = short_reason(reason)
    try:
        with open(dest_dir / "_raisons.txt", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M')}  {dst.name}\n    origine : {src}\n    raison  : {reason}\n\n")
    except OSError:
        pass
    with _lock:
        items = [i for i in load() if i["path"] not in (str(src), str(dst))]
        items.append({"path": str(dst), "origin": str(src), "reason": reason, "step": "tampon",
                      "date": time.strftime("%Y-%m-%d %H:%M")})
        _save(items)
    return str(dst)


def handle_error(path, e, base=None, step="identification", copy=False):
    """Erreur sur un fichier : accès refusé -> mis de côté sur place ; autre erreur -> dossier tampon.
    Renvoie le texte à afficher dans le journal."""
    from .organizer import friendly_error
    why = friendly_error(e)
    if not is_access_error(e):
        new = to_buffer(path, why, base, copy=copy)
        if new:
            return f"placé dans « {BUFFER_NAME} » ({Path(new).parent}) — {short_reason(why)}"
    add(path, why, step)
    return short_reason(why)


def log_line(path, why) -> str:
    """Ligne de journal pour un fichier écarté (dossier tampon ou mis de côté)."""
    name = Path(path).name
    return f"📦 {name} {why}" if why.startswith("placé dans") else f"⏸ mis de côté : {name} — {why}"


def matching(paths) -> list[dict]:
    """Éléments de la liste qui concernent ces fichiers (chemin actuel ou d'origine, s'ils sont dans le tampon)."""
    paths = {str(p) for p in paths}
    return [i for i in load() if i["path"] in paths or i.get("origin") in paths]
