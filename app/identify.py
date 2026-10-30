"""Reconnaissance des morceaux « façon Shazam » :
1) empreinte acoustique (Chromaprint/fpcalc) envoyée à AcoustID -> identifiant MusicBrainz,
2) récupération des infos complètes (album, piste, année, genre) sur MusicBrainz,
3) pochette depuis Cover Art Archive,
4) à défaut, recherche texte MusicBrainz à partir du nom de fichier.
"""
from pathlib import Path
import os
from dataclasses import dataclass

import requests

from .config import APP_NAME, settings
from .tags import read_tags, write_tags, guess_from_filename

try:
    import acoustid
except ImportError:  # pragma: no cover
    acoustid = None
import musicbrainzngs as mb

mb.set_useragent("Musicotheque", "1.0", "https://github.com/")
UA = {"User-Agent": "Musicotheque/1.0"}


@dataclass
class Match:
    score: float
    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    track: int = 0
    disc: int = 0
    year: str = ""
    genre: str = ""
    recording_id: str = ""
    release_id: str = ""
    source: str = ""

    def label(self):
        return f"{self.artist} — {self.title}  [{self.album} {self.year}]  ({int(self.score*100)} %, {self.source})"


def fingerprint_available() -> bool:
    if acoustid is None:
        return False
    from shutil import which
    return bool(os.environ.get("FPCALC") or which("fpcalc"))


def _pick_release(recording: dict, prefer_album: str = ""):
    """Choisit la meilleure parution : album officiel le plus ancien plutôt que compilation."""
    rels = recording.get("release-list", [])
    if not rels:
        return None

    def key(r):
        rg = r.get("release-group", {})
        ptype = rg.get("primary-type", r.get("release-group", {}).get("type", ""))
        secondary = rg.get("secondary-type-list", [])
        is_album = ptype == "Album" and not secondary
        same = prefer_album and r.get("title", "").lower() == prefer_album.lower()
        return (not same, not is_album, r.get("status") != "Official", r.get("date", "9999") or "9999")
    return sorted(rels, key=key)[0]


def _details(recording_id: str, prefer_album="") -> Match | None:
    try:
        rec = mb.get_recording_by_id(recording_id, includes=["artists", "releases", "tags"],
                                     release_type=["album", "single", "ep", "compilation"])["recording"]
    except Exception:
        return None
    m = Match(score=1.0, recording_id=recording_id, title=rec.get("title", ""),
              artist=rec.get("artist-credit-phrase", ""))
    tags = sorted(rec.get("tag-list", []), key=lambda t: -int(t.get("count", 0)))
    if tags:
        m.genre = tags[0]["name"].title()
    rel = _pick_release(rec, prefer_album)
    if rel:
        m.release_id = rel["id"]
        m.album = rel.get("title", "")
        m.year = (rel.get("date") or "")[:4]
        try:
            full = mb.get_release_by_id(rel["id"], includes=["recordings", "artist-credits"])["release"]
            m.album_artist = full.get("artist-credit-phrase", "")
            for medium in full.get("medium-list", []):
                for t in medium.get("track-list", []):
                    if t.get("recording", {}).get("id") == recording_id:
                        m.track = int(t.get("position", 0) or 0)
                        m.disc = int(medium.get("position", 0) or 0)
        except Exception:
            pass
    return m


def by_fingerprint(path: str, limit=5) -> list[Match]:
    key = settings.get("acoustid_key")
    if not (key and fingerprint_available()):
        return []
    try:
        res = acoustid.match(key, path, meta="recordings releasegroups", parse=False)
    except Exception:
        return []
    out, seen = [], set()
    for r in sorted(res.get("results", []), key=lambda x: -x.get("score", 0)):
        for rec in r.get("recordings", []) or []:
            rid = rec.get("id")
            if rid in seen:
                continue
            seen.add(rid)
            artist = " & ".join(a["name"] for a in rec.get("artists", []))
            out.append(Match(score=r.get("score", 0), title=rec.get("title", ""), artist=artist,
                             recording_id=rid, source="empreinte"))
            if len(out) >= limit:
                return out
    return out


def by_text(artist: str, title: str, limit=5) -> list[Match]:
    if not title:
        return []
    try:
        q = {"recording": title}
        if artist:
            q["artist"] = artist
        res = mb.search_recordings(limit=limit, **q)
    except Exception:
        return []
    out = []
    for rec in res.get("recording-list", []):
        out.append(Match(score=int(rec.get("ext:score", 0)) / 100, title=rec.get("title", ""),
                         artist=rec.get("artist-credit-phrase", ""), recording_id=rec["id"], source="texte"))
    return out


def candidates(path: str) -> list[Match]:
    """Liste de propositions, les meilleures en premier."""
    cur = read_tags(path)
    found = by_fingerprint(path)
    if not found:
        g = guess_from_filename(path)
        found = by_text(cur.artist or g.get("artist", ""), cur.title or g.get("title", ""))
    return found


def complete(m: Match, prefer_album="") -> Match:
    d = _details(m.recording_id, prefer_album) if m.recording_id else None
    if d:
        d.score, d.source = m.score, m.source
        return d
    return m


def cover_art(release_id: str) -> bytes | None:
    if not release_id:
        return None
    try:
        r = requests.get(f"https://coverartarchive.org/release/{release_id}/front-500",
                         headers=UA, timeout=15)
        if r.ok and r.content[:3] in (b"\xff\xd8\xff", b"\x89PN"):
            return r.content
    except requests.RequestException:
        pass
    return None


def apply_match(path: str, m: Match, overwrite=False, with_cover=True):
    """Complète les tags. overwrite=False : ne remplit que les champs vides."""
    cur = read_tags(path)

    def pick(new, old):
        return new if (overwrite or not old) and new else None
    cover = cover_art(m.release_id) if with_cover and (overwrite or not cur.has_cover) else None
    write_tags(path, title=pick(m.title, cur.title), artist=pick(m.artist, cur.artist),
               album=pick(m.album, cur.album), album_artist=pick(m.album_artist, cur.album_artist),
               track=pick(m.track, cur.track), disc=pick(m.disc, cur.disc),
               year=pick(m.year, cur.year), genre=pick(m.genre, cur.genre), cover=cover,
               mb_recording_id=m.recording_id or None)


def auto_identify(path: str, min_score=0.80, overwrite=False) -> Match | None:
    """Identification automatique : applique la meilleure proposition si elle est sûre."""
    cands = candidates(path)
    if not cands or cands[0].score < min_score:
        return None
    m = complete(cands[0], read_tags(path).album)
    apply_match(path, m, overwrite=overwrite)
    return m


def identify_or_set_aside(path: str, min_score=0.80, overwrite=False, log=None, buffer_base=None):
    """Comme auto_identify, mais ne lève jamais d'erreur, pour que les autres fichiers soient traités :
    - lecture seule : retirée, puis le fichier est complété ;
    - accès refusé impossible à lever : fichier mis de côté, laissé en place ;
    - autre erreur (tags endommagés « not a Frame instance »…) : fichier placé dans le dossier tampon.
    Renvoie (match ou None, texte pour le journal si le fichier a été écarté, sinon None)."""
    from . import setaside
    # vérifié d'abord (et lecture seule retirée) : inutile d'écouter un fichier qu'on ne pourra pas modifier
    why = setaside.check_access(path, on_unlock=(lambda p: log(f"🔓 lecture seule retirée : {Path(p).name}"))
                                if log else None)
    if why is not None:
        setaside.add(path, why, "identification")
        return None, setaside.short_reason(why)
    try:
        m = auto_identify(path, min_score=min_score, overwrite=overwrite)
    except Exception as e:                       # noqa: BLE001 - un fichier ne doit jamais arrêter les autres
        return None, setaside.handle_error(path, e, buffer_base)
    setaside.remove([path])
    return m, None
