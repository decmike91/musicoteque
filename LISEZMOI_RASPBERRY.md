# Musicothèque sur Raspberry Pi (ou autre carte) avec écran tactile

C'est le même logiciel que sur Windows (bibliothèque, rangement, identification, CD et YouTube → MP3,
profils audio, audiogramme, 3 sorties en même temps), avec une **interface tactile plein écran**
qui démarre toute seule comme une borne musicale.

## Matériel conseillé

| Élément | Conseil |
|---|---|
| Carte | **Raspberry Pi 5** (2 Go ou plus) ou **Pi 4** (2 Go ou plus). Pi 3 B+ possible, avec moins d'effets à la fois. Autres cartes possibles : Orange Pi 5, Rock Pi, Odroid, mini-PC x86 sous Debian, Ubuntu ou Armbian. |
| Écran tactile | **Raspberry Pi Touch Display 2** (7", 720×1280, à tourner de 90°), ou un écran tactile capacitif HDMI + USB de 7 à 10" (1024×600 ou 1280×800). Format minimum : 800×480. |
| Son | Prise jack du Pi 4 (qualité moyenne), **carte DAC HAT** (Raspberry Pi DAC+, HiFiBerry DAC+…), **DAC USB**, HDMI vers un ampli ou une TV, enceintes Bluetooth (avec le bureau). Jusqu'à **3 sorties en même temps**. |
| Stockage | Carte micro-SD de 32 Go et plus, ou mieux, un **SSD USB / NVMe** pour la musique. |
| Lecteur CD | Lecteur CD/DVD USB **avec alimentation séparée** (ou câble Y). Le port USB du Pi ne suffit pas toujours. |
| Alimentation | L'alimentation officielle (27 W pour le Pi 5). |

## Banana Pi et autres cartes
**Banana Pi BPI-M5** (Amlogic S905X3, 4 cœurs 64 bits, 4 Go) : elle convient.
- **Système :** installez **Armbian** en version Debian 12 « Bookworm » ou Ubuntu 24.04, de préférence une image minimale.
  Évitez les anciennes images Banana Pi (Ubuntu 20.04, Debian 10) : elles sont trop vieilles pour les bibliothèques nécessaires.
- **Installation :** la même que pour le Raspberry Pi, avec `./install_rpi.sh`.
- **Écran :** pas de connecteur d'écran DSI. Prenez un **écran tactile HDMI** dont le tactile passe par l'USB (7" 1024×600 par exemple).
- **Wi-Fi et Bluetooth :** pas intégrés. Ajoutez une clé USB Bluetooth reconnue par Linux, puis répondez « o » à la question Bluetooth de l'installateur.
- **Son :** la prise jack et le HDMI apparaissent comme « sortie 1 », « sortie 2 »… Le bouton **🔔 Bip de test** permet de les reconnaître.
  S'il n'y a aucun son sur la prise jack, ouvrez `alsamixer` et montez ou activez les réglages de sortie.

**Banana Pi BPI-M2 Berry** (Allwinner A40i, 32 bits, 1 Go) : déconseillée.
- **Processeur trop lent** pour les effets en temps réel sur plusieurs sorties.
- **Moteur d'effets audio :** il n'est pas proposé tout prêt pour les processeurs 32 bits.
- **Écran DSI :** son écran tactile est signalé comme ne fonctionnant pas.

## Bluetooth (casque, enceinte)
1. Pendant l'installation, répondez « o » à la question Bluetooth.
2. Dans l'application, ouvrez **Outils ▸ 📶 Bluetooth**.
3. Mettez l'appareil en mode appairage, choisissez-le dans la liste, et Musicothèque l'appaire et le connecte.
4. Dans **Son ▸ ＋**, ajoutez-le comme sortie. Vous pouvez le rattacher au **Lecteur 2** pour y écouter une autre musique.

## Installation

1. Installez **Raspberry Pi OS (64 bits)** avec Raspberry Pi Imager :
   - version **Lite** pour une borne dédiée (recommandé),
   - version avec bureau si le Pi sert aussi à autre chose.
2. Copiez le dossier `musicotheque` sur le Pi (clé USB, ou `scp`), puis dans un terminal :
   ```
   cd musicotheque
   chmod +x install_rpi.sh
   ./install_rpi.sh
   ```
3. Répondez aux deux questions :
   - **mode de démarrage** : 1 = borne plein écran, 2 = avec le bureau, 3 = rien,
   - **rotation de l'écran** : 90 pour le Touch Display 2 à l'horizontale, sinon 0.
4. Redémarrez : `sudo reboot`. Musicothèque s'ouvre directement en plein écran.

Pour l'essayer dans une fenêtre :
`.venv/bin/python touch_main.py --fenetre 800x480 --curseur`

## Utilisation au doigt

Barre du bas : **Lecture · Musique · File · Son · Outils**.

- **Lecture** : pochette, titre, avancer dans le morceau, ⏮ ⏯ ⏭, aléatoire 🔀, répétition 🔁, volume, vumètre.
- **Musique** : Artistes → Albums → Titres, Playlists, recherche 🔍 avec un clavier AZERTY à l'écran.
  - **Appui court** : lire.
  - **Appui long** : menu (lire ensuite, ajouter à la file ou à une playlist, identifier…).
- **File** : la liste de lecture en cours. Mélanger, retirer un titre, enregistrer en playlist.
- **Son** : une touche par sortie (1, 2, 3, ＋ pour en ajouter), puis quatre onglets :
  - **Égaliseur** 10 bandes et préréglages,
  - **Ambiance et effets** : ambiances, basses, surround, réverbération, balance,
  - **Audiogramme** : réglage au doigt et test auditif,
  - **Sortie et volume** : périphérique, voies, volume, retard d'alignement.

  **Profil** en haut : choisir un profil, 💾 enregistrer, ⋯ enregistrer sous, copier vers une autre sortie, renommer, supprimer.
- **Outils** :
  - Ranger une clé USB ou un disque,
  - Compléter les infos manquantes,
  - CD → MP3, YouTube → MP3,
  - Actualiser la bibliothèque, Éjecter un support,
  - **❓ Aide** : le manuel d'utilisation à l'écran, avec captures et liens entre chapitres,
  - Paramètres (clé AcoustID, dossier de la bibliothèque, qualité MP3, luminosité),
  - Éteindre ou redémarrer.

### Clé USB
Branchez une clé ou un disque. Musicothèque la détecte et propose :
- **Écouter** : lire la musique de la clé sans rien modifier,
- **Ranger dans ma bibliothèque** : copier la musique en la classant en `Artiste/Album (Année)/01 - Titre.mp3`.

Avant de retirer la clé, passez par **Outils ▸ Éjecter un support**.

Lors du rangement, deux interrupteurs sont activés par défaut :
- **Supprimer les doublons** : le meilleur exemplaire est gardé, les autres ne sont pas copiés, ou vont à la corbeille en mode Déplacer ;
- **WAV/OGG/WMA → MP3** : les fichiers WAV, OGG et WMA sont transformés en MP3.

### Une autre musique sur une autre sortie
1. **Son ▸ ＋** pour ajouter une sortie (par exemple le casque Bluetooth), puis **Sortie et volume ▸ 🎧 Lecteur ▸ Lecteur 2**.
2. Dans **Musique**, faites un appui long sur un titre, un album ou une playlist ▸ **🎧 Lire sur un autre lecteur**.
3. En haut de la page **Lecture**, une touche par lecteur (« Lecteur principal · Prise jack », « Lecteur 2 · Casque Bluetooth »)
   choisit celui qu'on pilote : titre, ⏯, volume, aléatoire.

Les pages Musique et File suivent le lecteur choisi : un appui court lance la musique sur ce lecteur.

Le plus simple pour créer un lecteur : **Son ▸ ＋ ▸ Ajouter un lecteur indépendant**. Le Lecteur 2, puis le Lecteur 3, est créé avec sa propre sortie en une seule étape. Jusqu'à 6 sorties en tout.

### Plusieurs sorties
Après avoir branché une nouvelle carte son ou un DAC USB : **Son ▸ Sortie et volume ▸ Rechercher les sorties audio**.
Les noms affichés sont simples : « Prise jack », « HDMI 1 », « USB : … », « HiFiBerry ».

Avec le bureau, chaque sortie PipeWire est proposée, y compris les enceintes Bluetooth appairées.
Sans bureau, il s'agit de chaque carte son.

## Taille de l'écran
L'interface tactile se met à l'échelle de l'écran, en paysage comme en portrait.
Elle a été vérifiée sur ces formats :
- 480×320 (écran 3,5"),
- 800×480,
- 1024×600,
- 720×1280 (portrait),
- 1280×800,
- 1920×1080.

Les boutons, les textes et les listes grandissent avec l'écran. La page Outils passe de 2 à 4 colonnes selon la largeur.

## Télécommande depuis un téléphone Android
Musicothèque se pilote depuis un téléphone sur le même Wi-Fi.
- **Ce qu'on peut faire :**
  - lecture, pause, titre suivant, avancer dans le morceau, volume, aléatoire, répétition ;
  - choisir de la musique (artistes, albums, titres, playlists, recherche) ;
  - gérer la file ;
  - régler chaque sortie : volume, lecteur diffusé, profil audio, activation ;
  - tout cela pour chacun des 3 lecteurs.
- **Application Android :** téléchargez **Musicotheque-Telecommande.apk** depuis l'onglet **Releases** du dépôt GitHub, sur le téléphone. Ouvrez le fichier et autorisez l'installation.
  L'application trouve le Raspberry Pi toute seule sur le Wi-Fi. Touchez-le, puis saisissez le code.
- **Sans application :** sur le Pi, ouvrez **Outils ▸ 📱 Télécommande** et scannez le QR code avec l'appareil photo du téléphone. Vous pouvez aussi ouvrir l'adresse affichée (`http://…:8080`) dans le navigateur.
- **Code d'appairage :** il est demandé une seule fois par téléphone. **Nouveau code** déconnecte tous les téléphones déjà appairés.
- **Couper la télécommande :** touchez le bouton « Activée » dans la même fenêtre.

## Bon à savoir
- Les profils audio et les réglages se trouvent dans `~/.config/Musicotheque/`. Un profil exporté depuis Windows (.json) s'importe tel quel.
- Une souris et un clavier restent possibles : le raccourci « Musicothèque (souris et clavier) » ouvre la version bureau.
- **Quitter** (Outils ▸ Paramètres) revient à la console. Si l'application plante, la borne la relance toute seule.
