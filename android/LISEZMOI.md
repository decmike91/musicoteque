# Musicothèque — Télécommande Android

Application Android qui pilote Musicothèque sur un Raspberry Pi (ou une autre carte) du même réseau Wi-Fi.

- **Recherche du Pi :** elle trouve les Musicothèque du réseau toute seule (service `_musicotheque._tcp`, annoncé par avahi sur le Pi). On peut aussi saisir l'adresse (ex. `192.168.1.20:8080`).
- **Contenu :** elle affiche la télécommande servie par le Pi (`app/remote_web/`).
- **Code d'appairage :** demandé une seule fois par téléphone (Outils ▸ Télécommande sur le Pi).
- **Bouton Retour :** « Changer de Musicothèque » ou « Quitter ».

## Obtenir l'APK
Le fichier APK est compilé automatiquement par GitHub (onglet **Actions**, programme « Application Android ») à chaque modification du dossier `android/`. Il est publié dans l'onglet **Releases** sous le nom `Musicotheque-Telecommande.apk`.

Pour le compiler soi-même : ouvrez le dossier `android/` dans Android Studio, puis **Build ▸ Build APK(s)**. Il faut Java 17 et Android 7 minimum sur le téléphone.
