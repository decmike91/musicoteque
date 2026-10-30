# Musicothèque — Manuel d'utilisation

Oct 30, 2026 · @mickael

## 1. Présentation

Musicothèque range, identifie, convertit et lit votre musique, sur ordinateur Windows ou sur une petite carte (Raspberry Pi, Banana Pi) avec écran tactile.

| Version | Pour qui | Se lance avec |
| --- | --- | --- |
| Windows (souris et clavier) | PC de bureau ou portable | Raccourci **Musicothèque** du Bureau |
| Tactile (Raspberry Pi, Banana Pi, Linux) | Borne musicale avec écran tactile | Démarre seule au branchement |
| Télécommande Android | Téléphone sur le même Wi-Fi que la borne | Application **Musicothèque** du téléphone |

Ce que fait le logiciel :

- **Ranger** un disque ou une clé USB en `Artiste/Album (Année)/01 - Titre.mp3`, en supprimant les doublons et en transformant les WAV, OGG et WMA en MP3.
- **Identifier** les morceaux sans informations grâce à leur empreinte sonore, « façon Shazam », avec album, année et pochette.
- **Convertir** un CD audio ou un lien YouTube en MP3.
- **Écouter** avec égaliseur, ambiances, effets, correction d'audiogramme et profils audio.
- **Diffuser** sur 6 sorties à la fois (haut-parleurs, casque Bluetooth, HDMI…), avec 3 lecteurs indépendants pour une musique différente par pièce.

Le code source et la dernière version sont sur [github.com/decmike91/musicoteque](https://github.com/decmike91/musicoteque).

## 2. Installation

Une seule installation suffit par appareil. Ensuite, les mises à jour remplacent les fichiers sans toucher à vos réglages ni à votre bibliothèque.

### Windows 10 et 11

1. Décompressez **Musicotheque.zip** dans un dossier, par exemple `Documents\Musicotheque`.
2. Double-cliquez sur **installer.bat**. L'installateur met en place Python, les bibliothèques et trois outils : ffmpeg (lecture et conversion), fpcalc (empreinte sonore) et cyanrip (extraction de CD).
3. Lancez **Musicothèque** depuis le raccourci du Bureau.

ffmpeg pèse environ 100 Mo : une barre de progression s'affiche pendant le téléchargement. S'il échoue, voir la section Dépannage.

### Raspberry Pi, Banana Pi et autres cartes Linux

1. Installez **Raspberry Pi OS 64 bits** (version Lite conseillée pour une borne), ou **Armbian** (Debian 12) pour une Banana Pi M5.
2. Copiez le dossier `musicotheque` sur la carte, puis dans un terminal : `./install_rpi.sh`.
3. Répondez aux questions : Bluetooth (o/N), démarrage (1 = borne plein écran), rotation de l'écran (90 pour le Touch Display 2 à l'horizontale).
4. Redémarrez : Musicothèque s'ouvre en plein écran.

Matériel conseillé : Raspberry Pi 4 ou 5 (ou Banana Pi M5), écran tactile de 7 à 10" (800×480 minimum), carte son DAC ou DAC USB pour un bon son.

### Télécommande Android

1. Sur le téléphone, ouvrez l'onglet **Releases** du dépôt GitHub et téléchargez **Musicotheque-Telecommande.apk**.
2. Ouvrez le fichier et autorisez l'installation depuis cette source.
3. Android 7 ou plus récent est nécessaire.

## 3. Premiers pas

Au premier lancement, la bibliothèque est vide : Musicothèque propose de ranger un emplacement ou d'ajouter un dossier.

- **Ranger et classer** (conseillé) : indiquez un disque, une clé USB ou un dossier. Le logiciel montre d'abord un aperçu, puis copie ou déplace la musique dans votre bibliothèque, classée par artiste et album. Voir la section 5.
- **Ajouter un dossier sans le réorganiser** : *Fichier ▸ Ajouter un dossier* (Ctrl+O). Les morceaux sont référencés là où ils sont.

La bibliothèque se trouve par défaut dans `Musique\Musicothèque` (Windows) ou `~/Music/Musicothèque` (Linux). Le dossier se change dans *Paramètres*.

Pour activer la reconnaissance par empreinte sonore, créez une clé gratuite sur [acoustid.org/new-application](https://acoustid.org/new-application) et collez-la dans *Fichier ▸ Paramètres ▸ Clé AcoustID* (tactile : *Outils ▸ Paramètres*). Sans clé, l'identification se fait seulement à partir du nom des fichiers.

## 4. Bibliothèque et lecteur

La fenêtre Windows a trois zones : le classement à gauche, la liste des titres au centre, la pochette et la file de lecture à droite. La barre du lecteur est en bas.

### Trouver un morceau

- **Classement** (à gauche) : Tous les titres, Artistes ▸ Albums, Albums, Infos incomplètes, Playlists, File de lecture.
- **Recherche** : tapez un titre, un artiste, un album ou un genre dans le champ du haut.
- **Tri** : par artiste, album, titre, année ou les plus écoutés. Un clic sur l'en-tête d'une colonne trie aussi.
- Les cases orange signalent une information manquante.

### Lire

- **Double-clic** sur un titre : la liste affichée devient la file de lecture.
- **Clic droit** : Lire, Lire ensuite, Ajouter à la file, Ajouter à une playlist, Lire sur un autre lecteur, Identifier, Modifier les informations, Afficher dans l'Explorateur.
- **Barre du lecteur** : 🔀 aléatoire, ⏮ précédent, ▶ lecture et pause, ⏭ suivant, ⏹ stop, 🔁 répétition (aucune, toute la file, un titre), barre d'avancement, vumètre, muet, volume.

### Playlists

- *Playlists ▸ Nouvelle playlist* (Ctrl+N), ou clic droit sur des titres ▸ *Ajouter à la playlist ▸ Nouvelle playlist*.
- Clic droit sur une playlist : Lire, Lire en aléatoire, Renommer, Exporter, Supprimer.
- Import et export au format M3U, compatible avec les autres lecteurs.

## 5. Ranger et classer un emplacement

Menu **Ranger ▸ Ranger / classer un emplacement** (Ctrl+R). Le rangement fonctionne sur un disque dur, une clé USB ou un simple dossier.

### Étape par étape

1. **Emplacement à ranger** : par exemple `E:\` pour une clé USB.
2. **Destination** : par défaut `E:\Musique classée`, ou « Ma bibliothèque ».
3. **Mode** : *Déplacer* (les fichiers quittent leur place d'origine) ou *Copier* (l'original reste intact).
4. **Options** :
   - *Identifier en ligne les titres incomplets* : retrouve d'abord les informations manquantes ;
   - *Supprimer automatiquement les doublons* (cochée par défaut) ;
   - *Transformer les WAV, OGG et WMA en MP3* (cochée par défaut).
5. **Analyser** : un aperçu montre chaque fichier, sa future place et une remarque (doublon, conversion, remplacement). **Rien n'est encore modifié.**
6. **Ranger** : les fichiers sont renommés et classés en `Artiste\Album (Année)\01 - Titre.mp3`. Les dossiers vides sont supprimés.

### Doublons

- Sont des doublons : les copies identiques, et le même morceau en plusieurs fichiers (même artiste, même titre, durée proche à 3 secondes près).
- **Le meilleur exemplaire est gardé** : sans perte (WAV, FLAC) d'abord, puis le meilleur débit, puis celui qui a une pochette et des informations complètes.
- Les autres vont à la **Corbeille**. Sur une clé USB, Windows n'a pas de corbeille : ils y sont supprimés définitivement.
- Un morceau déjà présent dans la bibliothèque n'est pas recopié. S'il arrive en meilleure qualité, il remplace l'ancien.
- Ne sont **pas** des doublons : les versions « Live » ou de durée différente, et le même titre sur deux albums différents (album et best-of). Chaque album reste complet.
- En mode *Copier*, rien n'est supprimé sur le support d'origine : les doublons ne sont simplement pas copiés.

### Conversion WAV, OGG et WMA en MP3

- Les informations et la pochette sont conservées.
- Les **WAV** (et AIFF) sont convertis à la qualité choisie dans les Paramètres (320 kbit/s par défaut).
- Les **OGG** et **WMA**, déjà compressés, sont convertis un peu au-dessus de leur qualité d'origine (192 kbit/s au minimum), sans gonfler les fichiers inutilement.
- En mode *Déplacer*, l'original va à la Corbeille une fois la conversion réussie.
- Un WMA protégé contre la copie (DRM) ne peut pas être converti : il est laissé tel quel, avec un message.

Pour nettoyer une bibliothèque déjà rangée : **Ranger ▸ Supprimer les doublons et transformer les WAV / OGG / WMA en MP3**.

### Fichiers protégés (« accès refusé »)

Un fichier impossible à lire, déplacer ou modifier **n'arrête pas le rangement** : il est signalé, laissé à sa place, et le rangement passe au suivant.

- La lecture seule (fréquente sur les fichiers copiés d'un CD) est retirée automatiquement quand c'est possible.
- Un fichier copié mais impossible à retirer de la clé est ajouté à la bibliothèque, et l'original reste sur la clé.
- En fin de rangement, la liste **« Fichiers non traités »** indique chaque fichier ignoré et pourquoi. Fermez le programme qui l'utilise, puis relancez le rangement.

### Annuler

**Ranger ▸ Annuler le dernier rangement** remet en place les fichiers déplacés. Les fichiers supprimés se récupèrent dans la Corbeille.

### Référencer sans ranger

**Fichier ▸ Ajouter un dossier** (Ctrl+O) ajoute un dossier à la bibliothèque sans déplacer ni renommer ses fichiers. **F5** actualise la bibliothèque.

## 6. Identifier, modifier les infos, CD et YouTube

### Identifier un titre « façon Shazam »

Musicothèque écoute le morceau, calcule son empreinte sonore et la compare à la base AcoustID et MusicBrainz (gratuites). Elle retrouve le titre, l'artiste, l'album, l'année, le genre, le numéro de piste et la pochette.

- **Un ou quelques titres** : clic droit ▸ *Identifier* (Ctrl+I). Une liste de propositions s'affiche, avec un score de confiance. Choisissez la bonne, puis *Appliquer*.
- **Toute la bibliothèque** : *Identifier ▸ Compléter automatiquement les infos manquantes*. Seules les propositions sûres sont appliquées ; les autres sont listées pour vérification.
- Aucune proposition ne convient ? Saisissez l'artiste et le titre dans *Recherche manuelle*, puis *Chercher*. *Passer* va au titre suivant.
- Sans clé AcoustID, l'identification se fait d'après le nom du fichier (moins fiable). La clé se saisit dans *Fichier ▸ Paramètres* (voir chapitre 2).

### Fichiers en lecture seule ou protégés

Pour compléter un titre, Musicothèque doit pouvoir modifier le fichier. Avant de l'écouter, elle vérifie qu'il est modifiable :

- **Fichier en lecture seule** (fréquent après une copie depuis un CD) : la lecture seule est **retirée automatiquement**, le journal affiche « 🔓 lecture seule retirée », et le fichier est complété normalement.
- **Lecture seule impossible à retirer** (fichier protégé par Windows, ouvert dans un autre programme, clé USB verrouillée) : le fichier est **mis de côté** (« ⏸ mis de côté »), et le traitement **continue avec les fichiers suivants**.

La liste se retrouve dans **Identifier ▸ Fichiers mis de côté** (sur le Pi : *Outils ▸ Compléter les infos manquantes*). Fermez le programme qui utilise le fichier ou déverrouillez la clé, puis **Réessayer**. Les fichiers réussis quittent la liste.

### Modifier les informations à la main

Clic droit ▸ *Modifier les informations* (Ctrl+E).

- Avec **plusieurs titres sélectionnés**, seuls les champs modifiés sont appliqués à tous (pratique pour corriger un nom d'album).
- **Pochette** : *Changer la pochette…* (image JPG ou PNG), ou *Identifier* pour la récupérer en ligne.
- Les informations sont écrites dans le fichier lui-même (MP3, FLAC, M4A, OGG, WMA) : elles suivent le fichier sur un autre appareil.

### CD audio vers MP3

1. Insérez le CD, puis *Convertir ▸ CD audio → MP3*.
2. Le lecteur et le disque sont détectés, et les titres, l'album et la pochette sont recherchés sur MusicBrainz.
3. Choisissez la qualité (320 kbit/s par défaut), puis *Extraire en MP3*. Le bouton *Lire les infos du disque* affiche d'abord la liste des titres.
4. Les MP3 arrivent directement dans la bibliothèque, classés en `Artiste\Album (Année)`.

L'extraction corrige les erreurs de lecture d'un disque rayé ; elle est donc parfois lente sur un vieux CD.

### Lien YouTube vers MP3

1. *Convertir ▸ Lien YouTube → MP3* (Ctrl+Y).
2. Collez le lien d'une vidéo ou d'une playlist.
3. Musicothèque télécharge le son, le convertit en MP3, reprend le titre et l'artiste de la vidéo et, si l'option est cochée, complète en ligne l'album, l'année et la pochette, puis range le fichier dans la bibliothèque.

> Réservez cette fonction aux contenus que vous avez le droit de télécharger.

## 7. Réglages du son et profils audio

Le panneau **Son** s'affiche sous la liste des titres (bouton 🎛 Son, ou Ctrl+G). Il a un onglet par sortie. En haut de chaque sortie se règlent le périphérique, le lecteur diffusé, les voies, le volume, le retard et le profil ; en dessous, deux onglets : Égaliseur & ambiance, et Audiogramme.

### Égaliseur

- **10 bandes**, de 31 Hz (grave) à 16 kHz (aigu), de −12 à +12 dB.
- **Préréglages** : Plat, Rock, Pop, Jazz, Classique, Électro, Hip-Hop, Voix, Basses +, Aigus +, Loudness, Acoustique.
- *Réinitialiser* : tout à 0 dB. Un limiteur évite la saturation quand on monte beaucoup les curseurs.

### Ambiances et effets

| Réglage | Effet |
| --- | --- |
| **Ambiance** | Préréglages : Aucune, Petite pièce, Salon, Club, Salle de concert, Live / Stade, Cathédrale, Studio. |
| **Renfort de basses** | Ajoute de la rondeur sans toucher à l'égaliseur. |
| **Surround** | Élargit l'image stéréo, surtout au casque. |
| **Réverbération** et **taille de salle** | Simule l'écho d'une pièce. |
| **Balance** | Répartit le son entre gauche et droite. |
| **Volume** | Bouton rotatif : faites-le tourner à la souris ou à la molette. |

Le **vumètre** stéréo affiche le niveau de chaque voie, avec maintien de crête. Tous les réglages sont mémorisés.

### Profils audio

Un profil regroupe l'égaliseur, l'ambiance, les effets, la balance **et l'audiogramme**.

1. En haut de la sortie, choisissez un profil dans la liste.
2. Réglez le son.
3. **Enregistrer** met à jour le profil, **Enregistrer sous…** en crée un nouveau.

Le menu **⋯** permet aussi de renommer, supprimer, importer ou exporter un profil (fichier `.json` à partager ou à copier sur le Raspberry Pi), et de copier les réglages vers une autre sortie.

Profils fournis : *Par défaut*, *Soirée*, *Écoute douce (nuit)*, *Concert*.

## 8. Audiogramme et test auditif

L'onglet **Audiogramme** de chaque sortie adapte le son à votre audition, oreille par oreille.

### Saisir un audiogramme

- Recopiez dans le tableau les valeurs de votre audiogramme (ORL, audioprothésiste), en dB HL, de 125 Hz à 8 kHz.
- Vous pouvez aussi **faire glisser les points** du graphique : oreille droite = **O rouge**, oreille gauche = **X bleue**.
- *Copier une oreille sur l'autre* et *Remettre à zéro* accélèrent la saisie.

### Activer la correction

1. Cochez **Corriger le son d'après cet audiogramme**.
2. Les fréquences moins bien entendues sont renforcées, selon la **règle du demi-gain** : une perte de 40 dB donne +20 dB.
3. Réglez si besoin l'**intensité** (de 0 à 100 %) et la **correction maximale** (en dB), pour garder un son confortable.

La courbe de correction appliquée s'affiche sous le graphique. L'audiogramme est enregistré avec le profil audio : chaque personne de la maison peut avoir le sien.

### Faire un test auditif

1. Branchez le casque que vous utiliserez pour écouter.
2. Réglez le volume de Windows à votre niveau habituel, **et ne le changez plus**.
3. Cliquez sur **Faire un test auditif**.
4. Un bip monte doucement. Appuyez sur **J'entends** (ou la barre Espace) dès que vous le percevez.
5. Chaque fréquence est testée sur chaque oreille. Le test dure 5 à 8 minutes.
6. Le résultat remplit l'audiogramme de la sortie choisie.

> Le test est indicatif : il ne remplace pas un examen par un professionnel de l'audition.

## 9. Plusieurs sorties et plusieurs lecteurs

### Le son sur 2 ou 3 périphériques en même temps

Dans le panneau Son, **＋ Ajouter une sortie** : haut-parleurs, casque, enceinte Bluetooth, écran HDMI, DAC USB… Chaque sortie a son onglet, avec :

- son **périphérique**, et le bouton **🔔** qui joue un bip de test pour le reconnaître ;
- son **volume** et ses **voies** : stéréo, inversée, mono, gauche seule, droite seule ;
- son **égaliseur**, son **ambiance**, ses effets et son **audiogramme**, indépendants des autres sorties ;
- un **retard** (en ms) pour aligner les sorties entre elles.

Les sorties restent synchronisées automatiquement, même si les cartes son n'ont pas exactement la même horloge.

> Une enceinte Bluetooth a souvent 150 à 250 ms de retard. Retardez d'autant les autres sorties pour que tout soit aligné.

### Une autre musique sur une autre sortie

Musicothèque a jusqu'à **3 lecteurs** : le lecteur principal, le Lecteur 2 et le Lecteur 3. Chacun a sa file, ses commandes, son volume, l'aléatoire et la répétition.

1. **＋ Ajouter un lecteur** (panneau Son, ou menu Son) crée le Lecteur 2, puis le Lecteur 3, chacun avec sa sortie.
   - Vous pouvez aussi ajouter une sortie, puis choisir **Lecteur 2** dans sa liste *Lecteur*.
2. Clic droit sur des titres, un album, un artiste ou une playlist ▸ **🎧 Lire sur un autre lecteur** ▸ Lecteur 2 ▸ *Lire maintenant* ou *Ajouter à sa file*.
3. Le panneau **Autres lecteurs**, à droite, pilote les lecteurs 2 et 3 : ⏮ ⏯ ⏭, aléatoire, avancement, volume et file. Il s'affiche aussi par **Son ▸ Afficher les autres lecteurs**.

Plusieurs sorties peuvent écouter le même lecteur : par exemple le salon et la cuisine sur le lecteur principal, et le casque Bluetooth sur le Lecteur 2. Jusqu'à **6 sorties** en tout.

### Enceintes et casques Bluetooth

- **Windows** : appairez d'abord l'appareil dans *Paramètres ▸ Bluetooth et appareils*. Il apparaît ensuite dans la liste des périphériques.
- **Raspberry Pi** : *Outils ▸ 📶 Bluetooth* appaire et connecte l'appareil depuis l'écran tactile (voir chapitre 10).

## 10. Version tactile (Raspberry Pi et autres cartes)

C'est le même logiciel, avec une interface plein écran pensée pour le doigt. L'installation est décrite au chapitre 2.

### Les cinq pages

La barre du bas donne accès à **▶ Lecture · 🎵 Musique · ☰ File · 🎚 Son · 🧰 Outils**.

| Page | Contenu |
| --- | --- |
| **Lecture** | Pochette, titre, avancement, ⏮ ⏯ ⏭, aléatoire 🔀, répétition 🔁, volume, vumètre. En haut, une touche par lecteur pour choisir celui qu'on pilote. |
| **Musique** | Artistes → Albums → Titres, Playlists, et recherche 🔍 avec un clavier AZERTY à l'écran. |
| **File** | La liste de lecture en cours : mélanger, retirer un titre, enregistrer en playlist. |
| **Son** | Une touche par sortie (1, 2, 3, ＋), puis quatre onglets : Égaliseur, Ambiance et effets, Audiogramme, Sortie et volume. Le profil audio se choisit en haut. |
| **Outils** | Les tuiles décrites ci-dessous. |

### Gestes

- **Appui court** sur un titre : le lire.
- **Appui long** : menu (lire ensuite, ajouter à la file ou à une playlist, lire sur un autre lecteur, identifier…).
- **Glisser** : faire défiler les listes, avec inertie.

### Les tuiles de la page Outils

- 🗂 **Ranger une clé USB ou un disque**, avec les interrupteurs *Supprimer les doublons* et *WAV/OGG/WMA → MP3* ;
- 🎵 **Compléter les infos manquantes** ;
- 💿 **CD audio → MP3** et ▶ **YouTube → MP3** ;
- 🔄 **Actualiser la bibliothèque** et ⏏ **Éjecter un support** ;
- 📶 **Bluetooth** : mettez le casque ou l'enceinte en mode appairage, touchez-le dans la liste, Musicothèque l'appaire et le connecte ;
- 📱 **Télécommande** : QR code et code d'appairage du téléphone (chapitre 11) ;
- ⚙ **Paramètres** : clé AcoustID, dossier de la bibliothèque, qualité MP3, luminosité, quitter ;
- ⏻ **Éteindre / redémarrer**.

### Clé USB

Quand vous branchez une clé ou un disque, Musicothèque propose :

- **Écouter** : lire la musique de la clé sans rien modifier ;
- **Ranger dans ma bibliothèque** : copier la musique en la classant.

Avant de retirer la clé, passez par **⏏ Éjecter un support**.

### Une autre musique sur une autre sortie

1. **Son ▸ ＋ ▸ Ajouter un lecteur indépendant** : le Lecteur 2 est créé avec sa sortie.
2. Dans **Musique**, appui long sur un titre, un album ou une playlist ▸ **🎧 Lire sur un autre lecteur**.
3. En haut de la page **Lecture**, touchez « Lecteur 2 · Casque Bluetooth » pour le piloter. Les pages Musique et File suivent le lecteur choisi.

### Taille d'écran

L'interface s'adapte à l'écran, en paysage comme en portrait, de 480×320 à 1920×1080. La page Outils passe de 2 à 4 colonnes selon la largeur.

## 11. Télécommande Android

La version Raspberry Pi se pilote depuis un téléphone ou une tablette **connecté au même Wi-Fi**.

### Ce qu'on peut faire

- lecture, pause, titre précédent et suivant, avancer dans le morceau, volume, aléatoire, répétition ;
- choisir de la musique : artistes, albums, titres, playlists, recherche ;
- gérer la file de lecture ;
- régler chaque sortie : volume, lecteur diffusé, profil audio, activation ;
- tout cela pour chacun des 3 lecteurs.

### Installer l'application

1. Sur le téléphone, ouvrez la page **Releases** du dépôt GitHub `decmike91/musicoteque` et téléchargez **Musicotheque-Telecommande.apk**.
2. Ouvrez le fichier et autorisez l'installation depuis cette source quand Android le demande.
3. Lancez **Musicothèque**. L'application trouve toute seule le Raspberry Pi sur le Wi-Fi : touchez-le.
4. Saisissez le **code à 4 chiffres** affiché sur le Pi dans **Outils ▸ 📱 Télécommande**.

Si le Pi n'est pas trouvé, saisissez l'adresse affichée dans la même fenêtre, par exemple `192.168.1.20:8080`, puis **Se connecter**.

### Sans application

Sur le Pi, ouvrez **Outils ▸ 📱 Télécommande** et scannez le **QR code** avec l'appareil photo du téléphone : la télécommande s'ouvre dans le navigateur, déjà appairée. Cela fonctionne aussi sur iPhone et sur un ordinateur.

### Code d'appairage et sécurité

- Le code est demandé **une seule fois** par téléphone.
- **Nouveau code** déconnecte tous les téléphones déjà appairés.
- Le bouton **Activée** coupe ou réactive la télécommande.
- Dans l'application, la touche Retour propose **Changer de Musicothèque** ou **Quitter**.

## 12. Dépannage, raccourcis et fichiers

### Dépannage

| Problème | Solution |
| --- | --- |
| L'installation reste bloquée sur ffmpeg | Attendez la fin du délai : l'installateur essaie un autre serveur, puis winget. Sinon, téléchargez ffmpeg (version « essentials ») et copiez `ffmpeg.exe` et `ffprobe.exe` dans le dossier `bin` de Musicothèque. |
| Un titre n'est pas reconnu | Vérifiez la clé AcoustID dans les Paramètres. Les enregistrements rares ou très récents peuvent manquer : complétez à la main (Ctrl+E). |
| « Accès refusé » pendant l'identification | La lecture seule est retirée automatiquement. Si c'est impossible, le fichier est mis de côté et les autres sont traités : voir **Identifier ▸ Fichiers mis de côté**, puis *Réessayer* après avoir fermé le programme qui l'utilise. |
| « Accès refusé » pendant le rangement | Fermez le programme qui utilise le fichier, ou déverrouillez la clé USB, puis relancez le rangement. Les autres fichiers ont été traités normalement. |
| Un WMA n'est pas converti | Il est protégé contre la copie (DRM). Il reste à sa place et se lit avec le Lecteur Windows Media. |
| Pas de son sur une sortie | Utilisez le bouton 🔔 pour reconnaître la sortie, vérifiez qu'elle est *Active*, son volume et ses voies. Sur Raspberry Pi ou Banana Pi, ouvrez `alsamixer` et montez les réglages de sortie. |
| Le casque Bluetooth n'apparaît pas | Il doit d'abord être appairé (Windows : Paramètres ▸ Bluetooth ; Pi : Outils ▸ Bluetooth), puis le bouton ⟳ à côté du périphérique. |
| Une nouvelle carte son n'est pas listée (Pi) | Lancez `python3 -m app.setup_audio` dans le dossier de Musicothèque, ou **Son ▸ Sortie et volume ▸ Rechercher les sorties audio**. |
| Le téléphone ne trouve pas le Pi | Le téléphone doit être sur le même Wi-Fi (pas en 4G, pas sur un réseau invité). Saisissez l'adresse affichée dans Outils ▸ Télécommande. |
| Le bas de la fenêtre est coupé | La fenêtre s'adapte à l'écran. Si besoin, double-cliquez sur sa barre de titre pour l'agrandir, ou masquez le panneau Son (Ctrl+G). |

### Raccourcis clavier (Windows)

| Touche | Action |
| --- | --- |
| **Espace** | Lecture / pause |
| **Ctrl+→** / **Ctrl+←** | Titre suivant / précédent |
| **Ctrl+O** | Ajouter un dossier à la bibliothèque |
| **F5** | Actualiser la bibliothèque |
| **Ctrl+R** | Ranger / classer un emplacement |
| **Ctrl+I** | Identifier la sélection |
| **Ctrl+E** | Modifier les informations |
| **Ctrl+Y** | Lien YouTube → MP3 |
| **Ctrl+N** | Nouvelle playlist |
| **Ctrl+G** | Afficher ou masquer le panneau Son |
| **F1** | Ouvrir l'aide |
| **Ctrl+Q** | Quitter |

### Où sont mes fichiers ?

Les réglages se trouvent dans `%APPDATA%\Musicotheque` sous Windows, et dans `~/.config/Musicotheque` sur Raspberry Pi.

| Fichier | Contenu |
| --- | --- |
| `settings.json` | Paramètres, réglages du son, sorties |
| `bibliotheque.db` | Bibliothèque : titres, playlists, statistiques d'écoute |
| `profils\` | Profils audio (`.json`, échangeables entre Windows et le Pi) |
| `rangement_*.json` | Journaux de rangement, utilisés par *Annuler le dernier rangement* |
| `peripheriques.json` | Noms des sorties audio (Pi) |

La musique elle-même reste dans le dossier de la bibliothèque choisi dans les Paramètres. Pour repartir de zéro sans perdre de musique, il suffit de supprimer `bibliotheque.db` : elle sera reconstruite à l'actualisation.
