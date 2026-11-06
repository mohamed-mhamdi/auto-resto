# SallePilot · Guide d’installation

SallePilot suit les tables d’un café ou d’un restaurant. La caméra estime l’occupation et l’équipe confirme la prise en charge, la livraison du premier article et la remise à disposition. Les alertes apparaissent dans le tableau de salle. L’application tourne sur le poste de l’établissement et conserve des événements de table dans SQLite.

[Rapport technique et résultats](RAPPORT-TECHNIQUE.md) · [Proposition commerciale et recette](PILOTE-COMMERCIAL.md)

## Démonstration

Sous Windows, installez Python 3.11 ou une version ultérieure, puis ouvrez `Lancer-demo.cmd`. Laissez la fenêtre ouverte et accédez à [SallePilot](http://127.0.0.1:8765/). Vous pouvez aussi lancer `python server.py --demo` depuis le dossier.

Essayez **Installer**, **Prendre en charge**, **Servi**, **Départ** et **Table prête**. Si un départ a été déclaré trop tôt, **Toujours occupée** restaure la session et ses confirmations. L’onglet **Bilan** présente les sept derniers jours. L’export des visites couvre l’historique et utilise des horodatages Unix. Les changements de la démo restent dans `data/demo.db`.

La [vidéo annotée](evaluation/demo-vision.mp4) montre le détecteur en action sur un extrait du film de Walter R. Booth. Le rectangle indique la zone de la table et les deux états correspondent à la prédiction du moment et à la confirmation dans le temps. [Source et attribution](evaluation/sources.json)

## Installation pilote avec une caméra

Prévoyez un poste Windows sur le site, une caméra fixe et l’accès autorisé à la webcam ou au flux RTSP du NVR. Pour installer les dépendances de vision, ouvrez `Preparer-vision.cmd` depuis le projet. L’archive contient les poids YOLOX-S et Nano. L’installation Python récupère OpenCV, ONNX Runtime et leurs dépendances.

### 1. Démarrer la salle en mode observation

Fermez la démo ou utilisez le port 8766 pour séparer les deux instances. Dans PowerShell, depuis le dossier du projet, choisissez des valeurs longues et aléatoires, distinctes pour l’équipe et la caméra. Le serveur et la vision partagent uniquement la clé caméra.

```powershell
$env:SALLEPILOT_PASSWORD = [Net.NetworkCredential]::new('', (Read-Host 'Mot de passe équipe (16 caractères minimum)' -AsSecureString)).Password
$env:SALLEPILOT_CAMERA_KEY = [Net.NetworkCredential]::new('', (Read-Host 'Clé caméra (24 caractères minimum)' -AsSecureString)).Password
python server.py --port 8766 --name 'Mon café' --tables 3 --wait 300
```

Sur [le tableau pilote](http://127.0.0.1:8766/), identifiez-vous avec **equipe** et le mot de passe choisi. Les données réelles vont dans `data/restaurant.db`. Le nombre de tables ajoute les tables manquantes. Pour un autre établissement ou une recette, spécifiez un autre fichier avec `--db`.

### 2. Calibrer le cadrage et les sièges

Ouvrez un second PowerShell dans le projet. Pour une webcam, utilisez `0`. Pour RTSP, saisissez l’URL avec `Read-Host -AsSecureString` comme pour la clé et utilisez un accès caméra en lecture seule.

```powershell
$env:SALLEPILOT_SOURCE = '0'
$env:SALLEPILOT_CAMERA_KEY = [Net.NetworkCredential]::new('', (Read-Host 'Même clé caméra que le serveur' -AsSecureString)).Password
$vision = '.\.vision-env\Scripts\python.exe'
& $vision vision/calibrate.py --tables 1 2 3 --seats 2 2 4 --reference
```

Pour chaque table, sélectionnez le cadrage général puis les zones où apparaissent la **tête et les épaules des clients assis**. `--seats 2 2 4` correspond à deux zones pour la table 1, deux pour la table 2 et quatre pour la table 3. Demandez à un volontaire de s’asseoir aux places testées pour repérer la bonne hauteur. Limitez les chevauchements entre tables. Pour la référence, sélectionnez un mur fixe avec des contours contrastés, hors passage. L’application conserve les descripteurs de cette zone dans `camera.json`.

```powershell
& $vision vision/worker.py --url http://127.0.0.1:8766
```

Le tableau affiche les observations de la caméra pendant que l’équipe garde la main. Une présence stable doit être confirmée sur plusieurs secondes. La sortie attend 30 secondes d’absence confirmée. Un flux interrompu, figé, trop sombre ou décalé suspend l’envoi. Le tableau indique une caméra indisponible après 15 secondes sans nouvelle observation et conserve les états de service. Vérifiez la référence de cadrage si le soir le signal devient indisponible.

### 3. Valider avant d’activer les transitions

1. Laissez le mode observation actif sur des services complets. Notez les arrivées, départs, masquages et passages du personnel. Comparez vos relevés au CSV des observations dans **Bilan**.
2. Activez les arrivées automatiques avec `--vision-auto` lors du redémarrage du serveur après la recette. L’équipe conserve le bouton **Départ**.
3. Activez `--vision-auto-departure` en plus de `--vision-auto` uniquement après une recette distincte des départs et des faux départs. **Table prête** reste une action d’équipe.
4. Pour revenir au mode observation, redémarrez le serveur sans ces options. Les sessions restent en base.

## Entraîner un modèle local facultatif

Le détecteur préentraîné fonctionne dès que les zones sont calibrées. Un classificateur d’image propre au site peut compléter le détecteur s’il améliore les résultats sur des tournages distincts. Quand les deux signaux se contredisent, la fusion s’abstient.

Filmez des volontaires sous les éclairages habituels. Pour chaque session de tournage, choisissez un seul lot parmi `train`, `val`, `test`. Après extraction, placez les images dans `dataset/<lot>/<empty|occupied>/`, en incluant vaisselle, passages et chaises vides avec des personnes debout. Gardez les clips masqués pour les tests vidéo.

```powershell
& $vision vision/extract.py recordings/session-01.mp4 --out recordings/session-01-crops
& $vision vision/train.py dataset --out occupancy.npz
& $vision vision/worker.py --url http://127.0.0.1:8766 --model occupancy.npz
```

Mesurez les trois modes avec `vision/benchmark.py` : YOLOX seul, classificateur seul avec `--crop-only --model occupancy.npz`, et fusion avec `--model occupancy.npz`. L’archive contient un classificateur expérimental de recherche dont les résultats justifient de le laisser désactivé.

## Exploitation et sauvegardes

- Le serveur écoute sur le poste local. Pour des téléphones ou tablettes, configurez un proxy HTTPS sur le réseau privé, limitez les accès et excluez `/api/vision` du proxy. La version pilote utilise un compte partagé et une clé caméra séparée.
- Placez la base sur un disque local et configurez le démarrage automatique du serveur et du worker sous un compte de service avant une mise en production. Utilisez un gestionnaire de secrets ou un mécanisme de configuration protégé du poste.
- Pour créer une copie SQLite vérifiée pendant le service, exécutez `python ops/backup.py data/restaurant.db sauvegardes/restaurant-2026-11-06.db` vers un volume local qui accepte les liens physiques, par exemple NTFS. Sauvegardez aussi `camera.json` et le modèle local s’il est utilisé. Testez la copie avec `server.py --db <copie>` sur un port différent.
- L’alerte de retard est enregistrée par le serveur même si aucun tableau n’est ouvert. Elle s’affiche au prochain rafraîchissement. La V2 prévoit un écran de service actif et les CSV. Les notifications mobiles et la caisse demandent des intégrations propres au client.
- La vision en direct ne sauvegarde ni vidéo ni audio. Limitez séparément la conservation des extraits de formation et des journaux, avec les conditions définies pour le site. En Tunisie, validez la finalité de l’analyse des images avec l’INPDP et votre conseil avant d’utiliser la caméra avec des clients. [Loi tunisienne, articles 69 à 71](https://www.inpdp.tn/ressources/loi_2004.pdf)

## Vérifications et reproduction

```powershell
python -m unittest discover -s tests -v
node --check web/app.js
& $vision evaluation/fetch_sources.py --ffmpeg 'C:/chemin/ffmpeg.exe'
& $vision vision/prepare_dataset.py evaluation/dataset.json --out dataset/public-v2
& $vision vision/train.py dataset/public-v2 --out occupancy.npz
& $vision vision/benchmark.py evaluation/test.json --out evaluation/mon-test --preview
& $vision evaluation/check_integration.py
```

Le téléchargement des sources est facultatif et requiert FFmpeg pour la normalisation. Les empreintes, auteurs, licences et liens figurent dans [le manifeste des vidéos](evaluation/sources.json).

## Aperçu vidéo local

Ajoutez `--preview` à la commande du worker et ouvrez [Vidéo sur le serveur pilote](http://127.0.0.1:8766/#video). Le panneau rafraîchit environ deux images par seconde. La couleur suit le tableau de salle et le champ « IA » indique la détection caméra pour comparaison. Le rouge apparaît après 15 minutes depuis l’installation sans confirmation **Servi**, même après une prise en charge. Le seuil des alertes de prise en charge reste indépendant. Les images d’aperçu sont gardées en mémoire et nécessitent le même accès que le tableau en mode pilote. Limitez l’accès à cet écran au personnel autorisé.

Pour un essai sans caméra, lancez `Preparer-vision.cmd`, puis `Lancer-video.cmd`. Le replay ouvre [l’onglet Vidéo de démonstration](http://127.0.0.1:8768/#video) et analyse un extrait en boucle. La table 1 est calibrée sur la vidéo. Utilisez l’onglet Salle pour modifier son état et vérifier l’overlay. Les états du service sont simulés et stockés dans une base séparée. [Attribution de l’extrait](evaluation/ATTRIBUTIONS.md)
