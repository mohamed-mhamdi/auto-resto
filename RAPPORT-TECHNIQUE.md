# SallePilot V2 · Rapport de réalisation et de recette

**Date** · 5 novembre 2026, heure de Tunis  
**Périmètre** · Occupation des tables, prise en charge, service, nettoyage et bilan local  
**Statut** · Version installable pour une démonstration et un pilote supervisé

## 1. Ce qui a été livré

- Un moteur de vision CPU avec les poids ONNX officiels de YOLOX-S et Nano. Une détection par image couvre l’ensemble de la salle. Les zones de sièges l’associent à une seule table et écartent les assignations ambiguës.
- Un suivi spatial et temporel de courte durée. Un client brièvement masqué garde une piste, une détection faible peut prolonger une piste existante et une confirmation durable est nécessaire pour modifier une table. Le contrôle optionnel du cadrage compare une zone fixe à la référence. Le worker suspend ses observations si l’image est décalée, figée, trop sombre ou très surexposée.
- Trois niveaux d’exploitation. **Observation** journalise la vision pendant que l’équipe gère les tables. **Arrivées automatiques** ouvre les sessions après confirmation. Les **départs automatiques** s’activent séparément. Une correction manuelle peut rétablir la même session et conserver son état de service.
- Les alertes persistent côté serveur. Le journal caméra et le CSV des visites permettent de comparer la vision au service. L’archive fournit le calibrage, l’outil d’entraînement, le benchmark vidéo, une vidéo annotée, le guide d’installation, la sauvegarde SQLite et une fiche commerciale.
- Les images en direct sont analysées sur le poste. Le worker envoie des états et des identifiants de tables. Aucun suivi nominatif ou par visage n’entre dans le pipeline.

## 2. Recherche et choix techniques

**Détection.** YOLOX fournit un détecteur de personnes adapté au CPU via ONNX. J’ai comparé deux poids officiels en utilisant la même logique de zones. YOLOX-S est le défaut parce qu’il a reconnu plus de places occupées sur les extraits examinés. Nano reste disponible pour les postes où le temps d’inférence est plus contraignant. [Ge et al., YOLOX](https://arxiv.org/abs/2107.08430) · [Exports officiels](https://github.com/Megvii-BaseDetection/YOLOX/tree/main/demo/ONNXRuntime)

**Suivi.** ByteTrack montre l’intérêt de récupérer certaines détections faibles lorsqu’elles s’associent à une piste existante. SallePilot reprend ce principe à petite échelle avec une association spatiale par siège, une durée de stabilité et une mémoire courte. L’implémentation utilise ses propres règles de suivi. [Zhang et al., ByteTrack](https://arxiv.org/abs/2110.06864)

**Posture.** J’ai chargé l’export MediaPipe Pose d’OpenCV Zoo et sondé les angles de hanche sur Caravela. Deux angles étaient exploitables pour 1 détection sur 22 dans le plan des clients et 29 sur 125 dans le plan du personnel. La couverture est trop faible sur ces scènes, où les jambes sont souvent masquées. La V2 utilise le cadrage des sièges et garde cet essai comme piste de recherche. [Bazarevsky et al., BlazePose](https://arxiv.org/abs/2006.10204) · [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/pose_estimation_mediapipe)

## 3. Données et entraînement exécutés

J’ai téléchargé huit fichiers vidéo depuis Wikimedia Commons. Plusieurs proviennent de YouTube et disposent d’une fiche de licence et d’attribution. J’ai normalisé leur cadence, retiré l’audio pour le traitement, annoté des fenêtres de temps et associé chaque zone à un état connu. Les changements de plan ont été exclus des fenêtres d’occupation. Le manifeste contient les liens, licences et empreintes SHA-256. [Sources et annotations](evaluation/sources.json)

| Lot | Sources | Découpes vides | Découpes occupées |
|---|---|---:|---:|
| Entraînement | Spring Court et CDC, exercice assis–debout | 152 | 132 |
| Validation | Caravela, clients, personnel debout et terrasse | 62 | 22 |
| Test | Film de Walter R. Booth, Sing Wong et Kusko | 28 | 69 |

Les 465 découpes proviennent de peu de scènes et plusieurs images d’une même scène sont corrélées. Les vidéos d’un lot ne figurent pas dans les autres lots du classificateur. Le panoramique de Kehlsteinhaus et l’exercice de marche CDC ont servi à des diagnostics séparés. Les vidéos du CDC utilisent le même cadre d’exercice et ne constituent pas une validation indépendante du classificateur.

J’ai entraîné un classificateur de zone basé sur des gradients et une régression logistique équilibrée. Après ajout de la deuxième source d’entraînement, son rappel moyen sur les découpes de test est passé de **58,7 % à 74,6 %**. Il a pourtant manqué les **22 découpes occupées de Caravela** en validation. La fusion a réduit la couverture du détecteur sur les séquences de test. Les poids expérimentaux sont inclus pour reproduction. **Le moteur par défaut reste YOLOX-S avec les zones et les règles temporelles.**

## 4. Mesures sur vidéo

Deux mesures répondent à des questions différentes. La **prédiction par échantillon** décrit ce que voit le moteur à un instant, après le suivi court. L’**état confirmé** demande une durée supplémentaire. Les extraits trop courts peuvent se terminer pendant cette attente. Les échantillons ne sont pas des visites indépendantes.

| Résultat sur le jeu de test vidéo | YOLOX-S | YOLOX-Nano | YOLOX-S + fusion avec le modèle entraîné |
|---|---:|---:|---:|
| Échantillons occupés reconnus | 112 sur 125 | 91 sur 125 | 59 sur 125 |
| Occupés signalés vides avant confirmation | 1 | 2 | 0 |
| Occupés laissés incertains | 12 | 32 | 66 |
| Échantillons vides reconnus | 28 sur 28 | 28 sur 28 | 28 sur 28 |
| Échantillons occupés couverts par l’état confirmé | 97 sur 125 | 82 sur 125 | 65 sur 125 |

- **Durée et contexte.** Le test a 3 extraits et 153 échantillons de table. Le film historique fournit 113 des 125 échantillons occupés. Les 28 échantillons vides proviennent d’une zone de sièges dans un restaurant à emporter. Cette zone reste visible moins de 30 secondes, donc aucun départ n’y est mesurable. Kusko fournit un court plan de clients avec du passage, insuffisant pour confirmer une nouvelle visite avec les seuils de production.
- **Personnel debout.** Sur le clip Caravela, les zones larges ont confirmé une fausse arrivée. Après calibrage de la hauteur des sièges, le moteur n’a confirmé aucune arrivée. Sur les 16 échantillons du plan, 15 ont été laissés incertains parce que le personnel masquait la zone. Cette comparaison utilise le même clip de validation.
- **Cadrage mobile.** Sur le plan panoramique de Kehlsteinhaus, le contrôle de cadrage a refusé 32 échantillons sur 33. Le premier sert de référence. Cela teste un déplacement visible avec une zone statique choisie à la main.
- **Transitions.** Sur l’exercice CDC, les seuils de production n’ont déclenché aucune transition pendant la courte séquence. Lors d’un diagnostic séparé avec des délais volontairement réduits, le siège déjà occupé au début a été confirmé après 1 s, puis le départ 5,25 s après le lever annoté. Le retour a été manqué avant la coupe vidéo. Ce test se déroule hors restaurant.
- **Temps de calcul.** Sur le poste Windows de développement, environ 110 ms par image en médiane pour YOLOX-S et environ 10 ms pour Nano sur ces clips, à deux échantillons par seconde. Ce temps exclut le décodage vidéo et les délais métier. Mesurez à nouveau sur le poste et les flux du restaurant.

Les [données de benchmark](evaluation/results/) contiennent les tableaux par extrait, les prédictions horodatées et les transitions observées. La [vidéo annotée](evaluation/demo-vision.mp4) montre la confirmation sur un extrait réel.

## 5. Recette logicielle

- Les dix tests automatisés couvrent la persistance, la protection de l’API, le mode observation, l’activation séparée des départs, les corrections, la perte caméra, le cadrage, le suivi et l’entraînement.
- La recette navigateur a été exécutée sur une base de test à 390 pixels de large. Le parcours installer, prendre en charge, servir, départ, correction, départ et nettoyage a abouti. Le bilan et les deux exports répondaient et aucun débordement horizontal ni erreur de chargement n’a été relevé.
- Une vidéo a été rejouée dans le moteur ONNX et l’API HTTP réelle, avec écriture dans une base isolée. La sauvegarde a été ouverte et contenait la session et les événements de service attendus.
- Aucun flux CCTV du futur client n’a été raccordé. Le système d’exploitation du poste commercial, son réseau, ses sauvegardes et les alertes en situation réelle restent à réceptionner.

## 6. Passer de la V2 au premier client

| Étape | Travail à réaliser | Critère de passage |
|---|---|---|
| 1. Cadrer le pilote | Choisir un café partenaire, trois tables, une caméra fixe et un référent. Valider la finalité du traitement, l’accès au flux, l’information des personnes et la conservation. | Accord du site et conditions d’usage validées avant l’ouverture du flux. |
| 2. Installer | Tester la connexion RTSP, la visibilité des sièges et la luminosité, puis calibrer. Démarrer le tableau en observation. Fixer les horaires de support et former le responsable. | Trois zones observables, équipe capable de gérer une table manuellement. |
| 3. Mesurer en service | Comparer le journal caméra à une observation horodatée sur plusieurs services, dont un rush et une soirée. Viser au moins 50 visites annotées sur le site. Compter les faux départs, les fausses arrivées et les retards. | Seuils convenus dans le devis et résultats signés avec le gérant. |
| 4. Activer progressivement | Activer d’abord les arrivées automatiques. Garder les départs manuels jusqu’à validation distincte. Exercer la correction, une coupure caméra et le retour en observation. | Équipe autonome et procédures de reprise vérifiées. |
| 5. Exploiter et facturer | Installer le démarrage automatique, configurer le réseau privé et HTTPS si accès sur téléphone, assurer les sauvegardes, les mises à jour et le support. | Restauration réussie, conditions commerciales et responsabilités documentées. |

Une cible de recette à discuter avec le gérant est **au moins 95 % des arrivées détectées en 10 s et zéro départ erroné observé** pendant la période testée. Suivez aussi le nombre de cas incertains et l’utilité des alertes. Ces seuils constituent des objectifs de recette pour un site, avec l’échantillon et les conditions indiqués dans le compte rendu.

La première offre peut être un forfait **installation, calibration et formation**, puis un contrat de support et de recalibrage. Chiffrez le temps réel du premier déploiement avant de fixer un abonnement. Pour équiper plusieurs établissements, ajoutez des comptes nominatifs et rôles, une supervision du poste, une procédure de mises à jour et un canal de support. Une intégration de caisse pourra confirmer la livraison si la caisse expose cet événement.

En Tunisie, les articles 69 à 71 encadrent l’autorisation et les finalités de la vidéosurveillance. La présence d’un système CCTV autorisé pour la sécurité ne valide pas à elle seule une analyse de service. Faites qualifier cet usage et les formalités par l’INPDP ou votre conseil avant un pilote avec de vrais clients. [Loi tunisienne](https://www.inpdp.tn/ressources/loi_2004.pdf) · [Référentiel de l’INPDP](https://www.inpdp.tn/Refrentiel_VS.pdf)

[Procédure d’installation](README.md) · [Devis et fiche de recette modifiables](PILOTE-COMMERCIAL.md)
