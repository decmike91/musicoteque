"""Page « Son » tactile : sorties (jusqu'à 3), profils, égaliseur, ambiances, audiogramme."""
import copy

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget

from ..config import settings
from .. import profiles as P
from ..audio_engine import (EQ_PRESETS, EQ_LABELS, AMBIANCES, MAX_ZONES, CHANNEL_MODES, output_devices,
                            device_label, SOURCE_NAMES, zone_source)
from ..ui.sound_panel import AudiogramChart, HearingTestDialog, SoundPanel, DEFAULT_DEVICE
from ..ui.widgets import VUMeter
from .common import px, label, button, touch_slider, ask, info, choose, menu, Keyboard


class SoundPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.zones = SoundPanel._load_cfgs()
        try:
            app.hub.set_zones(self.zones)
        except Exception:
            pass
        self.cur = 0
        self._loading = False
        lay = QVBoxLayout(self); lay.setContentsMargins(px(8), px(6), px(8), px(4)); lay.setSpacing(px(6))

        # --- ligne 1 : sorties + profil
        r1 = QHBoxLayout(); r1.setSpacing(px(6))
        self.zone_row = QHBoxLayout(); self.zone_row.setSpacing(0)
        r1.addLayout(self.zone_row)
        r1.addStretch()
        self.b_profile = button("Profil", self.pick_profile); r1.addWidget(self.b_profile, 1)
        r1.addWidget(button("💾", self.save_profile, obj="icon"))
        r1.addWidget(button("⋯", self.profile_menu, obj="icon"))
        lay.addLayout(r1)
        # --- ligne 2 : onglets
        r2 = QHBoxLayout(); r2.setSpacing(0)
        self.tabs = {}
        for i, lab in enumerate(["🎚 Égaliseur", "🏛 Ambiance && effets", "👂 Audiogramme", "🔊 Sortie && volume"]):
            b = button(lab, lambda _=False, i=i: self.set_tab(i), obj="seg", checkable=True)
            self.tabs[i] = b; r2.addWidget(b, 1)
        lay.addLayout(r2)
        self.stack = QStackedWidget(); lay.addWidget(self.stack, 1)
        self.stack.addWidget(self._build_eq())
        self.stack.addWidget(self._build_fx())
        self.stack.addWidget(self._build_audiogram())
        self.stack.addWidget(self._build_output())
        self.save_timer = QTimer(self); self.save_timer.setSingleShot(True); self.save_timer.timeout.connect(settings.save)
        self.set_tab(0)
        self.rebuild_zone_buttons()
        self.show_zone(0)

    # ================================================================= construction
    def _build_eq(self):
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.b_eq_on = button("Égaliseur activé", self.edited, checkable=True)
        self.b_preset = button("Préréglage", self.pick_preset)
        top.addWidget(self.b_eq_on); top.addWidget(self.b_preset, 1)
        top.addWidget(button("Réinitialiser", lambda: self.apply_preset("Plat")))
        l.addLayout(top)
        g = QGridLayout(); g.setSpacing(px(2)); self.eq = []; self.eq_vals = []
        for i, lab in enumerate(EQ_LABELS):
            v = label("0", "dim"); v.setAlignment(Qt.AlignCenter)
            s = touch_slider(Qt.Vertical, -12, 12, 0)
            s.valueChanged.connect(lambda val, v=v: (v.setText(f"{val:+d}"), self.eq_edited()))
            n = label(lab); n.setAlignment(Qt.AlignCenter)
            g.addWidget(v, 0, i); g.addWidget(s, 1, i, Qt.AlignHCenter); g.addWidget(n, 2, i)
            self.eq.append(s)
        g.setRowStretch(1, 1)
        l.addLayout(g, 1)
        return w

    def _build_fx(self):
        w = QWidget(); l = QHBoxLayout(w); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(px(12))
        grid = QGridLayout(); grid.setSpacing(px(6)); self.amb_btns = {}
        for i, name in enumerate(AMBIANCES):
            b = button(name, lambda _=False, n=name: self.apply_ambiance(n), checkable=True)
            self.amb_btns[name] = b; grid.addWidget(b, i // 2, i % 2)
        l.addLayout(grid, 1)
        sl = QGridLayout(); sl.setSpacing(px(4)); self.fx = {}
        specs = [("bass", "Basses", 0, 12, lambda v: f"+{v} dB"), ("surround", "Surround", 0, 100, lambda v: f"{v} %"),
                 ("reverb_mix", "Réverbération", 0, 100, lambda v: f"{v} %"),
                 ("reverb_room", "Taille de la salle", 0, 100, lambda v: f"{v} %"),
                 ("balance", "Balance G / D", -100, 100, lambda v: "centre" if v == 0 else (f"G {-v} %" if v < 0 else f"D {v} %"))]
        for r, (key, name, lo, hi, fmt) in enumerate(specs):
            val = label("", "dim"); val.setFixedWidth(px(90))
            s = touch_slider(Qt.Horizontal, lo, hi)
            s.valueChanged.connect(lambda v, val=val, fmt=fmt: (val.setText(fmt(v)), self.edited()))
            sl.addWidget(label(name), r, 0); sl.addWidget(s, r, 1); sl.addWidget(val, r, 2)
            self.fx[key] = (s, val, fmt)
        l.addLayout(sl, 1)
        return w

    def _build_audiogram(self):
        w = QWidget(); l = QHBoxLayout(w); l.setContentsMargins(0, 0, 0, 0)
        self.chart = AudiogramChart(); self.chart.setMinimumSize(px(300), px(180))
        self.chart.changed.connect(self.edited)
        l.addWidget(self.chart, 3)
        side = QVBoxLayout(); side.setSpacing(px(6))
        self.b_ag_on = button("Correction activée", self.edited, checkable=True)
        self.b_right = button("Droite (O)", lambda: self.set_ear("right"), checkable=True)
        self.b_left = button("Gauche (X)", lambda: self.set_ear("left"), checkable=True)
        self.b_right.setStyleSheet("color:#f85149"); self.b_left.setStyleSheet("color:#58a6ff")
        self.strength_lbl = label("", "dim")
        self.strength = touch_slider(Qt.Horizontal, 0, 100, 50)
        self.strength.valueChanged.connect(lambda v: (self.strength_lbl.setText(
            f"Intensité : {v} %" + (" (demi-gain)" if v == 50 else "")), self.edited()))
        side.addWidget(self.b_ag_on)
        ears = QHBoxLayout(); ears.addWidget(self.b_right); ears.addWidget(self.b_left); side.addLayout(ears)
        side.addWidget(self.strength_lbl); side.addWidget(self.strength)
        act = QHBoxLayout()
        act.addWidget(button("👂 Test auditif", self.hearing_test, obj="primary"), 1)
        act.addWidget(button("⋯", self.ag_menu, obj="icon"))
        side.addLayout(act)
        side.addStretch()
        l.addLayout(side, 2)
        self.set_ear("right")
        return w

    def _build_output(self):
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(px(8))
        r = QHBoxLayout()
        self.b_on = button("Sortie active", self.toggle_enabled, checkable=True)
        self.b_device = button("Périphérique", self.pick_device)
        r.addWidget(self.b_on); r.addWidget(self.b_device, 1)
        l.addLayout(r)
        r = QHBoxLayout()
        self.b_source = button("Lecteur", self.pick_source)
        self.b_channels = button("Voies", self.pick_channels)
        self.b_delay = button("Retard", self.pick_delay)
        r.addWidget(self.b_source, 1); r.addWidget(self.b_channels, 1); r.addWidget(self.b_delay, 1)
        l.addLayout(r)
        r = QHBoxLayout()
        r.addWidget(label("Volume de cette sortie"))
        self.zvol = touch_slider(Qt.Horizontal, 0, 100, 100)
        self.zvol_lbl = label("100 %"); self.zvol_lbl.setFixedWidth(px(70))
        self.zvol.valueChanged.connect(self.zone_volume)
        r.addWidget(self.zvol, 1); r.addWidget(self.zvol_lbl)
        l.addLayout(r)
        self.vu = VUMeter(); self.vu.setMinimumHeight(px(40)); l.addWidget(self.vu)
        r = QHBoxLayout()
        r.addWidget(button("🔔 Bip de test", self.test_sound))
        r.addWidget(button("🔍 Rechercher les sorties", self.rescan_devices))
        self.b_remove = button("✕ Retirer cette sortie", self.remove_zone, obj="danger")
        r.addWidget(self.b_remove)
        l.addLayout(r)
        l.addStretch()
        return w

    # ================================================================= sorties
    def rebuild_zone_buttons(self):
        while self.zone_row.count():
            it = self.zone_row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.zone_btns = []
        for i, z in enumerate(self.zones):
            dev = device_label(z.get("device") or "") or "Défaut"
            tag = f" L{zone_source(z) + 1}" if zone_source(z) else ""
            # nom du périphérique seulement s'il y a peu de sorties (sinon : numéro + lecteur)
            text = f"{i + 1} · {dev[:12]}{tag}" if len(self.zones) <= 2 else f"{i + 1}{tag}"
            b = button(text, lambda _=False, i=i: self.show_zone(i), obj="seg", checkable=True)
            if not z.get("enabled", True):
                b.setStyleSheet("color:#6e7681")
            self.zone_btns.append(b); self.zone_row.addWidget(b)
        if len(self.zones) < MAX_ZONES:
            self.zone_row.addWidget(button("＋", self.add_menu, obj="seg"))
        for i, b in enumerate(self.zone_btns):
            b.setChecked(i == self.cur)

    def cfg(self):
        return self.zones[self.cur]

    def show_zone(self, i):
        self.cur = max(0, min(i, len(self.zones) - 1))
        for k, b in enumerate(self.zone_btns):
            b.setChecked(k == self.cur)
        self.load_ui()

    def set_tab(self, i):
        self.stack.setCurrentIndex(i)
        for k, b in self.tabs.items():
            b.setChecked(k == i)

    def add_menu(self):
        free = self.app.hub.free_source()
        acts = [("🔊  Ajouter une sortie (même musique que le lecteur principal)", lambda: self.add_zone(0))]
        if free is not None:
            acts.append((f"🎧  Ajouter un lecteur indépendant ({SOURCE_NAMES[free]} : une autre musique)", self.add_player))
        else:
            acts.append(("🎧  Les 3 lecteurs sont déjà utilisés (choisissez « Lecteur » sur une sortie)", lambda: None))
        menu(self, "Ajouter", acts)

    def add_player(self):
        """Nouveau lecteur indépendant (2 puis 3) avec sa propre sortie, en une seule étape."""
        src = self.app.hub.free_source()
        if src is None:
            info(self, "Lecteurs", "Les 3 lecteurs sont déjà utilisés."); return
        if len(self.zones) >= MAX_ZONES:
            info(self, "Lecteurs", f"Nombre maximal de sorties atteint ({MAX_ZONES})."); return
        self.add_zone(src, quiet=True)
        self.pick_device()
        self.app.set_source(src)
        self.app.toast.show_msg(f"{SOURCE_NAMES[src]} prêt : choisissez sa musique (page Musique)", 6000)

    def add_zone(self, source=0, quiet=False):
        if len(self.zones) >= MAX_ZONES:
            info(self, "Sorties", f"Nombre maximal de sorties atteint ({MAX_ZONES})."); return
        used = {z.get("device") for z in self.zones}
        free = [d for d in output_devices() if d not in used]
        self.zones.append({"enabled": True, "device": free[0] if free else "", "volume": 1.0, "delay_ms": 0,
                           "channels": "stereo", "source": source,
                           "profile_name": "Par défaut", "profile": P.normalize({})})
        self.cur = len(self.zones) - 1
        self.apply_structure(self.zones[-1]); self.rebuild_zone_buttons(); self.show_zone(self.cur)
        self.set_tab(3)
        if not quiet:
            self.app.toast.show_msg(f"Sortie {self.cur + 1} ajoutée : choisissez son périphérique")

    def remove_zone(self):
        if len(self.zones) <= 1:
            info(self, "Sorties", "Il faut garder au moins une sortie."); return
        if ask(self, "Retirer la sortie", f"Retirer la sortie {self.cur + 1} ?") != 0:
            return
        removed = self.zones.pop(self.cur); self.cur = 0
        self.apply_structure(removed); self.rebuild_zone_buttons(); self.show_zone(0)

    def toggle_enabled(self):
        self.cfg()["enabled"] = self.b_on.isChecked()
        self.apply_structure(self.cfg()); self.rebuild_zone_buttons(); self.load_ui()

    def pick_device(self):
        names = output_devices()
        opts = [(DEFAULT_DEVICE, "")] + [(device_label(n), n) for n in names]
        v = choose(self, "Périphérique de la sortie", opts, self.cfg().get("device", ""))
        if v is not None:
            self.cfg()["device"] = v
            self.apply_structure(self.cfg()); self.rebuild_zone_buttons(); self.load_ui()

    def pick_source(self):
        opts = [(f"{n} — {'musique principale' if i == 0 else 'une autre musique, indépendante'}", i)
                for i, n in enumerate(SOURCE_NAMES)]
        v = choose(self, "Quelle musique diffuser sur cette sortie ?", opts, zone_source(self.cfg()))
        if v is not None and v != zone_source(self.cfg()):
            self.cfg()["source"] = v
            self.apply_structure(self.cfg()); self.rebuild_zone_buttons(); self.load_ui()
            if v:
                self.app.toast.show_msg(f"Sortie {self.cur + 1} → {SOURCE_NAMES[v]} : choisissez sa musique "
                                        "(Musique ▸ appui long ▸ Lire sur un autre lecteur)", 6000)

    def pick_channels(self):
        v = choose(self, "Voies", [(lab, k) for k, lab in CHANNEL_MODES.items()], self.cfg().get("channels", "stereo"))
        if v:
            self.cfg()["channels"] = v; self.load_ui(); self.save()

    def pick_delay(self):
        vals = [0, 10, 20, 30, 40, 50, 75, 100, 125, 150, 175, 200, 250, 300, 400, 500]
        v = choose(self, "Retard de cette sortie (pour l'aligner sur les autres)",
                   [(f"{x} ms", x) for x in vals], int(self.cfg().get("delay_ms", 0)))
        if v is not None:
            self.cfg()["delay_ms"] = v
            self.app.hub.realign(self.cfg()); self.load_ui(); self.save()

    def zone_volume(self, v):
        self.zvol_lbl.setText(f"{v} %")
        if not self._loading:
            self.cfg()["volume"] = v / 100; self.save()

    def test_sound(self):
        from ..audio_engine import test_tone
        try:
            test_tone(self.cfg().get("device", ""))
        except Exception as e:
            info(self, "Test", f"Impossible d'utiliser ce périphérique : {e}")

    def rescan_devices(self):
        try:
            from .. import setup_audio, audio_engine
            r = setup_audio.install()
            audio_engine._labels = None
            info(self, "Sorties audio", f"{len(r['sorties'])} sortie(s) trouvée(s) :\n" + "\n".join(r["sorties"].values()))
        except Exception as e:
            info(self, "Sorties audio", f"Recherche impossible : {e}")
        self.rebuild_zone_buttons(); self.load_ui()

    def apply_structure(self, changed=None):
        try:
            self.app.hub.set_zones(self.zones, changed)
        except Exception as e:
            self.app.toast.show_msg(str(e), 6000)
        self.save()
        self.app.sources_updated()

    def zone_obj(self, i=None):
        return self.app.hub.zone_for(self.zones[self.cur if i is None else i])

    def apply_profile_live(self, i=None):
        z = self.zone_obj(i)
        if z is not None:
            z.apply_profile(self.zones[self.cur if i is None else i]["profile"])

    def save(self):
        settings["zones"] = self.zones
        self.save_timer.start(800)

    # ================================================================= affichage / lecture des réglages
    def load_ui(self):
        self._loading = True
        c = self.cfg(); p = P.normalize(c.get("profile")); c["profile"] = p
        self.b_eq_on.setChecked(p["eq_enabled"])
        for s, g in zip(self.eq, p["eq_gains"]):
            s.setValue(int(round(g)))
        self.b_preset.setText(f"Préréglage : {p['eq_preset']}")
        for n, b in self.amb_btns.items():
            b.setChecked(n == p["ambiance"])
        for key, (s, val, fmt) in self.fx.items():
            v = p[key] if key == "bass" else round(p[key] * 100)
            s.setValue(int(v)); val.setText(fmt(int(v)))
        ag = p["audiogram"]
        self.b_ag_on.setChecked(bool(ag["enabled"])); self.chart.set_values(ag["left"], ag["right"])
        self.strength.setValue(round(ag["strength"] * 100))
        self.strength_lbl.setText(f"Intensité : {self.strength.value()} %")
        self.b_on.setChecked(c.get("enabled", True))
        self.b_on.setText("Sortie active" if c.get("enabled", True) else "Sortie coupée")
        self.b_device.setText(f"Périphérique : {device_label(c.get('device') or '') or DEFAULT_DEVICE}")
        self.b_channels.setText(f"Voies : {CHANNEL_MODES.get(c.get('channels', 'stereo'))}")
        self.b_source.setText(f"🎧 {SOURCE_NAMES[zone_source(c)]}")
        self.b_delay.setText(f"Retard : {int(c.get('delay_ms', 0))} ms")
        self.zvol.setValue(round(c.get("volume", 1.0) * 100)); self.zvol_lbl.setText(f"{self.zvol.value()} %")
        self.b_remove.setEnabled(len(self.zones) > 1)
        self._loading = False
        self._update_profile_btn()

    def read_ui(self):
        c = self.cfg(); p = P.normalize(c.get("profile"))
        p["eq_enabled"] = self.b_eq_on.isChecked()
        p["eq_gains"] = [float(s.value()) for s in self.eq]
        for key, (s, val, fmt) in self.fx.items():
            p[key] = s.value() if key == "bass" else s.value() / 100
        p["audiogram"].update(enabled=self.b_ag_on.isChecked(), left=list(self.chart.left),
                              right=list(self.chart.right), strength=self.strength.value() / 100)
        return p

    def edited(self, *_):
        if self._loading:
            return
        c = self.cfg()
        c["profile"] = self.read_ui()
        self.apply_profile_live()
        self._update_profile_btn(); self.save()

    def eq_edited(self):
        if self._loading:
            return
        gains = [float(s.value()) for s in self.eq]
        p = self.cfg()["profile"]
        if gains != [float(x) for x in EQ_PRESETS.get(p.get("eq_preset"), [])]:
            p["eq_preset"] = "Personnalisé"; self.b_preset.setText("Préréglage : Personnalisé")
        self.edited()

    def pick_preset(self):
        v = choose(self, "Préréglage de l'égaliseur", [(n, n) for n in EQ_PRESETS], self.cfg()["profile"]["eq_preset"])
        if v:
            self.apply_preset(v)

    def apply_preset(self, name):
        self.cfg()["profile"]["eq_preset"] = name
        self._loading = True
        for sl, g in zip(self.eq, EQ_PRESETS[name]):
            sl.setValue(int(g))
        self._loading = False
        self.b_preset.setText(f"Préréglage : {name}")
        self.edited()

    def apply_ambiance(self, name):
        a = AMBIANCES.get(name)
        self.cfg()["profile"]["ambiance"] = name
        self._loading = True
        for n, b in self.amb_btns.items():
            b.setChecked(n == name)
        if a is None:
            self.fx["reverb_mix"][0].setValue(0); self.fx["surround"][0].setValue(0)
        else:
            room, mix, damp, sur = a
            self.fx["reverb_room"][0].setValue(round(room * 100)); self.fx["reverb_mix"][0].setValue(round(mix * 100))
            self.fx["surround"][0].setValue(round(sur * 100))
        self._loading = False
        self.edited()

    def set_ear(self, ear):
        self.chart.edit = ear; self.chart.update()
        self.b_right.setChecked(ear == "right"); self.b_left.setChecked(ear == "left")

    def ag_menu(self):
        n = len(P.AUDIOGRAM_FREQS)
        menu(self, "Audiogramme", [
            ("Copier oreille droite → gauche", lambda: (self.chart.set_values(list(self.chart.right), self.chart.right), self.edited())),
            ("Copier oreille gauche → droite", lambda: (self.chart.set_values(self.chart.left, list(self.chart.left)), self.edited())),
            ("Remettre à zéro", lambda: (self.chart.set_values([0] * n, [0] * n), self.edited())),
        ])

    def hearing_test(self):
        self.app.hub.pause_all()
        d = HearingTestDialog(self.cfg().get("device", ""), getattr(self.app, "tone_factory", None), self)
        d.setWindowState(Qt.WindowFullScreen)
        if d.exec() and d.result:
            self.chart.set_values(d.result["left"], d.result["right"])
            self.b_ag_on.setChecked(True); self.edited()
            self.app.toast.show_msg("Audiogramme mis à jour — pensez à enregistrer le profil 💾")

    # ================================================================= profils
    def _update_profile_btn(self):
        c = self.cfg(); name = c.get("profile_name", "Par défaut")
        modified = P.load_profile(name) != P.normalize(c["profile"])
        self.b_profile.setText(f"Profil : {name}" + ("  •" if modified else ""))

    def pick_profile(self):
        name = choose(self, "Profil audio de la sortie", [(n, n) for n in P.list_profiles()],
                      self.cfg().get("profile_name"))
        if name:
            self.cfg()["profile_name"] = name
            self.cfg()["profile"] = P.load_profile(name)
            self.apply_profile_live()
            self.load_ui(); self.save()

    def save_profile(self):
        name = self.cfg().get("profile_name", "Par défaut")
        if P.is_builtin(name):
            self.save_as(); return
        P.save_profile(name, self.cfg()["profile"])
        self._update_profile_btn(); self.save()
        self.app.toast.show_msg(f"Profil « {name} » enregistré")

    def save_as(self):
        name = Keyboard.get(self, "Nom du profil audio", f"Mon profil {len(P.list_profiles()) + 1}")
        if not name or not name.strip():
            return
        name = name.strip()
        if name in P.list_profiles() and ask(self, "Profil", f"Remplacer le profil « {name} » ?") != 0:
            return
        P.save_profile(name, self.cfg()["profile"])
        self.cfg()["profile_name"] = name
        self._update_profile_btn(); self.save()
        self.app.toast.show_msg(f"Profil « {name} » enregistré")

    def profile_menu(self):
        name = self.cfg().get("profile_name", "Par défaut")
        acts = [("💾  Enregistrer sous un nouveau nom…", self.save_as)]
        others = [i for i in range(len(self.zones)) if i != self.cur]
        for i in others:
            acts.append((f"📋  Copier ces réglages vers la sortie {i + 1}", lambda i=i: self.copy_to(i)))
        if not P.is_builtin(name):
            acts.append(("✏  Renommer le profil…", self.rename_profile))
            acts.append(("🗑  Supprimer le profil", self.delete_profile))
        acts.append(("↺  Revenir au profil enregistré", lambda: (self.cfg().__setitem__("profile", P.load_profile(name)),
                                                                 self.edited_from_cfg())))
        menu(self, f"Profil « {name} »", acts)

    def edited_from_cfg(self):
        self.apply_profile_live()
        self.load_ui(); self.save()

    def copy_to(self, i):
        self.zones[i]["profile"] = copy.deepcopy(self.cfg()["profile"])
        self.zones[i]["profile_name"] = self.cfg().get("profile_name")
        self.apply_profile_live(i)
        self.save(); self.app.toast.show_msg(f"Réglages copiés vers la sortie {i + 1}")

    def rename_profile(self):
        old = self.cfg().get("profile_name")
        name = Keyboard.get(self, "Nouveau nom du profil", old)
        if name and name.strip() and name.strip() != old:
            P.save_profile(name.strip(), P.load_profile(old)); P.delete_profile(old)
            for z in self.zones:
                if z.get("profile_name") == old:
                    z["profile_name"] = name.strip()
            self._update_profile_btn(); self.save()

    def delete_profile(self):
        name = self.cfg().get("profile_name")
        if ask(self, "Supprimer", f"Supprimer le profil « {name} » ?\n(les réglages de la sortie sont conservés)") == 0:
            P.delete_profile(name)
            for z in self.zones:
                if z.get("profile_name") == name:
                    z["profile_name"] = "Par défaut"
            self._update_profile_btn(); self.save()

    def remote_set_output(self, i, d):
        """Réglage d'une sortie depuis la télécommande (appelé dans le fil principal)."""
        c = self.zones[i]
        structural = False
        if "volume" in d:
            c["volume"] = max(0.0, min(1.0, float(d["volume"])))
        if "enabled" in d:
            c["enabled"] = bool(d["enabled"]); structural = True
        if "source" in d:
            c["source"] = max(0, min(2, int(d["source"]))); structural = True
        if "profile" in d and d["profile"] in P.list_profiles():
            c["profile_name"] = d["profile"]; c["profile"] = P.load_profile(d["profile"])
            if not structural:
                self.apply_profile_live(i)
        if structural:
            self.apply_structure(c); self.rebuild_zone_buttons()
        if i == self.cur:
            self.load_ui()
        self.save()

    def tick(self):
        if self.stack.currentIndex() == 3:
            z = self.zone_obj()
            self.vu.set_levels(*(z.levels if z is not None and z.player.playing else (0, 0, 0, 0)))
