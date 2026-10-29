#!/bin/bash
# Installation de Musicothèque sur Raspberry Pi (ou autre carte / mini-PC sous Debian, Ubuntu, Armbian).
# Utilisation :   chmod +x install_rpi.sh && ./install_rpi.sh
set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ "$(id -u)" -eq 0 ]; then
  echo "Lancez ce script SANS sudo (il demandera le mot de passe quand il le faut) : ./install_rpi.sh"; exit 1
fi
ME="$(id -un)"
step() { echo; echo "=== $* ==="; }

step "1/6  Paquets du système (quelques minutes)"
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip ffmpeg libportaudio2 libasound2-plugins alsa-utils \
     libchromaprint-tools udisks2 fonts-noto-color-emoji fonts-dejavu-core avahi-daemon
# Qt pour Python (fourni par la distribution : plus rapide et plus fiable sur ARM)
sudo apt-get install -y python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtwidgets \
  || echo "PySide6 n'est pas dans les dépôts : il sera installé avec pip."
# extraction de CD
sudo apt-get install -y cyanrip || echo "cyanrip indisponible : l'extraction de CD ne fonctionnera pas."
# sortie PipeWire par périphérique (bureau Raspberry Pi OS, enceintes Bluetooth)
sudo apt-get install -y pipewire-alsa 2>/dev/null || true
sudo usermod -aG audio,video,cdrom,plugdev "$ME" || true

read -rp "Utiliser un casque ou des enceintes Bluetooth ? [o/N] : " BT
if [ "$BT" = "o" ] || [ "$BT" = "O" ]; then
  # PipeWire gère le Bluetooth audio ; chaque appareil devient une sortie de Musicothèque
  sudo apt-get install -y bluez pipewire pipewire-pulse wireplumber pipewire-alsa libspa-0.2-bluetooth pulseaudio-utils
  sudo systemctl enable --now bluetooth || true
  systemctl --user enable --now pipewire pipewire-pulse wireplumber 2>/dev/null || true
fi

step "2/6  Bibliothèques Python"
python3 -m venv --system-site-packages "$APP_DIR/.venv"
PY="$APP_DIR/.venv/bin/python"
"$PY" -m pip install --upgrade pip
"$PY" -m pip install numpy pedalboard sounddevice mutagen pyacoustid musicbrainzngs requests yt-dlp send2trash qrcode
"$PY" -c "import PySide6" 2>/dev/null || "$PY" -m pip install PySide6

step "3/6  Sorties audio"
cd "$APP_DIR" && "$PY" -m app.setup_audio

step "Télécommande : le téléphone trouve Musicothèque tout seul sur le Wi-Fi"
# annonce réseau (mDNS) lue par l'application Android ; adresse aussi joignable en http://$(hostname).local:8080
sudo mkdir -p /etc/avahi/services
sudo tee /etc/avahi/services/musicotheque.service >/dev/null <<'EOS'
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">Musicothèque (%h)</name>
  <service><type>_musicotheque._tcp</type><port>8080</port></service>
  <service><type>_http._tcp</type><port>8080</port></service>
</service-group>
EOS
sudo systemctl enable --now avahi-daemon 2>/dev/null || true
sudo systemctl restart avahi-daemon 2>/dev/null || true

step "4/6  Luminosité de l'écran réglable depuis l'application"
echo 'SUBSYSTEM=="backlight", RUN+="/bin/chmod 666 /sys/class/backlight/%k/brightness"' | \
  sudo tee /etc/udev/rules.d/90-musicotheque-ecran.rules >/dev/null
sudo udevadm control --reload-rules || true

step "5/6  Raccourcis"
mkdir -p ~/.local/share/applications ~/.local/bin
cat > ~/.local/share/applications/musicotheque.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Musicothèque (tactile)
Exec=$PY $APP_DIR/touch_main.py
Icon=multimedia-audio-player
Categories=AudioVideo;Audio;Player;
EOF
cat > ~/.local/share/applications/musicotheque-bureau.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Musicothèque (souris et clavier)
Exec=$PY $APP_DIR/main.py
Icon=multimedia-audio-player
Categories=AudioVideo;Audio;Player;
EOF

step "6/6  Démarrage automatique"
echo "Comment voulez-vous lancer Musicothèque ?"
echo "  1) Borne plein écran au démarrage (recommandé avec Raspberry Pi OS Lite, sans bureau)"
echo "  2) Au démarrage du bureau (Raspberry Pi OS avec bureau)"
echo "  3) Ne rien démarrer automatiquement"
read -rp "Votre choix [1] : " MODE; MODE=${MODE:-1}
ROT=0
if [ "$MODE" != "3" ]; then
  echo "Rotation de l'écran : 0, 90, 180 ou 270 degrés"
  echo "  (écran officiel Raspberry Pi Touch Display 2 : 90 pour le mettre à l'horizontale)"
  read -rp "Rotation [0] : " ROT; ROT=${ROT:-0}
fi

if [ "$MODE" = "1" ]; then
  sudo apt-get install -y cage qt6-wayland wlr-randr
  cat > ~/.local/bin/musicotheque-borne <<EOF
#!/bin/sh
# Lance Musicothèque en plein écran (compositeur « cage »). Relance automatique en cas de plantage.
export QT_QPA_PLATFORM=wayland
MARQUE="\$HOME/.config/Musicotheque/.quitter"
rm -f "\$MARQUE"
while true; do
  cage -s -- sh -c 'if [ "$ROT" != "0" ]; then for o in \$(wlr-randr | grep -E "^[A-Za-z]" | cut -d" " -f1); do wlr-randr --output "\$o" --transform $ROT; done; fi; exec "$PY" "$APP_DIR/touch_main.py"'
  [ -f "\$MARQUE" ] && { rm -f "\$MARQUE"; break; }
  sleep 2
done
EOF
  chmod +x ~/.local/bin/musicotheque-borne
  # démarrage sur la console 1 après connexion automatique
  touch ~/.bash_profile
  sed -i '/# >>> musicotheque/,/# <<< musicotheque/d' ~/.bash_profile
  cat >> ~/.bash_profile <<'EOF'
# >>> musicotheque
if [ -z "$WAYLAND_DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then exec ~/.local/bin/musicotheque-borne; fi
# <<< musicotheque
EOF
  if command -v raspi-config >/dev/null; then
    sudo raspi-config nonint do_boot_behaviour B2   # console + connexion automatique
  else
    sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
    printf '[Service]\nExecStart=\nExecStart=-/sbin/agetty --autologin %s --noclear %%I $TERM\n' "$ME" | \
      sudo tee /etc/systemd/system/getty@tty1.service.d/autologin.conf >/dev/null
    sudo systemctl set-default multi-user.target
  fi
  echo "Borne configurée : redémarrez (sudo reboot) pour lancer Musicothèque en plein écran."
elif [ "$MODE" = "2" ]; then
  mkdir -p ~/.config/autostart
  cp ~/.local/share/applications/musicotheque.desktop ~/.config/autostart/
  if [ "$ROT" != "0" ]; then
    echo "Pour la rotation sur le bureau : menu Préférences ▸ Configuration de l'écran ▸ Orientation."
  fi
  echo "Musicothèque démarrera avec le bureau (et se trouve dans le menu Son et vidéo)."
fi

echo
echo "Installation terminée ✓"
echo "Essai immédiat :  $PY $APP_DIR/touch_main.py --fenetre 800x480 --curseur"
echo "Après avoir branché une nouvelle carte son :  cd $APP_DIR && $PY -m app.setup_audio"
