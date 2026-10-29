"""Index de la bibliothèque musicale (SQLite) : référencement, recherche, classement."""
import os
import sqlite3
import threading
from pathlib import Path

from .config import AUDIO_EXTS, data_dir
from .tags import read_tags, TrackInfo

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks(
  path TEXT PRIMARY KEY, title TEXT, artist TEXT, album_artist TEXT, album TEXT,
  track INTEGER, disc INTEGER, year TEXT, genre TEXT, duration REAL, bitrate INTEGER,
  has_cover INTEGER, mtime REAL, plays INTEGER DEFAULT 0, rating INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS playlists(id INTEGER PRIMARY KEY, name TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS playlist_items(playlist_id INTEGER, pos INTEGER, path TEXT);
"""
COLS = ["path", "title", "artist", "album_artist", "album", "track", "disc", "year",
        "genre", "duration", "bitrate", "has_cover"]


def iter_audio_files(root: str | Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith((".", "$")) and d != "System Volume Information"]
        for n in filenames:
            if Path(n).suffix.lower() in AUDIO_EXTS:
                yield str(Path(dirpath) / n)


class Library:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = str(db_path or data_dir() / "bibliotheque.db")
        self._lock = threading.RLock()
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # ---------- référencement ----------
    def scan(self, root, progress=None, cancel=lambda: False) -> int:
        files = list(iter_audio_files(root))
        n = 0
        for i, p in enumerate(files):
            if cancel():
                break
            try:
                mt = os.path.getmtime(p)
            except OSError:
                continue
            with self._lock:
                row = self.db.execute("SELECT mtime FROM tracks WHERE path=?", (p,)).fetchone()
            if row is None or row["mtime"] != mt:
                self.upsert(read_tags(p), mt)
                n += 1
            if progress:
                progress(i + 1, len(files), p)
        self.purge_missing(root)
        return n

    def upsert(self, t: TrackInfo, mtime=None):
        if mtime is None:
            try:
                mtime = os.path.getmtime(t.path)
            except OSError:
                mtime = 0
        vals = [getattr(t, c) for c in COLS]
        vals[-1] = int(bool(vals[-1]))
        with self._lock:
            self.db.execute(
                f"INSERT INTO tracks({','.join(COLS)},mtime) VALUES({','.join('?'*len(COLS))},?) "
                f"ON CONFLICT(path) DO UPDATE SET " + ",".join(f"{c}=excluded.{c}" for c in COLS[1:]) +
                ",mtime=excluded.mtime", vals + [mtime])
            self.db.commit()

    def rename_path(self, old, new):
        with self._lock:
            self.db.execute("DELETE FROM tracks WHERE path=?", (new,))
            self.db.execute("UPDATE tracks SET path=? WHERE path=?", (new, old))
            self.db.execute("UPDATE playlist_items SET path=? WHERE path=?", (new, old))
            self.db.commit()

    def remove(self, path):
        with self._lock:
            self.db.execute("DELETE FROM tracks WHERE path=?", (path,))
            self.db.commit()

    def purge_missing(self, root=None):
        with self._lock:
            q = "SELECT path FROM tracks" + (" WHERE path LIKE ?" if root else "")
            rows = self.db.execute(q, (str(root) + "%",) if root else ()).fetchall()
            gone = [(r["path"],) for r in rows if not os.path.exists(r["path"])]
            self.db.executemany("DELETE FROM tracks WHERE path=?", gone)
            self.db.commit()

    # ---------- requêtes / classement ----------
    def tracks(self, artist=None, album=None, search=None, incomplete_only=False, order="artist"):
        q, args = "SELECT * FROM tracks WHERE 1=1", []
        if artist is not None:
            q += " AND COALESCE(NULLIF(album_artist,''),NULLIF(artist,''),'Artiste inconnu')=?"; args.append(artist)
        if album is not None:
            q += " AND COALESCE(NULLIF(album,''),'Album inconnu')=?"; args.append(album)
        if search:
            q += " AND (title LIKE ? OR artist LIKE ? OR album LIKE ? OR genre LIKE ? OR path LIKE ?)"
            args += [f"%{search}%"] * 5
        if incomplete_only:
            q += " AND (COALESCE(title,'')='' OR COALESCE(artist,'')='' OR COALESCE(album,'')='')"
        orders = {
            "artist": "artist COLLATE NOCASE, album COLLATE NOCASE, disc, track, title",
            "album": "album COLLATE NOCASE, disc, track",
            "title": "title COLLATE NOCASE",
            "year": "year DESC, album, track",
            "plays": "plays DESC",
        }
        q += " ORDER BY " + orders.get(order, orders["artist"])
        with self._lock:
            return [dict(r) for r in self.db.execute(q, args).fetchall()]

    def has_path(self, path) -> bool:
        with self._lock:
            return self.db.execute("SELECT 1 FROM tracks WHERE path=?", (path,)).fetchone() is not None

    def artists(self):
        with self._lock:
            return [r[0] for r in self.db.execute(
                "SELECT COALESCE(NULLIF(album_artist,''),NULLIF(artist,''),'Artiste inconnu') a, COUNT(*) "
                "FROM tracks GROUP BY a ORDER BY a COLLATE NOCASE")]

    def albums(self, artist=None):
        q = ("SELECT COALESCE(NULLIF(album,''),'Album inconnu') al, MAX(year) y, COUNT(*) n FROM tracks")
        args = []
        if artist is not None:
            q += " WHERE COALESCE(NULLIF(album_artist,''),NULLIF(artist,''),'Artiste inconnu')=?"; args.append(artist)
        q += " GROUP BY al ORDER BY y, al COLLATE NOCASE"
        with self._lock:
            return [(r["al"], r["y"] or "", r["n"]) for r in self.db.execute(q, args)]

    def stats(self):
        with self._lock:
            r = self.db.execute(
                "SELECT COUNT(*) n, COUNT(DISTINCT artist) a, COUNT(DISTINCT album) al, "
                "COALESCE(SUM(duration),0) d, SUM(CASE WHEN COALESCE(title,'')='' OR COALESCE(artist,'')='' "
                "OR COALESCE(album,'')='' THEN 1 ELSE 0 END) inc FROM tracks").fetchone()
            return dict(r)

    def count_play(self, path):
        with self._lock:
            self.db.execute("UPDATE tracks SET plays=plays+1 WHERE path=?", (path,)); self.db.commit()

    # ---------- playlists ----------
    def playlists(self):
        with self._lock:
            return [(r["id"], r["name"]) for r in self.db.execute("SELECT * FROM playlists ORDER BY name")]

    def create_playlist(self, name) -> int:
        with self._lock:
            cur = self.db.execute("INSERT OR IGNORE INTO playlists(name) VALUES(?)", (name,))
            self.db.commit()
            return cur.lastrowid or self.db.execute("SELECT id FROM playlists WHERE name=?", (name,)).fetchone()[0]

    def delete_playlist(self, pid):
        with self._lock:
            self.db.execute("DELETE FROM playlist_items WHERE playlist_id=?", (pid,))
            self.db.execute("DELETE FROM playlists WHERE id=?", (pid,)); self.db.commit()

    def playlist_paths(self, pid):
        with self._lock:
            return [r[0] for r in self.db.execute(
                "SELECT path FROM playlist_items WHERE playlist_id=? ORDER BY pos", (pid,))]

    def set_playlist(self, pid, paths):
        with self._lock:
            self.db.execute("DELETE FROM playlist_items WHERE playlist_id=?", (pid,))
            self.db.executemany("INSERT INTO playlist_items VALUES(?,?,?)",
                                [(pid, i, p) for i, p in enumerate(paths)])
            self.db.commit()

    def add_to_playlist(self, pid, paths):
        self.set_playlist(pid, self.playlist_paths(pid) + list(paths))

    @staticmethod
    def export_m3u(paths, dest):
        from .tags import read_tags
        lines = ["#EXTM3U"]
        for p in paths:
            t = read_tags(p)
            lines.append(f"#EXTINF:{int(t.duration)},{t.artist} - {t.title}")
            lines.append(p)
        Path(dest).write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def import_m3u(src):
        base = Path(src).parent
        out = []
        for line in Path(src).read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                p = Path(line)
                out.append(str(p if p.is_absolute() else base / p))
        return out
