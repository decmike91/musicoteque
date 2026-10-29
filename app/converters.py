"""Conversions : CD audio -> MP3 (cyanrip, métadonnées MusicBrainz) et lien YouTube -> MP3 (yt-dlp)."""
import os
import re
import string
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import settings, tool
from .tags import read_tags, write_tags, guess_from_filename

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


# ======================= CD -> MP3 =======================
def cd_drives() -> list[str]:
    """Lecteurs optiques Windows (ex. ['D:'])."""
    if sys.platform != "win32":
        return [d for d in ("/dev/cdrom", "/dev/sr0") if os.path.exists(d)]
    import ctypes
    out = []
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    for i, letter in enumerate(string.ascii_uppercase):
        if mask & (1 << i) and ctypes.windll.kernel32.GetDriveTypeW(f"{letter}:\\") == 5:
            out.append(f"{letter}:")
    return out


def _run(cmd, cwd=None, log=print, cancel=lambda: False):
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                            creationflags=CREATE_NO_WINDOW)
    for line in proc.stdout:
        log(line.rstrip())
        if cancel():
            proc.kill(); break
    return proc.wait()


def cd_info(drive: str, log=print) -> int:
    exe = tool("cyanrip")
    if not exe:
        raise RuntimeError("cyanrip introuvable : lancez installer.bat pour l'installer.")
    return _run([exe, "-d", drive, "-I"], log=log)


def rip_cd(drive: str, bitrate=320, log=print, cancel=lambda: False, release=None,
           album=None, artist=None) -> list[str]:
    """Extrait le CD en MP3 dans un dossier temporaire avec les tags MusicBrainz + pochette.
    Retourne la liste des MP3 créés (à ranger ensuite dans la bibliothèque)."""
    exe = tool("cyanrip")
    if not exe:
        raise RuntimeError("cyanrip introuvable : lancez installer.bat pour l'installer.")
    out_dir = Path(tempfile.mkdtemp(prefix="rip_"))
    cmd = [exe, "-d", drive, "-o", "mp3", "-b", str(int(bitrate)), "-A", "-T", "simple", "-Q"]
    if release:
        cmd += ["-R", str(release)]
    if album or artist:  # CD inconnu de MusicBrainz : métadonnées saisies
        meta = []
        if album:
            meta.append(f'album="{album}"')
        if artist:
            meta.append(f'album_artist="{artist}"')
        cmd += ["-N", "-a", ":".join(meta)]
    log("> " + " ".join(cmd))
    code = _run(cmd, cwd=out_dir, log=log, cancel=cancel)
    files = sorted(str(p) for p in out_dir.rglob("*.mp3"))
    if code != 0 and not files:
        raise RuntimeError(f"L'extraction a échoué (code {code}). Si le CD est inconnu, "
                           "renseignez l'album et l'artiste puis relancez.")
    return files


# ======================= YouTube -> MP3 =======================
def youtube_to_mp3(url: str, dest_dir: str | Path, bitrate=320, log=print, progress=None,
                   playlist=True) -> list[str]:
    import yt_dlp

    dest_dir = Path(dest_dir); dest_dir.mkdir(parents=True, exist_ok=True)
    created = []

    def hook(d):
        if d["status"] == "downloading" and progress:
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            progress(d.get("downloaded_bytes", 0), tot, d.get("filename", ""))
        elif d["status"] == "finished":
            log("Téléchargé, conversion en MP3…")

    def post_hook(d):
        if d.get("status") == "finished" and d.get("postprocessor") == "MoveFiles":
            fp = d.get("info_dict", {}).get("filepath")
            if fp:
                created.append(fp)

    class Logger:
        def debug(self, m):
            if not m.startswith("[debug]"):
                log(m)
        info = debug
        def warning(self, m): log("Attention : " + m)
        def error(self, m): log("Erreur : " + m)

    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(dest_dir / "%(title)s.%(ext)s"),
        "noplaylist": not playlist,
        "windowsfilenames": True,
        "writethumbnail": True,
        "logger": Logger(),
        "progress_hooks": [hook],
        "postprocessor_hooks": [post_hook],
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": str(bitrate)},
            {"key": "FFmpegMetadata", "add_metadata": True},
            {"key": "EmbedThumbnail"},
        ],
        "postprocessor_args": {"embedthumbnail+ffmpeg_o": ["-c:v", "mjpeg", "-vf", "crop=ih:ih"]},
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    if not created:
        created = [str(p) for p in dest_dir.glob("*.mp3")]
    for f in created:
        _clean_youtube_tags(f)
    return created


def _clean_youtube_tags(path):
    """YouTube met le nom de la chaîne en artiste et le titre complet de la vidéo :
    on essaie d'en déduire « Artiste - Titre »."""
    t = read_tags(path)
    title = t.title or Path(path).stem
    g = guess_from_filename(title + ".mp3")
    artist = g.get("artist") or re.sub(r"\s*-\s*Topic$|VEVO$", "", t.artist or "").strip()
    clean_title = g.get("title", title)
    write_tags(path, title=clean_title, artist=artist or None)
