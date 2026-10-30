"""Réparation automatique des tags MP3 endommagés (« not a Frame instance », en-tête ID3 illisible…).

Principe, sans jamais toucher au son :
  1. on récupère tout ce qui reste lisible : cadres ID3v2 un par un, tag ID3v1 en fin de fichier
     (rien n'est inventé : les infos manquantes restent vides pour que l'identification les complète) ;
  2. on retire l'en-tête ID3v2 abîmé (il est placé avant le son, on le coupe octet par octet) ;
  3. on écrit des tags neufs et propres avec les informations récupérées ;
  4. on vérifie que la partie audio est identique, octet pour octet, à celle d'origine.
     Sinon, le fichier d'origine est remis tel quel et la réparation est déclarée impossible.
"""
import hashlib
import os
from pathlib import Path

ID3_TEXT = {"TIT2": "title", "TPE1": "artist", "TALB": "album", "TPE2": "album_artist",
            "TCON": "genre", "TRCK": "track", "TPOS": "disc", "TDRC": "year", "TYER": "year"}


def can_repair(path) -> bool:
    return str(path).lower().endswith(".mp3")


def _syncsafe(b: bytes) -> int:
    return (b[0] & 0x7F) << 21 | (b[1] & 0x7F) << 14 | (b[2] & 0x7F) << 7 | (b[3] & 0x7F)


_BITRATES = {  # (version MPEG 1 ?, couche) -> kbit/s selon l'index 1..14
    (True, 1): [32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448],
    (True, 2): [32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384],
    (True, 3): [32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    (False, 1): [32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256],
    (False, 2): [8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
    (False, 3): [8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}
_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def _frame_len(d: bytes, i: int) -> int:
    """Longueur de la trame audio MPEG qui commence en i, ou 0 si ce n'est pas un début de trame valide."""
    if i + 4 > len(d) or d[i] != 0xFF or (d[i + 1] & 0xE0) != 0xE0:
        return 0
    ver, layer_bits = (d[i + 1] >> 3) & 3, (d[i + 1] >> 1) & 3
    bri, sri, pad = d[i + 2] >> 4, (d[i + 2] >> 2) & 3, (d[i + 2] >> 1) & 1
    if ver == 1 or layer_bits == 0 or bri in (0, 15) or sri == 3:
        return 0
    layer = 4 - layer_bits
    mpeg1 = ver == 3
    br = _BITRATES[(mpeg1, layer)][bri - 1] * 1000
    sr = _RATES[ver][sri]
    if layer == 1:
        return (12 * br // sr + pad) * 4
    return (144 if (layer == 2 or mpeg1) else 72) * br // sr + pad


def _audio_starts_at(d: bytes, i: int, frames=3) -> bool:
    """Vrai si au moins `frames` trames audio valides se suivent à partir de i (ou si le son finit avant)."""
    for _ in range(frames):
        if i >= len(d) or d[i:i + 3] == b"TAG":
            return True
        n = _frame_len(d, i)
        if n < 24:
            return False
        i += n
    return True


def _id3v2_end(data: bytes) -> int | None:
    """Position du début du son, après tous les en-têtes ID3v2 (même abîmés). None si incertaine."""
    pos = 0
    while data[pos:pos + 3] == b"ID3" and len(data) >= pos + 10:
        flags = data[pos + 5]
        size = _syncsafe(data[pos + 6:pos + 10])
        declared = pos + 10 + size + (10 if flags & 0x10 else 0)
        nxt = declared
        while nxt < len(data) and data[nxt] == 0:          # bourrage de zéros laissé par certains logiciels
            nxt += 1
        if nxt <= len(data) and (data[nxt:nxt + 3] == b"ID3" or _audio_starts_at(data, nxt)):
            pos = nxt
            continue
        # taille d'en-tête fausse : on cherche les vraies trames audio
        found = next((i for i in range(pos + 10, min(len(data), pos + 10 + 4 * 1024 * 1024))
                      if data[i] == 0xFF and _audio_starts_at(data, i)), None)
        return found
    if pos == 0 and not _audio_starts_at(data, 0):
        # pas d'en-tête ID3 reconnaissable au début : le début du son doit être trouvé tout de suite
        found = next((i for i in range(0, min(len(data), 64 * 1024)) if data[i] == 0xFF and _audio_starts_at(data, i)), None)
        return found
    return min(pos, len(data))


def _audio_part(data: bytes) -> bytes:
    """Le son : tout ce qui suit les en-têtes ID3v2, sans le tag ID3v1 de 128 octets en fin de fichier."""
    end = _id3v2_end(data)
    a = data[end or 0:]
    if len(a) >= 128 and a[-128:-125] == b"TAG":
        a = a[:-128]
    return a


def _clean(v) -> str:
    return str(v).replace("\x00", " ").strip()


def salvage(path) -> dict:
    """Tout ce qui peut encore être lu dans le fichier, cadre par cadre."""
    info, cover = {}, None
    # 1) ID3v2 : d'abord normalement, puis sans conversion de version (souvent la cause de l'erreur)
    for kw in ({}, {"translate": False}):
        try:
            from mutagen.id3 import ID3
            t = ID3(str(path), **kw)
        except Exception:
            continue
        for key in list(t.keys()):
            try:
                fr = t[key]
                fid = key[:4]
                if fid in ID3_TEXT and getattr(fr, "text", None):
                    field = ID3_TEXT[fid]
                    if not info.get(field):
                        info[field] = _clean(fr.text[0])
                elif fid == "APIC" and cover is None and getattr(fr, "data", None):
                    cover = bytes(fr.data)
            except Exception:
                continue                  # ce cadre-là est abîmé : on garde les autres
        break
    # 2) ID3v1 (fin de fichier), format fixe très robuste
    try:
        with open(path, "rb") as f:
            f.seek(-128, os.SEEK_END)
            v1 = f.read(128)
        if v1[:3] == b"TAG":
            dec = lambda b: b.split(b"\x00")[0].decode("latin-1", "replace").strip()
            for field, (a, b) in (("title", (3, 33)), ("artist", (33, 63)), ("album", (63, 93)), ("year", (93, 97))):
                if not info.get(field) and dec(v1[a:b]):
                    info[field] = dec(v1[a:b])
            if not info.get("track") and v1[125] == 0 and v1[126]:
                info["track"] = str(v1[126])
    except OSError:
        pass
    for k in ("track", "disc"):
        if info.get(k):
            n = str(info[k]).split("/")[0].strip()
            info[k] = int(n) if n.isdigit() else None
    if info.get("year"):
        info["year"] = str(info["year"])[:4]
    info["cover"] = cover
    return {k: v for k, v in info.items() if v not in (None, "")}


def repair(path, log=None) -> bool:
    """Reconstruit des tags propres. True si réussi (son vérifié identique), False sinon (fichier inchangé)."""
    say = log or (lambda m: None)
    p = Path(path)
    if not can_repair(p) or not p.exists():
        return False
    try:
        original = p.read_bytes()
    except OSError:
        return False
    start = _id3v2_end(original)
    if start is None:
        say(f"✗ réparation impossible pour {p.name} : début du son introuvable avec certitude (fichier laissé intact)")
        return False
    audio_before = hashlib.sha256(_audio_part(original)).hexdigest()
    keep = salvage(p)
    stripped = original[start:]
    tmp = p.with_name(p.stem + ".reparation-en-cours.mp3")
    try:
        tmp.write_bytes(stripped)
        from .tags import write_tags
        write_tags(tmp, title=keep.get("title"), artist=keep.get("artist"), album=keep.get("album"),
                   album_artist=keep.get("album_artist"), track=keep.get("track"), disc=keep.get("disc"),
                   year=keep.get("year"), genre=keep.get("genre"), cover=keep.get("cover"))
        new = tmp.read_bytes()
        if hashlib.sha256(_audio_part(new)).hexdigest() != audio_before:
            raise ValueError("son modifié pendant la réparation : annulée")
        from .tags import read_tags
        read_tags(tmp)                                   # les nouveaux tags doivent se relire
        os.replace(tmp, p)                               # remplacement d'un seul coup : jamais de fichier à moitié écrit
    except Exception as e:                               # noqa: BLE001 - échec : l'original n'a pas été touché
        try:
            tmp.unlink()
        except OSError:
            pass
        say(f"✗ réparation impossible pour {p.name} : {e}")
        return False
    got = ", ".join(k for k in ("title", "artist", "album", "year", "cover") if keep.get(k)) or "aucune info lisible"
    say(f"🔧 tags réparés : {p.name} (son intact ; récupéré : {got.replace('title', 'titre').replace('artist', 'artiste').replace('year', 'année').replace('cover', 'pochette')})")
    return True


def run_with_repair(fn, path, log=None):
    """Exécute fn() ; si les tags du fichier sont abîmés, les répare puis réessaie une fois.
    Une erreur d'accès (lecture seule, fichier ouvert…) n'est pas une erreur de tags : elle est relancée telle quelle."""
    try:
        return fn()
    except Exception as e:                               # noqa: BLE001
        from .setaside import is_access_error
        if is_access_error(e) or not can_repair(path):
            raise
        if not repair(path, log):
            raise
        return fn()
