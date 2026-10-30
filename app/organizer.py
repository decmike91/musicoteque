"""Rangement automatique d'un emplacement (disque dur, clé USB) :
Artiste / Album (Année) / NN - Titre.ext, détection des doublons, journal d'annulation."""
import hashlib
import json
import os
import re
import shutil
import stat
import time
from dataclasses import dataclass
from pathlib import Path

from .config import data_dir
from .library import iter_audio_files
from .tags import read_tags, guess_from_filename, TrackInfo

WIN_FORBIDDEN = r'[<>:"/\\|?*\x00-\x1f]'
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def clean_name(s: str, maxlen=80) -> str:
    s = re.sub(WIN_FORBIDDEN, "_", str(s)).strip().rstrip(".")
    s = re.sub(r"\s+", " ", s)
    if s.upper() in RESERVED:
        s = "_" + s
    return s[:maxlen].rstrip(" .") or "_"


@dataclass
class Move:
    src: str
    dst: str
    # "déplacer", "incomplet", "déjà rangé", "doublon", "déjà présent", "remplace"
    status: str
    info: TrackInfo | None = None
    convert: bool = False      # WAV -> MP3
    replaces: str = ""         # fichier de moins bonne qualité remplacé dans la destination
    reason: str = ""           # explication (doublon de…)
    base: str = ""             # destination du rangement (son dossier tampon reçoit les fichiers en erreur)


CONVERT_EXTS = {".wav", ".aif", ".aiff", ".ogg", ".oga", ".wma"}   # transformés en MP3 si l'option est cochée
LOSSLESS_EXTS = {".wav", ".aif", ".aiff", ".flac"}


def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\s*[\(\[](official|clip|lyrics?|audio|video|hd|hq|remaster(ed)?[^\)\]]*)[\)\]]", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def song_key(t: TrackInfo):
    """Identité d'un morceau : artiste + titre normalisés (None si inconnus)."""
    a, ti = _norm(t.artist or t.album_artist), _norm(t.title)
    return (a, ti) if a and ti else None


def quality(path: str, bitrate: int = 0, has_cover=False, complete=False) -> tuple:
    """Plus c'est grand, meilleur c'est : sans perte > débit > pochette > infos complètes."""
    lossless = Path(path).suffix.lower() in LOSSLESS_EXTS
    return (1 if lossless else 0, bitrate or 0, 1 if has_cover else 0, 1 if complete else 0)


def target_path(dest_root: Path, t: TrackInfo, pattern: str, ext: str) -> Path:
    artist = t.album_artist or t.artist or "Artiste inconnu"
    if artist.lower() in ("various artists", "artistes divers", "compilation"):
        artist = "Compilations"
    album = t.album or "Titres isolés"
    if t.year and t.album:
        album = f"{album} ({t.year})"
    title = t.title or Path(t.path).stem
    track = t.track or 0
    if t.disc and t.disc > 1:
        title_prefix = f"{t.disc}-"
    else:
        title_prefix = ""
    rel = pattern.format(artist=clean_name(artist), album=clean_name(album), title=clean_name(title),
                         track=track, year=t.year or "", disc=t.disc or 1,
                         track_artist=clean_name(t.artist or artist), genre=clean_name(t.genre or "Divers"))
    parts = [p for p in rel.replace("\\", "/").split("/") if p]
    if not track:  # pas de numéro : enlever le "00 - "
        parts[-1] = re.sub(r"^00\s*-\s*", "", parts[-1])
    elif title_prefix:
        parts[-1] = title_prefix + parts[-1]
    return dest_root.joinpath(*parts).with_suffix(ext.lower())


def quick_hash(path, block=1 << 16) -> str:
    """Empreinte rapide (taille + début + fin) pour repérer les doublons exacts."""
    h = hashlib.md5()
    size = os.path.getsize(path)
    h.update(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(block))
        if size > block * 2:
            f.seek(-block, 2); h.update(f.read(block))
    return h.hexdigest()


def plan(source: str | Path, dest_root: str | Path | None = None,
         pattern="{artist}/{album}/{track:02d} - {title}", use_filename=True,
         progress=None, cancel=lambda: False, dup_mode="delete", convert_wav=True,
         existing=None, same_song=True) -> list[Move]:
    """Prépare le rangement (rien n'est modifié).
    dup_mode : "delete" = doublons supprimés (ou non copiés), "aside" = mis dans _Doublons.
    convert_wav : les WAV/AIFF deviennent des MP3.
    existing : titres déjà présents dans la destination (lignes de la bibliothèque),
               pour ne pas recopier un morceau déjà rangé.
    same_song : un même morceau en plusieurs fichiers (ex. MP3 128 et 320 kbit/s) est un doublon ;
                on garde le meilleur exemplaire."""
    source = Path(source)
    dest_root = Path(dest_root) if dest_root else source / "Musique classée"
    files = list(iter_audio_files(source))
    items, unreadable = [], []
    for i, p in enumerate(files):
        if cancel():
            break
        if progress:
            progress(i + 1, len(files), p)
        try:
            t = read_tags(p)
            if use_filename and (not t.title or not t.artist):
                g = guess_from_filename(p)
                t.title = t.title or g.get("title", "")
                t.artist = t.artist or g.get("artist", "")
                t.track = t.track or g.get("track", 0)
            h = quick_hash(p)
        except Exception as e:       # fichier illisible : signalé, puis on continue
            unreadable.append(_error_move(p, None, e, dest_root))
            continue
        items.append({"path": p, "t": t, "hash": h, "key": song_key(t),
                      "q": quality(p, t.bitrate, t.has_cover, not t.is_incomplete)})

    # --- doublons dans la source : on garde le meilleur exemplaire de chaque groupe
    dup_of = {}
    groups = {}
    for it in items:
        groups.setdefault(("h", it["hash"]), []).append(it)
    if same_song:
        for it in items:
            if it["key"]:
                groups.setdefault(("k", it["key"]), []).append(it)
    for kind, members in groups.items():
        if len(members) < 2:
            continue
        if kind[0] == "k":   # même titre : durées proches seulement (sinon : autre version, live…)
            members = sorted(members, key=lambda x: x["t"].duration)
            clusters, cur = [], [members[0]]
            for m in members[1:]:
                if abs(m["t"].duration - cur[-1]["t"].duration) <= 3:
                    cur.append(m)
                else:
                    clusters.append(cur); cur = [m]
            clusters.append(cur)
        else:
            clusters = [members]
        for c in clusters:
            c = [m for m in c if m["path"] not in dup_of]
            if len(c) < 2:
                continue
            if kind[0] == "k":
                # même morceau sur deux albums différents (album + best-of) : on garde les deux,
                # pour ne pas rendre un album incomplet. Un fichier sans album est un doublon du meilleur.
                by_album = {}
                for m in c:
                    by_album.setdefault(_norm(m["t"].album), []).append(m)
                named = [g for a, g in by_album.items() if a]
                loose = by_album.get("", [])
                subgroups = named or [loose]
                if named and loose:
                    best_named = max((m for g in named for m in g), key=lambda m: m["q"])
                    for m in loose:
                        dup_of[m["path"]] = best_named["path"]
            else:
                subgroups = [c]
            for g in subgroups:
                if len(g) < 2:
                    continue
                best = max(g, key=lambda m: m["q"])
                for m in g:
                    if m is not best:
                        dup_of[m["path"]] = best["path"]

    # --- morceaux déjà présents dans la destination
    ex_index = {}
    for r in existing or []:
        rp = str(r["path"])
        if rp.startswith(str(dest_root)) and not rp.startswith(str(source) + os.sep) and os.path.exists(rp):
            ti = TrackInfo(path=r["path"], title=r.get("title") or "", artist=r.get("artist") or "",
                           album_artist=r.get("album_artist") or "", album=r.get("album") or "",
                           duration=r.get("duration") or 0)
            k = song_key(ti)
            if k:
                ex_index.setdefault(k, []).append((r, quality(r["path"], r.get("bitrate") or 0, r.get("has_cover"),
                                                               bool(r.get("album")))))

    moves, taken = list(unreadable), set()
    replaced = set()
    for it in items:
        try:
            _plan_item(it, moves, taken, replaced, dup_of, ex_index, dest_root, pattern, dup_mode, convert_wav)
        except Exception as e:
            moves.append(_error_move(it["path"], it["t"], e, dest_root))
    for m in moves:
        m.base = str(dest_root)
    return moves


BUFFER_STATUS = "à vérifier"


def _error_move(p, t, e, dest_root):
    """Accès refusé : laissé en place ; autre erreur (tags endommagés…) : ira dans le dossier tampon."""
    from .setaside import is_access_error, buffer_dir
    if is_access_error(e):
        return Move(p, "", "erreur", t, reason=friendly_error(e))
    return Move(p, str(buffer_dir(dest_root) / Path(p).name), BUFFER_STATUS, t, reason=friendly_error(e))


def _plan_item(it, moves, taken, replaced, dup_of, ex_index, dest_root, pattern, dup_mode, convert_wav):
    """Décide du sort d'un fichier (ajoute un Move à `moves`)."""
    p, t = it["path"], it["t"]
    conv = convert_wav and Path(p).suffix.lower() in CONVERT_EXTS
    ext = ".mp3" if conv else Path(p).suffix
    if p in dup_of:
        dst = "" if dup_mode == "delete" else str(_unique(dest_root / "_Doublons" / clean_name(Path(p).name), taken))
        moves.append(Move(p, dst, "doublon", t, reason=f"doublon de « {Path(dup_of[p]).name} »"))
        return
    replaces = ""
    if it["key"] in ex_index:
        alb = _norm(t.album)
        match = [(r, q) for r, q in ex_index[it["key"]]
                 if abs((r.get("duration") or 0) - t.duration) <= 3 and r["path"] not in replaced
                 and (not alb or not _norm(r.get("album") or "") or _norm(r.get("album") or "") == alb)]
        if match:
            r, q = max(match, key=lambda x: x[1])
            if q >= it["q"]:
                dst = "" if dup_mode == "delete" else str(_unique(dest_root / "_Doublons" / clean_name(Path(p).name), taken))
                moves.append(Move(p, dst, "déjà présent", t, reason=f"déjà dans la bibliothèque : {Path(r['path']).name}"))
                return
            replaces = r["path"]; replaced.add(replaces)
    dst = target_path(dest_root, t, pattern, ext)
    if not conv and dst.exists() and str(Path(p).resolve()).lower() == str(dst.resolve()).lower():
        moves.append(Move(p, p, "déjà rangé", t)); taken.add(str(dst).lower()); return
    if replaces and str(Path(replaces).resolve()).lower() == str(dst.resolve()).lower():
        taken.add(str(dst).lower())            # la place est libérée par le fichier remplacé
    else:
        dst = _unique(dst, taken)
    status = "remplace" if replaces else ("incomplet" if t.is_incomplete else "déplacer")
    moves.append(Move(p, str(dst), status, t, convert=conv, replaces=replaces,
                      reason=f"meilleure qualité que {Path(replaces).name}" if replaces else ""))


def make_writable(path):
    """Retire l'attribut « lecture seule » (fréquent sur les fichiers copiés d'un CD)."""
    try:
        os.chmod(path, os.stat(path).st_mode | stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def retry_writable(fn, path, *args):
    """Exécute fn ; en cas d'accès refusé, retire la lecture seule et réessaie une fois."""
    try:
        return fn(path, *args)
    except PermissionError:
        make_writable(path)
        return fn(path, *args)


def friendly_error(e: BaseException, short=False) -> str:
    """Message compréhensible pour le journal."""
    txt = str(e)
    errno_ = getattr(e, "errno", None) or getattr(getattr(e, "__context__", None), "errno", None)
    if isinstance(e, PermissionError) or errno_ in (1, 13) or "denied" in txt.lower() or "refusé" in txt.lower() \
            or "[WinError 5]" in txt or "[WinError 32]" in txt:
        if short:
            return "accès refusé"
        return ("accès refusé (fichier en lecture seule, ouvert dans un autre programme, "
                "ou dossier protégé) — fichier laissé en place")
    if "[WinError 2]" in txt or isinstance(e, FileNotFoundError):
        return "fichier introuvable (déplacé ou supprimé entre-temps)"
    if "No space" in txt or "[WinError 112]" in txt:
        return "disque plein"
    if "not a Frame instance" in txt or "can't sync" in txt.lower() or type(e).__module__.startswith("mutagen") \
            or "header not found" in txt.lower():
        return f"informations du fichier (tags) endommagées ou format non reconnu : {txt[-120:]}"
    return txt[-200:] or type(e).__name__


def trash(path) -> str:
    """Envoie à la corbeille (récupérable) ; à défaut, supprime."""
    try:
        from send2trash import send2trash
        try:
            send2trash(str(path))
        except Exception:
            make_writable(path)
            send2trash(str(path))
        return "corbeille"
    except ImportError:
        pass
    except Exception:
        pass
    retry_writable(os.remove, path)
    return "supprimé"


def mp3_bitrate_for(src, wanted=320) -> int:
    """WAV/AIFF : qualité demandée. OGG (déjà compressé) : un peu au-dessus de la qualité
    d'origine (au moins 192 kbit/s), sans dépasser la qualité demandée — inutile de gonfler le fichier."""
    if Path(src).suffix.lower() in LOSSLESS_EXTS:
        return int(wanted)
    br = read_tags(src).bitrate or 192
    for std in (192, 224, 256, 320):
        if std >= br + 32:
            return min(int(wanted), std)
    return int(wanted)


def convert_to_mp3(src, dst, bitrate=320, info: TrackInfo | None = None):
    """WAV / AIFF / OGG / WMA -> MP3 (LAME) en gardant les informations et la pochette.
    Un WMA protégé (DRM) ne peut pas être converti : il est laissé tel quel."""
    import subprocess
    import sys
    from .tags import write_tags
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    tmp = str(Path(dst).with_suffix(".tmp.mp3"))
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(src), "-map", "0:a:0", "-map_metadata", "0",
           "-codec:a", "libmp3lame", "-b:a", f"{int(bitrate)}k", "-id3v2_version", "3", tmp]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       creationflags=0x08000000 if sys.platform == "win32" else 0)
    if r.returncode != 0 or not os.path.exists(tmp):
        if os.path.exists(tmp):
            os.remove(tmp)
        err = r.stderr.strip()[-200:]
        if "drm" in err.lower() or "protected" in err.lower():
            err = "fichier protégé contre la copie (DRM), laissé tel quel"
        raise OSError(f"conversion impossible : {err}")
    os.replace(tmp, dst)
    from .tags import read_cover
    cover = read_cover(src)
    if cover and not read_tags(dst).has_cover:
        write_tags(dst, cover=cover)
    if info:
        cur = read_tags(dst)
        write_tags(dst, title=info.title if not cur.title else None, artist=info.artist if not cur.artist else None,
                   album=info.album if not cur.album else None, album_artist=info.album_artist or None,
                   track=info.track or None, disc=info.disc or None, year=info.year or None, genre=info.genre or None)


def _unique(dst: Path, taken: set) -> Path:
    cand, n = dst, 2
    while str(cand).lower() in taken or cand.exists():
        cand = dst.with_name(f"{dst.stem} ({n}){dst.suffix}"); n += 1
    taken.add(str(cand).lower())
    return cand


def move_file(src, dst) -> bool:
    """Déplace ; renvoie False si le fichier a pu être copié mais pas retiré de son ancien
    emplacement (original verrouillé ou support en lecture seule)."""
    try:
        os.rename(src, dst)
        return True
    except PermissionError:
        make_writable(src)
        try:
            os.rename(src, dst)
            return True
        except OSError:
            pass
    except OSError:
        pass                     # autre disque : copie puis suppression
    shutil.copy2(src, dst)
    try:
        retry_writable(os.remove, src)
        return True
    except OSError:
        return False


def execute(moves: list[Move], copy=False, library=None, progress=None, cancel=lambda: False,
            write_guessed=True, bitrate=320, log_fn=None) -> Path:
    """Applique le plan, fichier par fichier : une erreur sur un fichier (accès refusé…)
    est notée, puis on passe au suivant. Retourne le chemin du journal (pour annuler).
    copy=True : les originaux ne sont jamais modifiés ni supprimés."""
    say = log_fn or (lambda m: None)
    log, errors = [], []
    todo = [m for m in moves if m.src != m.dst or m.convert]
    stats = {"rangés": 0, "convertis": 0, "doublons supprimés": 0, "remplacés": 0}
    for i, m in enumerate(todo):
        if cancel():
            say("Arrêt demandé.")
            break
        entry = {"src": m.src, "dst": m.dst, "copy": copy, "status": m.status}
        try:
            _execute_one(m, entry, copy, library, write_guessed, bitrate, say, stats)
        except Exception as e:
            from .setaside import is_access_error, to_buffer, BUFFER_NAME
            entry["error"] = friendly_error(e)
            new = None
            if not is_access_error(e) and m.status != "erreur" and os.path.exists(m.src):
                new = to_buffer(m.src, entry["error"], m.base or None, copy=copy)
            if new:
                entry["buffer"] = new
                stats["dossier tampon"] = stats.get("dossier tampon", 0) + 1
                _lib(library, "remove", m.src)
                say(f"📦 {Path(m.src).name} → « {BUFFER_NAME} » : {entry['error']}")
            else:
                errors.append((m.src, entry["error"]))
                say(f"⚠ {Path(m.src).name} : {entry['error']}")
        log.append(entry)
        if progress:
            progress(i + 1, len(todo), m.dst or m.src)
    if not copy:
        for root in {str(Path(e["src"]).parent) for e in log if "error" not in e}:
            remove_empty_dirs(root)
    parts = [f"{v} {k}" for k, v in stats.items() if v]
    if errors:
        parts.append(f"{len(errors)} fichier(s) non traités (laissés en place)")
    say("Bilan : " + (", ".join(parts) if parts else "rien à faire."))
    if errors:
        say("Fichiers non traités :")
        for src, why in errors[:30]:
            say(f"   • {src} — {why}")
        if len(errors) > 30:
            say(f"   … et {len(errors) - 30} autres (voir le journal)")
    lp = data_dir() / f"rangement_{time.strftime('%Y%m%d_%H%M%S')}.json"
    try:
        lp.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return lp


def _lib(library, fn, *args):
    """Mise à jour de la bibliothèque : ne doit jamais interrompre le rangement."""
    if library is None:
        return
    try:
        getattr(library, fn)(*args)
    except Exception:
        pass


def _upsert(library, path):
    """Ajout à la bibliothèque après rangement : un fichier aux infos abîmées ne doit rien interrompre."""
    if library is None:
        return
    try:
        library.upsert(read_tags(path))
    except Exception:
        pass


def _execute_one(m: Move, entry, copy, library, write_guessed, bitrate, say, stats):
    from .tags import write_tags
    if m.status == "erreur":                      # déjà illisible à l'analyse
        raise OSError(m.reason)
    if m.status == BUFFER_STATUS:                 # erreur à l'analyse (tags endommagés…) : dossier tampon
        from .setaside import to_buffer, BUFFER_NAME
        new = to_buffer(m.src, m.reason, m.base or None, copy=copy)
        if not new:
            raise OSError(f"impossible de le placer dans « {BUFFER_NAME} » ({m.reason})")
        entry["buffer"] = new
        _lib(library, "remove", m.src)
        stats["dossier tampon"] = stats.get("dossier tampon", 0) + 1
        say(f"📦 {Path(m.src).name} → « {BUFFER_NAME} » : {m.reason}")
        return
    if m.status in ("doublon", "déjà présent") and not m.dst:
        # doublon à supprimer : jamais dans le support d'origine en mode copie
        if copy:
            entry["skipped"] = True
            return
        entry["trashed"] = [m.src, trash(m.src)]
        _lib(library, "remove", m.src)
        stats["doublons supprimés"] += 1
        say(f"🗑 {Path(m.src).name} ({m.reason})")
        return
    if m.replaces and os.path.exists(m.replaces):
        entry["replaced"] = [m.replaces, trash(m.replaces)]   # échec -> erreur, le nouveau n'est pas placé
        _lib(library, "remove", m.replaces)
        stats["remplacés"] += 1
        say(f"↻ {Path(m.replaces).name} remplacé ({m.reason})")
    Path(m.dst).parent.mkdir(parents=True, exist_ok=True)
    if m.convert:
        convert_to_mp3(m.src, m.dst, mp3_bitrate_for(m.src, bitrate), m.info)
        entry["convert"] = True
        stats["convertis"] += 1
        say(f"🎵 {Path(m.src).name} → MP3 ({read_tags(m.dst).bitrate} kbit/s)")
        if not copy:
            try:
                entry["trashed"] = [m.src, trash(m.src)]
                _lib(library, "remove", m.src)
            except Exception as e:
                say(f"⚠ {Path(m.src).name} : converti, mais l'original n'a pas pu être retiré ({friendly_error(e, True)})")
        _upsert(library, m.dst)
    elif copy:
        shutil.copy2(m.src, m.dst)
        _upsert(library, m.dst)
    else:
        if move_file(m.src, m.dst):
            _lib(library, "rename_path", m.src, m.dst)   # garde écoutes et playlists
        else:
            entry["copied_only"] = True
            say(f"⚠ {Path(m.src).name} : copié dans la bibliothèque, mais l'original n'a pas pu être retiré "
                "(accès refusé)")
        _upsert(library, m.dst)
    if write_guessed and m.info and m.status not in ("doublon", "déjà présent"):
        try:
            cur = read_tags(m.dst)
            if (not cur.title and m.info.title) or (not cur.artist and m.info.artist):
                make_writable(m.dst)
                write_tags(m.dst, title=None if cur.title else m.info.title,
                           artist=None if cur.artist else m.info.artist,
                           track=None if cur.track else (m.info.track or None))
                _upsert(library, m.dst)
        except Exception as e:     # le fichier est rangé ; seules les infos n'ont pas pu être écrites
            say(f"ℹ {Path(m.dst).name} : rangé, mais infos non enregistrées ({friendly_error(e, True)})")
    stats["rangés"] += 1


def undo(log_path, library=None) -> int:
    n = 0
    for e in reversed(json.loads(Path(log_path).read_text(encoding="utf-8"))):
        if e.get("buffer"):                       # placé dans le dossier tampon : on le remet
            e = dict(e, dst=e["buffer"])
            e.pop("error", None); e.pop("convert", None)
        if "error" in e or e.get("skipped") or not e.get("dst") or not os.path.exists(e["dst"]):
            continue      # (les fichiers supprimés se récupèrent dans la corbeille)
        try:
            if e.get("copy") or e.get("convert") or e.get("copied_only"):
                retry_writable(os.remove, e["dst"])
            else:
                Path(e["src"]).parent.mkdir(parents=True, exist_ok=True)
                move_file(e["dst"], e["src"])
                _lib(library, "rename_path", e["dst"], e["src"])
            remove_empty_dirs(str(Path(e["dst"]).parent))
            n += 1
        except Exception:
            continue          # un fichier bloqué n'empêche pas de remettre les autres
    return n


def remove_empty_dirs(start: str):
    p = Path(start)
    while p.exists() and p.is_dir() and p.parent != p:
        try:
            leftovers = [x for x in p.iterdir() if x.name.lower() not in ("thumbs.db", "desktop.ini", ".ds_store")]
            if leftovers:
                return
            for x in p.iterdir():
                x.unlink()
            p.rmdir()
        except OSError:
            return
        p = p.parent
