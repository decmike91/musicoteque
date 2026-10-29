# Musicothèque

Logiciel pour référencer, ranger, identifier, convertir et écouter votre musique.

- **Windows** : ce document.
- **Raspberry Pi ou autre carte avec écran tactile** : voir **LISEZMOI_RASPBERRY.md**.

## Installation (une seule fois)

1. Décompressez le dossier où vous voulez (par ex. `C:\Programmes\Musicotheque`).
2. Double-cliquez sur **installer.bat**. Il installe automatiquement :
   - Python et les bibliothèques nécessaires,
   - **ffmpeg** (lecture et conversion), **fpcalc** (empreinte audio), **cyanrip** (extraction de CD).
3. Un raccourci **Musicothèque** apparaît sur le Bureau (ou lancez `lancer.bat`).

Optionnel : `creer_exe.bat` fabrique un programme autonome `dist\Musicotheque\Musicotheque.exe`
à copier sur un autre PC sans rien installer.

### Activer la reconnaissance « façon Shazam »
La reconnaissance par empreinte sonore utilise AcoustID + MusicBrainz (gratuits).
1. Créez une clé gratuite sur https://acoustid.org/new-application
2. Collez-la dans **Fichier ▸ Paramètres ▸ Clé AcoustID**.

Sans clé, le logiciel identifie quand même à partir du nom de fichier (moins fiable).

## Ce que fait le logiciel

| Fonction | Où |
|---|---|
| Ranger et classer un disque dur, une clé USB ou un dossier | **Ranger ▸ Ranger / classer un emplacement** (Ctrl+R) |
| Référencer un dossier sans le réorganiser | Fichier ▸ Ajouter un dossier (Ctrl+O) |
| Classement par artiste, album, titres incomplets | Panneau de gauche |
| Retrouver les titres et compléter les infos (titre, artiste, album, année, genre, pochette) | Clic droit ▸ Identifier (Ctrl+I) ou **Identifier ▸ Compléter automatiquement** |
| Modifier les infos à la main (un ou plusieurs fichiers, pochette) | Clic droit ▸ Modifier les informations (Ctrl+E) |
| CD audio → MP3 avec titres et pochette | Convertir ▸ CD audio → MP3 |
| Lien YouTube → MP3 (vidéo ou playlist) | Convertir ▸ Lien YouTube → MP3 (Ctrl+Y) |
| Playlists (créer, ajouter, M3U import/export) | Menu Playlists, clic droit sur les titres |
| Lecture aléatoire, répétition (tout / un titre) | Boutons 🔀 et 🔁 du lecteur |

### Le rangement, étape par étape
1. Choisissez l'emplacement (ex. `E:\` pour une clé USB).
2. Choisissez où ranger (par défaut `E:\Musique classée`, ou « Ma bibliothèque »).
3. Option : cochez *Identifier en ligne les titres incomplets* pour retrouver d'abord les infos manquantes.
4. **Analyser** : un aperçu montre chaque fichier et sa future place. Rien n'est encore modifié.
5. **Ranger** : les fichiers sont renommés et classés en `Artiste\Album (Année)\01 - Titre.mp3`.
   Les doublons exacts vont dans `_Doublons`, les dossiers vides sont supprimés.
6. Une erreur ? **Annuler le dernier rangement** remet en place les fichiers déplacés.
   Les fichiers supprimés se récupèrent dans la **Corbeille**.

### Fichiers protégés (« accès refusé »)
Un fichier qui ne peut pas être lu, déplacé ou modifié n'arrête plus le rangement. Il est signalé, laissé à sa place, et le rangement passe au suivant. C'est le cas d'un fichier ouvert dans un autre programme, d'un dossier protégé ou d'une clé verrouillée.
- La **lecture seule** (fréquente sur les fichiers copiés d'un CD) est retirée automatiquement quand c'est possible.
- Si un fichier a pu être copié mais pas retiré de la clé, il est dans la bibliothèque et l'original reste sur la clé, avec un message.
- En fin de rangement, la liste **« Fichiers non traités »** indique chaque fichier ignoré et pourquoi. Relancez le rangement après avoir fermé le programme qui l'utilise.

### Doublons et fichiers WAV
Deux options du rangement, cochées par défaut :
- **Supprimer automatiquement les doublons.**
  - Sont des doublons : les copies identiques, et le même morceau en plusieurs fichiers (même artiste, même titre, durée proche).
  - Le **meilleur exemplaire est gardé** : sans perte (WAV/FLAC) d'abord, puis le meilleur débit, puis celui qui a une pochette et des infos complètes.
  - Les autres vont à la **Corbeille**. Sur une clé USB, Windows n'a pas de corbeille : ils y sont supprimés définitivement.
  - Un morceau déjà présent dans la bibliothèque n'est pas recopié. S'il arrive en meilleure qualité, il remplace l'ancien.
  - Ne sont pas considérés comme des doublons : les versions « Live » ou de durée différente, et le même titre présent sur deux albums différents (album et best-of), pour que chaque album reste complet.
  - En mode **Copier**, rien n'est supprimé sur le support d'origine : les doublons ne sont simplement pas copiés.
- **Transformer les WAV, OGG et WMA en MP3**, en gardant les informations et la pochette :
  - les WAV sont convertis à la qualité choisie dans Paramètres (320 kbit/s par défaut) ;
  - les OGG et WMA, déjà compressés, sont convertis un peu au-dessus de leur qualité d'origine (192 kbit/s au minimum), pour ne pas gonfler les fichiers inutilement.
  En mode Déplacer, le fichier d'origine va à la Corbeille une fois la conversion réussie.
  Un WMA protégé contre la copie (DRM, acheté sur d'anciens magasins en ligne) ne peut pas être converti : il est laissé tel quel, avec un message.

Pour nettoyer une bibliothèque déjà rangée : menu **Ranger ▸ Supprimer les doublons et transformer les WAV / OGG / WMA en MP3**.

### Le lecteur
- Volume (bouton rotatif), muet, barre de progression, vumètre stéréo avec maintien de crête.
- **Égaliseur 10 bandes** (31 Hz à 16 kHz) avec préréglages : Rock, Pop, Jazz, Classique, Électro,
  Hip-Hop, Voix, Basses +, Aigus +, Loudness, Acoustique.
- **Ambiances préprogrammées** : Petite pièce, Salon, Club, Salle de concert, Live / Stade, Cathédrale, Studio.
- Réglages : renfort de basses, **surround** (élargissement spatial), **réverbération** et taille de salle, **balance**.
- Tous les réglages sont mémorisés. Ctrl+G affiche/masque le panneau **Son**.

### Plusieurs sorties en même temps (2 ou 3 périphériques)
Dans le panneau Son, **＋ Ajouter une sortie** (jusqu'à 3) : haut-parleurs, casque, enceinte Bluetooth, écran HDMI…
Chaque sortie a son propre onglet avec :
- son **périphérique**, son **volume**, ses **voies** (stéréo, inversée, mono, gauche seule, droite seule),
- son **égaliseur**, son **ambiance** et ses effets,
- son **audiogramme**,
- un **retard** (en ms) pour aligner les sorties. Une enceinte Bluetooth a souvent 150 à 250 ms de retard :
  retardez d'autant les autres sorties.

Les sorties restent synchronisées automatiquement, même si les cartes son n'ont pas exactement la même horloge.

### Écouter une autre musique sur une autre sortie (casque Bluetooth, autre pièce…)
Chaque sortie peut diffuser la musique du **lecteur principal**, ou celle du **Lecteur 2** ou du **Lecteur 3**.
Ces deux lecteurs supplémentaires sont indépendants : chacun a sa file, ses commandes, son volume et ses réglages aléatoire et répétition.
1. Panneau **Son** ▸ **＋ Ajouter une sortie** ▸ choisissez le périphérique (par exemple le casque Bluetooth, une fois appairé dans Windows).
2. Dans **Lecteur**, choisissez **Lecteur 2**.
3. Clic droit sur des titres, un album, un artiste ou une playlist ▸ **🎧 Lire sur un autre lecteur** ▸ Lecteur 2 ▸ Lire maintenant (ou Ajouter à sa file).
4. Le panneau **Autres lecteurs**, à droite, pilote le lecteur 2 : ⏮ ⏯ ⏭, aléatoire, avancer dans le morceau, volume, file.
   Il s'affiche aussi par le menu **Son ▸ Afficher les autres lecteurs**.

Raccourci : **＋ Ajouter un lecteur**, dans le panneau Son ou dans le menu Son, crée le Lecteur 2 puis le Lecteur 3, chacun avec sa sortie. Jusqu'à 6 sorties en tout.

Plusieurs sorties peuvent écouter le même lecteur, par exemple le salon et la cuisine sur le lecteur principal, et le casque sur le lecteur 2.

### Profils audio personnalisés
En haut de chaque sortie : choisissez un profil, réglez, puis **Enregistrer** ou **Enregistrer sous…**.
Un profil contient l'égaliseur, l'ambiance, les effets, la balance **et l'audiogramme**.
Menu **⋯** : renommer, supprimer, importer/exporter (fichier .json à partager), copier vers une autre sortie.
Profils fournis : Par défaut, Soirée, Écoute douce (nuit), Concert.

### Audiogramme personnalisé
Onglet **Audiogramme** de chaque sortie :
- Saisissez les valeurs de votre audiogramme (ORL, audioprothésiste) dans le tableau, ou faites glisser
  les points du graphique. Oreille droite = O rouge, oreille gauche = X bleue.
- Cochez **Corriger le son d'après cet audiogramme**. Les fréquences moins bien entendues sont renforcées,
  oreille par oreille (règle du demi-gain par défaut, intensité et correction maximale réglables).
- **Faire un test auditif** : un bip monte doucement, appuyez sur *J'entends* (ou Espace) dès que vous le percevez.
  Avant le test, réglez le volume de Windows à votre niveau habituel et ne le changez plus. Le test dure 5 à 8 minutes.
  Le résultat est indicatif et ne remplace pas un examen par un professionnel.

## Affichage et taille de l'écran
- La fenêtre s'adapte à l'écran (portable 1366×768, écran Full HD, 4K avec mise à l'échelle de Windows).
  Sur un petit écran, elle s'ouvre en plein écran et le panneau Son est masqué au départ (bouton **🎛 Son** ou Ctrl+G).
- Le panneau Son se **redimensionne** en faisant glisser sa séparation. Il **défile** quand la place manque.
  Il peut aussi être détaché dans une fenêtre à part, avec le bouton en haut à droite du panneau.
- La taille et la disposition de la fenêtre sont mémorisées d'une fois sur l'autre.

## Remarques
- Formats lus : MP3, FLAC, M4A/AAC, OGG, Opus, WAV, WMA.
- Le téléchargement YouTube est à réserver aux contenus que vous avez le droit de télécharger.
- Données (bibliothèque, réglages, journaux de rangement) : `%APPDATA%\Musicotheque`.
