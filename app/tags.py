"""Lecture / écriture des métadonnées (ID3 pour MP3, tags génériques pour les autres formats)."""
from dataclasses import dataclass, field, asdict
from pathlib import Path

import mutagen
from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TPE1, TPE2, TALB, TRCK, TPOS, TDRC, TCON, APIC, TXXX


@dataclass
class TrackInfo:
    path: str
    title: str = ""
    artist: str = ""
    album_artist: str = ""
    album: str = ""
    track: int = 0
    disc: int = 0
    year: str = ""
    genre: str = ""
    duration: float = 0.0
    bitrate: int = 0
    has_cover: bool = False
    mb_recording_id: str = ""
    extra: dict = field(default_factory=dict)

    def as_dict(self):
        return asdict(self)

    @property
    def is_incomplete(self) -> bool:
        return not (self.title and self.artist and self.album)


def _num(v) -> int:
    try:
        return int(str(v).split("/")[0].strip() or 0)
    except ValueError:
        return 0


def read_tags(path: str | Path) -> TrackInfo:
    path = str(path)
    info = TrackInfo(path=path)
    try:
        f = mutagen.File(path)
    except Exception:
        f = None
    if f is None:
        return info
    if f.info is not None:
        info.duration = float(getattr(f.info, "length", 0) or 0)
        info.bitrate = int((getattr(f.info, "bitrate", 0) or 0) / 1000)
    tags = f.tags
    if tags is None:
        return info
    if isinstance(tags, ID3):
        g = lambda k: str(tags[k].text[0]) if k in tags and tags[k].text else ""
        info.title, info.artist, info.album = g("TIT2"), g("TPE1"), g("TALB")
        info.album_artist, info.genre = g("TPE2"), g("TCON")
        info.track, info.disc = _num(g("TRCK")), _num(g("TPOS"))
        info.year = g("TDRC")[:4]
        info.has_cover = any(k.startswith("APIC") for k in tags.keys())
        for fr in tags.getall("TXXX"):
            if fr.desc == "MusicBrainz Release Track Id" or fr.desc == "MusicBrainz Recording Id":
                info.mb_recording_id = str(fr.text[0])
    elif type(tags).__name__ == "ASFTags":   # WMA (Windows Media Audio)
        def g(*keys):
            for k in keys:
                v = tags.get(k)
                if v:
                    return str(v[0].value if hasattr(v[0], "value") else v[0]).strip()
            return ""
        info.title, info.artist = g("Title"), g("Author", "WM/AlbumArtist")
        info.album, info.album_artist = g("WM/AlbumTitle"), g("WM/AlbumArtist")
        info.genre, info.year = g("WM/Genre"), g("WM/Year")[:4]
        info.track = _num(g("WM/TrackNumber", "WM/Track"))
        info.disc = _num(g("WM/PartOfSet"))
        info.has_cover = bool(tags.get("WM/Picture"))
    else:  # FLAC / OGG / MP4 ...
        def g(*keys):
            for k in keys:
                try:
                    present = k in tags
                except (ValueError, KeyError):   # OGG : les noms comme « ©nam » (M4A) sont refusés
                    present = False
                if present:
                    v = tags[k]
                    v = v[0] if isinstance(v, list) and v else v
                    if isinstance(v, tuple):
                        v = v[0]
                    return str(v)
            return ""
        info.title = g("title", "\xa9nam")
        info.artist = g("artist", "\xa9ART")
        info.album = g("album", "\xa9alb")
        info.album_artist = g("albumartist", "aART")
        info.genre = g("genre", "\xa9gen")
        info.year = g("date", "\xa9day")[:4]
        info.track = _num(g("tracknumber", "trkn"))
        info.disc = _num(g("discnumber", "disk"))
        def has(k):
            try:
                return k in tags
            except (ValueError, KeyError):
                return False
        info.has_cover = bool(getattr(f, "pictures", None)) or has("covr") or has("metadata_block_picture")
    return info


def write_tags(path: str | Path, title=None, artist=None, album=None, album_artist=None,
               track=None, disc=None, year=None, genre=None, cover: bytes | None = None,
               mb_recording_id=None):
    """Écrit uniquement les champs fournis (None = inchangé)."""
    path = str(path)
    try:   # fichier en lecture seule (copié d'un CD…) : on retire cet attribut pour pouvoir écrire
        import os, stat
        os.chmod(path, os.stat(path).st_mode | stat.S_IWRITE)
    except OSError:
        pass
    if path.lower().endswith(".mp3"):
        try:
            t = ID3(path)
        except ID3NoHeaderError:
            t = ID3()
        pairs = [(TIT2, title), (TPE1, artist), (TALB, album), (TPE2, album_artist),
                 (TCON, genre), (TDRC, year)]
        for cls, val in pairs:
            if val is not None and str(val) != "":
                t.setall(cls.__name__, [cls(encoding=3, text=str(val))])
        if track:
            t.setall("TRCK", [TRCK(encoding=3, text=str(track))])
        if disc:
            t.setall("TPOS", [TPOS(encoding=3, text=str(disc))])
        if cover:
            mime = "image/png" if cover[:4] == b"\x89PNG" else "image/jpeg"
            t.delall("APIC")
            t.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover))
        if mb_recording_id:
            t.add(TXXX(encoding=3, desc="MusicBrainz Recording Id", text=mb_recording_id))
        t.save(path, v2_version=3)  # ID3v2.3 = compatible avec l'Explorateur Windows
        return
    f = mutagen.File(path, easy=True)
    if f is None:
        return
    if f.tags is None:
        f.add_tags()
    for k, v in dict(title=title, artist=artist, album=album, albumartist=album_artist,
                     genre=genre, date=year).items():
        if v:
            f[k] = str(v)
    if track:
        f["tracknumber"] = str(track)
    if disc:
        f["discnumber"] = str(disc)
    f.save()
    if cover and path.lower().endswith(".flac"):
        from mutagen.flac import FLAC, Picture
        fl = FLAC(path)
        pic = Picture(); pic.type = 3; pic.data = cover
        pic.mime = "image/png" if cover[:4] == b"\x89PNG" else "image/jpeg"
        fl.clear_pictures(); fl.add_picture(pic); fl.save()


def read_cover(path: str | Path) -> bytes | None:
    try:
        f = mutagen.File(str(path))
    except Exception:
        return None
    if f is None or f.tags is None:
        pics = getattr(f, "pictures", None)
        return pics[0].data if pics else None
    if isinstance(f.tags, ID3):
        for k in f.tags.keys():
            if k.startswith("APIC"):
                return f.tags[k].data
    pics = getattr(f, "pictures", None)
    if pics:
        return pics[0].data
    try:
        if "covr" in f.tags:
            return bytes(f.tags["covr"][0])
    except (ValueError, KeyError):
        pass
    # WMA : pochette dans WM/Picture (type, taille, type MIME, description, image)
    if type(f.tags).__name__ == "ASFTags" and f.tags.get("WM/Picture"):
        try:
            import struct
            raw = f.tags["WM/Picture"][0].value
            size = struct.unpack_from("<I", raw, 1)[0]
            pos = 5
            for _ in range(2):              # type MIME puis description, en UTF-16 terminés par 0
                while raw[pos:pos + 2] != b"\x00\x00":
                    pos += 2
                pos += 2
            return raw[pos:pos + size]
        except Exception:
            return None
    # OGG Vorbis / Opus : pochette en base64 dans METADATA_BLOCK_PICTURE
    try:
        vals = f.tags.get("metadata_block_picture") or f.tags.get("METADATA_BLOCK_PICTURE")
        if vals:
            import base64
            from mutagen.flac import Picture
            return Picture(base64.b64decode(vals[0])).data
    except Exception:
        pass
    return None


def guess_from_filename(path: str | Path) -> dict:
    """'01 - Artiste - Titre.mp3' -> {track, artist, title}."""
    import re
    stem = Path(path).stem
    stem = re.sub(r"[_]+", " ", stem)
    stem = re.sub(r"\s*[\(\[](official|clip|lyrics?|audio|video|hd|hq)[^\)\]]*[\)\]]", "", stem, flags=re.I)
    out = {}
    m = re.match(r"^\s*(\d{1,3})[\s.\-_]+(.*)$", stem)
    if m:
        out["track"] = int(m.group(1)); stem = m.group(2)
    parts = [p.strip() for p in re.split(r"\s+[-–—]\s+", stem) if p.strip()]
    if len(parts) >= 2:
        out["artist"], out["title"] = parts[0], " - ".join(parts[1:])
    elif parts:
        out["title"] = parts[0]
    return out
