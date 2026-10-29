"""Moteur audio : décodage (ffmpeg), effets temps réel (égaliseur 10 bandes, basses, surround,
réverbération, ambiances, balance, correction d'audiogramme par oreille), volume, vumètres,
et sortie simultanée sur 1 à 3 périphériques (« sorties »), chacun avec ses propres réglages."""
import collections
import math
import subprocess
import sys
import threading
import time

import numpy as np
from pedalboard import (Pedalboard, PeakFilter, LowShelfFilter, HighShelfFilter, Reverb, Limiter, Gain)

from .profiles import AUDIOGRAM_FREQS, audiogram_gains, normalize

SR = 44100
BLOCK = 2048
EQ_FREQS = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
EQ_LABELS = ["31", "62", "125", "250", "500", "1k", "2k", "4k", "8k", "16k"]

EQ_PRESETS = {
    "Plat":        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "Rock":        [5, 4, 2, -1, -2, -1, 2, 3, 4, 4],
    "Pop":         [-1, 1, 3, 4, 3, 0, -1, -1, 1, 2],
    "Jazz":        [3, 2, 1, 2, -1, -1, 0, 1, 2, 3],
    "Classique":   [4, 3, 2, 1, -1, -1, 0, 2, 3, 4],
    "Électro":     [6, 5, 1, 0, -2, 2, 1, 1, 4, 5],
    "Hip-Hop":     [6, 5, 2, 3, -1, -1, 1, -1, 2, 3],
    "Voix":        [-3, -2, -1, 1, 3, 4, 4, 3, 1, -1],
    "Basses +":    [7, 6, 5, 2, 0, 0, 0, 0, 0, 0],
    "Aigus +":     [0, 0, 0, 0, 0, 1, 3, 5, 6, 7],
    "Loudness":    [6, 4, 0, 0, -2, 0, -1, -2, 4, 2],
    "Acoustique":  [4, 3, 2, 1, 2, 2, 3, 3, 2, 1],
}

# Ambiances préprogrammées : (réverbe taille, réverbe mixage, amortissement, surround)
AMBIANCES = {
    "Aucune":           None,
    "Petite pièce":     (0.25, 0.15, 0.6, 0.15),
    "Salon":            (0.40, 0.18, 0.5, 0.25),
    "Club":             (0.45, 0.22, 0.4, 0.40),
    "Salle de concert": (0.75, 0.30, 0.35, 0.50),
    "Live / Stade":     (0.90, 0.35, 0.25, 0.70),
    "Cathédrale":       (0.98, 0.45, 0.15, 0.55),
    "Studio":           (0.15, 0.08, 0.7, 0.10),
}

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


MAX_ZONES = 6          # sorties audio (haut-parleurs, casque, HDMI…)
CHANNEL_MODES = {"stereo": "Stéréo", "swap": "Stéréo inversée (G↔D)", "mono": "Mono",
                 "left": "Voie gauche seule", "right": "Voie droite seule"}


# ====================================================================== correction auditive
class AudiogramFilter:
    """Filtre FIR à phase linéaire, un par oreille, dessiné d'après la courbe de correction.
    Il tourne toujours (filtre neutre si désactivé) pour que toutes les sorties aient la même latence."""
    TAPS = 2048

    def __init__(self):
        self._h = None
        self._H = {}
        self._tail = np.zeros((2, self.TAPS - 1), dtype=np.float32)
        self.set_gains([0] * len(AUDIOGRAM_FREQS), [0] * len(AUDIOGRAM_FREQS))

    @classmethod
    def design(cls, gains_db) -> np.ndarray:
        n = cls.TAPS
        f = np.fft.rfftfreq(n, 1 / SR)
        g8k = gains_db[-1]
        fx = np.log10([20, *AUDIOGRAM_FREQS, 10000, 16000, SR / 2])
        gx = [gains_db[0], *gains_db, g8k, g8k * 0.5, 0.0]  # au-delà de 10 kHz : correction atténuée
        db = np.interp(np.log10(np.maximum(f, 1.0)), fx, gx)
        h = np.fft.irfft(10 ** (db / 20), n)
        h = np.roll(h, n // 2) * np.hanning(n)
        return h.astype(np.float32)

    def set_gains(self, gl, gr, enabled=True):
        if not enabled:
            gl = gr = [0.0] * len(AUDIOGRAM_FREQS)
        head = -0.5 * max(max(gl), max(gr), 0.0)  # marge pour éviter la saturation
        k = 10 ** (head / 20)
        self._h = np.stack([self.design(gl), self.design(gr)]) * k
        self._H = {}

    def reset(self):
        self._tail = np.zeros((2, self.TAPS - 1), dtype=np.float32)

    def process(self, x: np.ndarray) -> np.ndarray:
        n, m = x.shape[1], self.TAPS
        nfft = 1 << (n + m - 1 - 1).bit_length()
        h, H = self._h, self._H
        if nfft not in H:
            H[nfft] = np.fft.rfft(h, nfft)
        y = np.fft.irfft(np.fft.rfft(x, nfft) * H[nfft], nfft)[:, : n + m - 1]
        y[:, : m - 1] += self._tail
        self._tail = y[:, n:].astype(np.float32)
        return y[:, :n].astype(np.float32)


# ====================================================================== effets
class DSP:
    """Chaîne d'effets d'une sortie. Les réglages peuvent être modifiés pendant la lecture."""

    def __init__(self):
        self.eq = [PeakFilter(cutoff_frequency_hz=f, gain_db=0.0, q=1.2) for f in EQ_FREQS]
        self.eq[0] = LowShelfFilter(cutoff_frequency_hz=40, gain_db=0.0, q=0.7)
        self.eq[-1] = HighShelfFilter(cutoff_frequency_hz=12000, gain_db=0.0, q=0.7)
        self.bass = LowShelfFilter(cutoff_frequency_hz=110, gain_db=0.0, q=0.7)
        self.preamp = Gain(gain_db=0.0)
        self.reverb = Reverb(room_size=0.5, damping=0.5, wet_level=0.0, dry_level=1.0, width=1.0)
        self.board = Pedalboard([self.preamp, *self.eq, self.bass, self.reverb])
        self.limiter = Pedalboard([Limiter(threshold_db=-0.5, release_ms=80)])
        self.audiogram = AudiogramFilter()
        self.balance = 0.0      # -1 gauche ... +1 droite
        self.surround = 0.0     # 0 ... 1 (élargissement stéréo + effet Haas)
        self.enabled = True
        self._lock = threading.RLock()   # réglages modifiés depuis l'interface pendant le traitement
        self._haas_len = int(0.012 * SR)  # 12 ms
        self._haas = np.zeros((2, self._haas_len), dtype=np.float32)

    # --- réglages ---
    def set_eq(self, gains):
        for flt, g in zip(self.eq, gains):
            flt.gain_db = float(g)
        # pré-amplification négative pour éviter la saturation quand on pousse l'égaliseur
        self.preamp.gain_db = -max(0.0, max(gains) * 0.6)

    def set_bass(self, db):
        self.bass.gain_db = float(db)

    def set_reverb(self, mix, room=None, damping=None):
        mix = float(np.clip(mix, 0, 1))
        self.reverb.wet_level = mix * 0.6
        self.reverb.dry_level = 1.0 - mix * 0.35
        if room is not None:
            self.reverb.room_size = float(np.clip(room, 0, 1))
        if damping is not None:
            self.reverb.damping = float(np.clip(damping, 0, 1))

    def set_audiogram(self, ag: dict):
        gl, gr = audiogram_gains(ag)
        self.audiogram.set_gains(gl, gr, bool(ag.get("enabled")))

    def apply_profile(self, p: dict):
        with self._lock:
            self._apply_profile(normalize(p))

    def _apply_profile(self, p: dict):
        self.set_eq(p["eq_gains"] if p["eq_enabled"] else [0.0] * 10)
        self.set_bass(p["bass"])
        amb = AMBIANCES.get(p["ambiance"])
        self.set_reverb(p["reverb_mix"], p["reverb_room"], amb[2] if amb else 0.5)
        self.surround = float(p["surround"])
        self.balance = float(p["balance"])
        self.set_audiogram(p["audiogram"])

    def reset(self):
        with self._lock:
            self._reset()

    def _reset(self):
        self.board.reset()
        self.limiter.reset()
        self.audiogram.reset()
        self._haas = np.zeros((2, self._haas_len), dtype=np.float32)

    # --- traitement ---
    def process(self, x: np.ndarray) -> np.ndarray:
        """x : tableau (2, n) float32."""
        with self._lock:
            return self._process(x)

    def _process(self, x: np.ndarray) -> np.ndarray:
        if not self.enabled:
            return self.audiogram.process(x)
        y = self.board(x, SR, reset=False)
        if self.surround > 0:
            s = self.surround
            mid, side = (y[0] + y[1]) * 0.5, (y[0] - y[1]) * 0.5
            side = side * (1 + 1.5 * s)
            l, r = mid + side, mid - side
            # Haas : chaque voie reçoit un écho retardé (12 ms) et inversé de l'autre -> sensation d'espace
            n = y.shape[1]
            buf = np.concatenate([self._haas, np.stack([l, r])], axis=1)
            d = buf[:, :n]
            self._haas = buf[:, n:]
            l, r = l - 0.25 * s * d[1], r - 0.25 * s * d[0]
            y = np.stack([l, r]) / (1 + 0.6 * s)
        if self.balance:
            b = self.balance
            y = y * np.array([[min(1.0, 1 - b)], [min(1.0, 1 + b)]], dtype=np.float32)
        y = self.audiogram.process(y.astype(np.float32, copy=False))
        return self.limiter(y, SR, reset=False).astype(np.float32, copy=False)


def levels(x: np.ndarray):
    """(peak_g, peak_d, rms_g, rms_d) d'un bloc (2, n)."""
    if x.size == 0:
        return (0.0, 0.0, 0.0, 0.0)
    pk = np.abs(x).max(axis=1)
    rms = np.sqrt(np.mean(x * x, axis=1))
    return (float(pk[0]), float(pk[1]), float(rms[0]), float(rms[1]))


# ====================================================================== périphériques
def _preferred_hostapi(sd):
    """Sous Windows, DirectSound : noms complets et rééchantillonnage automatique."""
    try:
        for i, api in enumerate(sd.query_hostapis()):
            if sys.platform == "win32" and api["name"] == "Windows DirectSound":
                return i
        return sd.default.hostapi if sd.default.hostapi >= 0 else 0
    except Exception:
        return 0


LINUX_PREFIX = "Musicotheque_"


def output_devices() -> list[str]:
    """Noms des périphériques de sortie (haut-parleurs, casques, enceintes Bluetooth, HDMI…).
    Sous Linux (Raspberry Pi…), on montre les sorties préparées par l'installateur
    (une par carte son ou par sortie PipeWire), sinon toutes les sorties ALSA."""
    try:
        import sounddevice as sd
        api = _preferred_hostapi(sd)
        names = [d["name"] for d in sd.query_devices()
                 if d["max_output_channels"] > 0 and d["hostapi"] == api]
        mine = [n for n in names if n.startswith(LINUX_PREFIX)]
        return mine or names
    except Exception:
        return []


_labels = None


def device_label(name: str) -> str:
    """Nom lisible d'un périphérique (« Prise jack », « HDMI 1 »… sur Raspberry Pi)."""
    global _labels
    if _labels is None:
        try:
            import json
            from .config import data_dir
            _labels = json.loads((data_dir() / "peripheriques.json").read_text(encoding="utf-8"))
        except Exception:
            _labels = {}
    if name in _labels:
        return _labels[name]
    return name[len(LINUX_PREFIX):].replace("_", " ") if name.startswith(LINUX_PREFIX) else name


def resolve_device(name: str):
    """Nom -> index sounddevice (None = périphérique par défaut de Windows)."""
    if not name:
        return None
    try:
        import sounddevice as sd
        api = _preferred_hostapi(sd)
        devs = list(enumerate(sd.query_devices()))
        for pass_api in (True, False):
            for i, d in devs:
                if d["max_output_channels"] > 0 and d["name"] == name and (not pass_api or d["hostapi"] == api):
                    return i
    except Exception:
        pass
    return None


# ====================================================================== sortie
class Zone:
    """Une sortie audio : un périphérique + son propre profil (égaliseur, ambiance, audiogramme),
    son volume, son retard d'alignement et son mode de voies."""

    def __init__(self, player, cfg: dict):
        self.player = player
        self.cfg = cfg
        self.dsp = DSP()
        self.dsp.apply_profile(cfg.get("profile"))
        self.stream = None
        self.channels = 2
        self.error = ""
        self.levels = (0.0, 0.0, 0.0, 0.0)
        self._lock = threading.Lock()
        # fréquence d'échantillonnage du périphérique (ex. 48 kHz en HDMI) : conversion si besoin
        self.rate = self._pick_rate()
        self._rs = None
        if self.rate != SR:
            from pedalboard.io import StreamResampler
            self._rs = StreamResampler(SR, self.rate, 2)
        self._blocks = collections.deque()
        self._off = 0
        self.buffered = 0
        self._err = 0.0
        self.consumed = 0          # échantillons lus depuis le dernier départ (silence d'alignement compris)
        self._t_last = 0.0         # instant du dernier appel (sortie principale)
        self._last_got = 0
        self.reset_buffer()

    # --- réglages ---
    @property
    def enabled(self):
        return bool(self.cfg.get("enabled", True))

    @property
    def delay_samples(self):
        return int(max(0, float(self.cfg.get("delay_ms", 0))) * self.rate / 1000)

    @property
    def ahead_seconds(self):
        """Durée de son prête dans le tampon (hors silence d'alignement)."""
        return (self.buffered - self.delay_samples) / self.rate

    def _pick_rate(self):
        try:
            import sounddevice as sd
            dev = resolve_device(self.cfg.get("device", ""))
            info = sd.query_devices(dev, "output")
            ch = max(1, min(2, int(info["max_output_channels"])))
            try:
                sd.check_output_settings(device=dev, samplerate=SR, channels=ch, dtype="float32")
                return SR
            except Exception:
                return int(info["default_samplerate"]) or SR
        except Exception:
            return SR

    def apply_profile(self, profile):
        self.cfg["profile"] = normalize(profile)
        self.dsp.apply_profile(self.cfg["profile"])

    # --- tampon ---
    def reset_buffer(self):
        with self._lock:
            self._blocks.clear()
            self._off = 0
            self.buffered = 0
            self._err = 0.0
            self.consumed = 0
            self._last_got = 0
            self._t_last = time.perf_counter()
            if self._rs is not None:
                self._rs.reset()
            d = self.delay_samples
            if d:
                self._blocks.append(np.zeros((2, d), dtype=np.float32))
                self.buffered = d
        self.dsp.reset()

    def push(self, y):
        if self._rs is not None:
            y = self._rs.process(y)
            if y.shape[1] == 0:
                return
        with self._lock:
            self._blocks.append(y)
            self.buffered += y.shape[1]

    def _take(self, n):
        out = np.zeros((2, n), dtype=np.float32)
        got = 0
        with self._lock:
            while got < n and self._blocks:
                b = self._blocks[0]
                k = min(n - got, b.shape[1] - self._off)
                out[:, got:got + k] = b[:, self._off:self._off + k]
                got += k
                self._off += k
                if self._off >= b.shape[1]:
                    self._blocks.popleft(); self._off = 0
            self.buffered -= got
            self.consumed += got
        return out, got

    def _drop(self, n):
        self._take(n)

    # --- périphérique ---
    def open(self):
        if self.stream is not None or not self.enabled:
            return
        import sounddevice as sd
        dev = resolve_device(self.cfg.get("device", ""))
        try:
            info = sd.query_devices(dev, "output")
            self.channels = max(1, min(2, int(info["max_output_channels"])))
            self.stream = sd.OutputStream(device=dev, samplerate=self.rate, channels=self.channels, dtype="float32",
                                          blocksize=1024, callback=self._callback, latency="low")
            self.stream.start()
            self.error = ""
        except Exception as e:
            self.stream = None
            self.error = f"Sortie « {self.cfg.get('device') or 'par défaut'} » indisponible : {e}"
            raise

    def close(self):
        if self.stream is not None:
            try:
                self.stream.stop(); self.stream.close()
            except Exception:
                pass
            self.stream = None

    def _callback(self, outdata, frames, time_info, status):
        p = self.player
        master = p.master
        if not p.playing:
            outdata.fill(0); self.levels = (0.0, 0.0, 0.0, 0.0)
            if self is master:
                self._t_last, self._last_got = time.perf_counter(), 0
            return
        if self is master:
            out, got = self._take(frames)
            self._t_last, self._last_got = time.perf_counter(), got
            p._frames_played += got
            p.position = p._start_offset + p._frames_played / self.rate
            if got == 0 and p._eof:
                p.playing = False; p.finished = True
        else:
            out, got = self._take_synced(frames, master)
        out = self._mix(out)
        self.levels = levels(out)
        if self.channels == 1:
            outdata[:, 0] = out.mean(axis=0)
        else:
            outdata[:] = out.T

    def _take_synced(self, frames, master):
        """Garde cette sortie calée sur la sortie principale.
        On compare la position de lecture de chacune (en échantillons, à l'instant présent) ;
        les horloges de deux cartes son ne battent jamais exactement au même rythme, donc on
        rattrape l'écart en lisant 1 échantillon de plus ou de moins par bloc (inaudible)."""
        if master is None:
            return self._take(frames)
        elapsed = min(time.perf_counter() - master._t_last, 2 * frames / self.rate)
        # chaque sortie commence par son silence d'alignement : le décalage voulu est donc obtenu
        # quand toutes les sorties ont lu la même durée totale (converti si les fréquences diffèrent)
        master_now = (master.consumed - master._last_got + elapsed * master.rate) * self.rate / master.rate
        err = self.consumed - master_now                              # > 0 : cette sortie est en avance
        if err > frames:                         # la principale attend des données : on attend aussi
            return np.zeros((2, frames), dtype=np.float32), 0
        if err < -self.rate * 0.25:                     # gros retard (périphérique bloqué) : on saute
            self._take(int(-err)); self._err = 0.0
        self._err = 0.95 * self._err + 0.05 * err
        e = self._err
        k = 0 if abs(e) < 64 else int(min(8, 1 + abs(e) // 1000))   # rattrapage plus rapide si gros écart
        n = frames - k if e > 0 else frames + k
        out, got = self._take(n)
        if n != frames:
            if got == n:
                t = np.linspace(0, n - 1, frames)
                out = np.stack([np.interp(t, np.arange(n), out[c]) for c in range(2)]).astype(np.float32)
            else:  # tampon presque vide : on complète par du silence
                fixed = np.zeros((2, frames), dtype=np.float32)
                k = min(frames, out.shape[1]); fixed[:, :k] = out[:, :k]; out = fixed
        return out, got

    def _mix(self, out):
        p = self.player
        g = 0.0 if p.muted else (p.volume ** 2) * float(self.cfg.get("volume", 1.0)) ** 2
        out *= g
        mode = self.cfg.get("channels", "stereo")
        if mode == "swap":
            out = out[::-1].copy()
        elif mode == "mono":
            out[:] = out.mean(axis=0)
        elif mode == "left":
            out[1] = out[0]
        elif mode == "right":
            out[0] = out[1]
        return out


class Player:
    """Lecteur multi-sorties. L'interface interroge position/levels/finished via un minuteur."""

    def __init__(self, zone_cfgs=None):
        self.volume = 0.8
        self.muted = False
        self.path = None
        self.duration = 0.0
        self.position = 0.0
        self.playing = False
        self.finished = False
        self.error = ""
        self._proc = None
        self._thread = None
        self._stop = threading.Event()
        self._eof = False
        self._frames_played = 0
        self._start_offset = 0.0
        self.zones: list[Zone] = []
        self.set_zones(zone_cfgs if zone_cfgs is not None else [{"device": "", "enabled": True, "profile": {}}])

    # ---------- sorties ----------
    @property
    def master(self) -> Zone | None:
        """La première sortie active donne le tempo (position, fin de morceau)."""
        for z in self.zones:
            if z.enabled and z.stream is not None:
                return z
        return None

    @property
    def active_zones(self):
        return [z for z in self.zones if z.enabled]

    @property
    def levels(self):
        m = self.master
        return m.levels if m else (0.0, 0.0, 0.0, 0.0)

    @property
    def dsp(self):  # compatibilité : effets de la première sortie
        return self.zones[0].dsp if self.zones else None

    def set_zones(self, cfgs):
        """(Re)crée les sorties ; la lecture reprend là où elle en était."""
        was, pos = self.playing, self.position
        self.playing = False
        self._stop_decoder()
        for z in self.zones:
            z.close()
        self.zones = [Zone(self, c) for c in cfgs[:MAX_ZONES]]
        if self.path:
            self._start_decoder(pos)
            if was:
                self.play()

    def realign(self):
        """À appeler après un changement de retard : recale toutes les sorties."""
        if self.path:
            self.seek(self.position)

    def _open_streams(self):
        errors = []
        for z in self.active_zones:
            try:
                z.open()
            except Exception:
                errors.append(z.error)
        if errors:
            self.error = " · ".join(errors)
        if self.master is None:
            raise RuntimeError(self.error or "Aucune sortie audio disponible.")

    # ---------- décodage ----------
    def _decoder(self, path, start, stop):
        cmd = ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{start:.3f}", "-i", path,
               "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    creationflags=CREATE_NO_WINDOW)
        except FileNotFoundError:
            self.error = "ffmpeg introuvable : lancez l'installateur"
            self._eof = True
            return
        self._proc = proc
        nbytes = BLOCK * 2 * 4
        high = BLOCK * 6
        while not stop.is_set():
            data = proc.stdout.read(nbytes)
            if not data:
                break
            x = np.frombuffer(data[: len(data) // 8 * 8], dtype=np.float32).reshape(-1, 2).T.copy()
            for z in self.zones:
                # une sortie qui n'a pas pu s'ouvrir ne doit pas accumuler de son
                if z.enabled and (z.stream is not None or not self.playing):
                    z.push(z.dsp.process(x))
            # le rythme est donné par la sortie principale
            while not stop.is_set():
                m = self.master
                ref = m if m is not None else (self.active_zones[0] if self.active_zones else None)
                if ref is None or min(z.ahead_seconds for z in self.active_zones) < high / SR:
                    break
                stop.wait(0.01)
        proc.kill()
        if not stop.is_set():
            self._eof = True

    def _start_decoder(self, start):
        self._stop_decoder()
        self._stop = threading.Event()
        self._eof = False
        for z in self.zones:
            z.reset_buffer()
        self._start_offset = start
        self._frames_played = 0
        self.position = start
        self._thread = threading.Thread(target=self._decoder, args=(self.path, start, self._stop), daemon=True)
        self._thread.start()

    def _stop_decoder(self):
        self._stop.set()
        if self._proc:
            try:
                self._proc.kill()
            except OSError:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        self._proc = None

    # ---------- commandes ----------
    def load(self, path, duration=0.0, autoplay=True):
        from .tags import read_tags
        self.playing = False
        self.path = path
        self.duration = duration or read_tags(path).duration
        self.finished = False
        self.error = ""
        self._start_decoder(0.0)
        if autoplay:
            self.play()

    def play(self):
        if not self.path:
            return
        if self.finished:
            self.finished = False
            self._start_decoder(0.0)
        # on laisse le décodeur prendre un peu d'avance pour que toutes les sorties partent ensemble
        t0 = time.perf_counter()
        while (self.zones and min(z.ahead_seconds for z in self.active_zones or self.zones) < BLOCK * 2 / SR
               and not self._eof and time.perf_counter() - t0 < 1.0):
            time.sleep(0.005)
        self._open_streams()
        self.playing = True

    def pause(self):
        self.playing = False

    def toggle(self):
        self.pause() if self.playing else self.play()

    def stop(self):
        self.playing = False
        self._stop_decoder()
        self.position = 0.0
        if self.path:
            self._start_decoder(0.0)

    def seek(self, seconds):
        if not self.path:
            return
        was = self.playing
        self.playing = False
        self._start_decoder(max(0.0, min(seconds, max(0.0, self.duration - 0.5))))
        self.playing = was

    def close(self):
        self.playing = False
        self._stop_decoder()
        for z in self.zones:
            z.close()


def test_tone(device_name="", seconds=1.6):
    """Petit bip sur un périphérique, pour savoir quelle prise correspond à quelle sortie."""
    g = ToneGenerator(device_name)
    g.freq, g.db, g.ear, g.on = 660.0, -18.0, "both", True
    threading.Timer(seconds, g.close).start()
    return g


# ====================================================================== plusieurs lecteurs
MAX_SOURCES = 3
SOURCE_NAMES = ["Lecteur principal", "Lecteur 2", "Lecteur 3"]


def zone_source(cfg) -> int:
    try:
        return max(0, min(MAX_SOURCES - 1, int(cfg.get("source", 0) or 0)))
    except (TypeError, ValueError):
        return 0


class AudioHub:
    """Jusqu'à 3 lecteurs indépendants. Chaque sortie (haut-parleurs, casque Bluetooth, HDMI…)
    est rattachée à l'un d'eux par son réglage « source » : on peut ainsi écouter un titre
    sur le salon et un autre sur le casque, en même temps."""

    def __init__(self):
        self.players = [Player([]) for _ in range(MAX_SOURCES)]
        self.cfgs = []

    @property
    def main(self) -> Player:
        return self.players[0]

    def set_zones(self, cfgs, changed=None):
        """Répartit les sorties entre les lecteurs. `changed` : la sortie modifiée
        (seul son lecteur, ancien et nouveau, est relancé) ; None = tous."""
        self.cfgs = cfgs
        errors = []
        for i, p in enumerate(self.players):
            group = [c for c in cfgs if zone_source(c) == i]
            same = [id(c) for c in group] == [id(z.cfg) for z in p.zones]
            touched = changed is None or any(z.cfg is changed for z in p.zones) or any(c is changed for c in group)
            if not same or touched:
                try:
                    p.set_zones(group)
                except Exception as e:
                    errors.append(f"{SOURCE_NAMES[i]} : {e}")
        if errors:
            raise RuntimeError(" · ".join(errors))

    def zone_for(self, cfg) -> "Zone | None":
        for p in self.players:
            for z in p.zones:
                if z.cfg is cfg:
                    return z
        return None

    def player_for(self, cfg) -> Player:
        return self.players[zone_source(cfg)]

    def realign(self, cfg=None):
        for p in self.players:
            if cfg is None or any(z.cfg is cfg for z in p.zones):
                p.realign()

    def pause_all(self):
        for p in self.players:
            p.pause()

    def free_source(self):
        """Premier lecteur (2 ou 3) qui n'a encore aucune sortie, sinon None."""
        used = {zone_source(c) for c in self.cfgs}
        for i in range(1, MAX_SOURCES):
            if i not in used:
                return i
        return None

    def used_sources(self) -> list[int]:
        """Lecteurs qui ont au moins une sortie active."""
        return sorted({zone_source(c) for c in self.cfgs if c.get("enabled", True)} | {0})

    def label(self, i, short=False) -> str:
        devs = [device_label(c.get("device") or "") or "Sortie par défaut"
                for c in self.cfgs if zone_source(c) == i and c.get("enabled", True)]
        if short or not devs:
            return SOURCE_NAMES[i] + ("" if devs or i == 0 else " (aucune sortie)")
        return f"{SOURCE_NAMES[i]} · {', '.join(devs)}"

    def close(self):
        for p in self.players:
            p.close()


# ====================================================================== test auditif
class ToneGenerator:
    """Son pur pulsé (plus facile à détecter) sur une oreille, pour le test auditif."""

    def __init__(self, device_name=""):
        self.freq, self.db, self.ear, self.on = 1000.0, -80.0, "left", False
        self._phase = 0.0
        self._t = 0
        import sounddevice as sd
        dev = resolve_device(device_name)
        self.stream = sd.OutputStream(device=dev, samplerate=SR, channels=2, dtype="float32",
                                      blocksize=512, callback=self._cb)
        self.stream.start()

    def _cb(self, out, frames, t, status):
        if not self.on:
            out.fill(0); return
        amp = 10 ** (min(self.db, -6.0) / 20)            # plafond de sécurité : -6 dBFS
        k = np.arange(frames)
        ph = self._phase + 2 * math.pi * self.freq * k / SR
        self._phase = float((ph[-1] + 2 * math.pi * self.freq / SR) % (2 * math.pi))
        tt = (self._t + k) / SR
        self._t += frames
        env = np.clip(np.minimum((tt % 0.5) / 0.02, (0.3 - tt % 0.5) / 0.02), 0, 1)  # 300 ms on / 200 ms off
        s = (amp * env * np.sin(ph)).astype(np.float32)
        out.fill(0)
        if self.ear == "both":
            out[:, 0] = s; out[:, 1] = s
        else:
            out[:, 0 if self.ear == "left" else 1] = s

    def close(self):
        try:
            self.stream.stop(); self.stream.close()
        except Exception:
            pass
