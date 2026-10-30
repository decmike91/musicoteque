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
