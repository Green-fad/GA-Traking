# Rapport final — Reconstruction de la plateforme GAtraking

**Date :** 26/11/2026 — **Dépôt :** https://github.com/Green-fad/Mssa (branche `main`)

## 1. Audit du dépôt existant

Le dépôt cible était **vide** (aucune branche, aucun commit) : la reconstruction a été faite de zéro, sans écrasement de code existant.

## 2. Fonctionnalités réellement implémentées et testées

Chaque module ci-dessous contient du code fonctionnel (aucune interface fictive), sa configuration, ses tests et une démonstration :

| Module | Contenu livré | Preuve |
|---|---|---|
| **GA-CORE** | Bus d'événements typé (33 types, isolation des erreurs, handlers sync/async), registre de services avec santé, routage local/cloud (charges essentielles toujours locales), pipeline analytique orchestrateur | tests `test_resilience.py`, intégration |
| **GA-VISION** | Capture RTSP/fichier/webcam (reconnexion réseau), détecteur **YOLO réel ONNX** (poids officiels ultralytics, GPU auto-détecté) **+ repli MOG2 hors-ligne**, **ANPR : lecture réelle des plaques** (OpenCV 5 contours + OCR tesseract, 100 % offline), gestion multi-caméras threadée, registre de modèles versionné (SHA-256) | `test_yolo.py` (inférence réelle : bus + personnes détectés), `test_anpr.py` : 7 plaques lues exactement + scène négative sans fausse lecture |
| **GA-TRACK** | Filtre de Kalman à vitesse constante (bruit normalisé par taille d'objet), **ByteTrack complet** (association 2 étapes, récupération d'occlusions à faible confiance), trajectoires, comptage bidirectionnel | `test_track.py` : identité stable, 2 objets séparés, occlusion, anti-double comptage |
| **GA-ROAD** | Calibration homographie 4 points, vitesse filtrée (anti-tremblement < 5 cm, anti-accélération irréaliste, détection d'arrêt par absorption du fond), événements (excès candidat, arrêt, mauvaise direction, franchissement), **dossiers de preuves : images horodatées + plaque ANPR capturée à l'instant de l'infraction** | `test_road.py` + intégration : vitesse mesurée à ±1,5 % de la vérité terrain |
| **GA-SECURITY** | Zones polygonales (ray casting, N images consécutives), incendie (HSV + scintillement temporel), anomalies (z-score), alertes dédoublonnées par (type, caméra) | `test_security.py` : flamme confirmée, aucune fausse alerte sur scène calme |
| **GA-INTELLIGENCE** | Clients LLM cloud (OpenAI-compatible) et local (Ollama), **rapports calculés depuis les données réelles**, assistant en liste blanche, **connecteurs registres officiels** (plaque → titulaire, CIN → identité) avec habilitation légale, audit sans plaque en clair, limitation de débit (anti-requetes massives) et masquage par rôle | `test_api.py`, `test_registries.py` (12 tests : garde-fous, RBAC, extract CSV offline, E2E identification) |
| **GA-OPERATIONS** | API REST complète (caméras, alertes, événements, dossiers, **identification registre**, utilisateurs, paramètres IA, système, journaux, médias), **WebSocket d'alertes temps réel**, **flux MJPEG par caméra**, JWT/PBKDF2 200k itérations, RBAC 3 rôles, anti force brute, **audit immuable**, **frontend React/TypeScript complet (12 vues, build Vite strict)** avec panneau d'identification et badges plaque | `test_api.py` + vérification serveur réel (SPA 200, bundle 662 ko, MJPEG 200 multipart/x-mixed-replace) |
| **GA-DATA** | SQLAlchemy 2.0 (SQLite hors-ligne / PostgreSQL), cache Redis + repli mémoire TTL, médias avec rétention, **file de synchronisation persistante idempotente** (reprise, backoff, 409 déjà-connu) | `test_data.py` : idempotence, coupure réseau sans perte, purge rétention |
| **Serveur cloud** | `cloud_server/` : réception `/api/v1/sync/batch` **idempotente** (clés d'idempotence, doublons comptés), authentification Bearer, **statistiques multisites**, liste des sites, base dédiée | `test_cloud.py` : E2E avec la **vraie** SyncEngine (ASGI) — réception, déduplication, agrégats |
| **CI** | GitHub Actions : installation pip cachée, vérification imports, suite pytest complète, démonstration bout-en-bout | `.github/workflows/ci.yml` |

**Frontend (12 vues du cahier des charges)** : connexion, tableau de bord (KPI + graphes recharts), mur vidéo (snapshots rafraîchis + flux MJPEG), gestion des caméras (CRUD), cartographie des installations, centre d'alertes (actions + WebSocket temps réel), historique des événements, dossiers avec visionneuse de preuves, validation humaine et **identification du titulaire via les registres**, gestion des utilisateurs, paramètres IA, état système, assistant conversationnel. Build `tsc` strict sans erreur ; bundle **versionné dans le dépôt** (`frontend/dist/`) pour déploiement Windows sans Node ; repli console legacy autonome.

**Chaîne infraction routière complète (cœur métier)** : détection véhicule → tracking → infraction (vitesse/franchissement/arrêt/intrusion) → **lecture de la plaque à l'instant de l'infraction (ANPR offline)** → dossier de preuve (images + métriques + plaque) → **interrogation du registre habilité (titulaire / identité)** → validation humaine → décision + contestation + audit. Le raccordement aux registres réels se fait **par configuration sans modifier le code** : fournisseur `http` (endpoint REST habilité + jeton) ou `offline` (extract CSV autorisé livré par l'autorité).

## 3. Tests exécutés (résultat réel)

- **113 tests pytest — tous verts** (`python -m pytest tests/ -q` → `113 passed`) :
  - unitaires : Kalman, ByteTrack, comptage, calibration, vitesse, zones, incendie, anomalies, alertes, sync, médias, registre de modèles ;
  - **YOLO réel** : inférence ONNX Runtime avec les poids officiels (image réelle : bus + personnes détectés) ;
  - **ANPR réel** : 7 plaques synthétiques lues exactement (formats variés, petite plaque vue de loin), bbox dans le cadre de la plaque, aucune fausse lecture sur bruit ;
  - **registres officiels** : garde-fous (inactif sans habilitation, fondement légal obligatoire, limite de débit par utilisateur), connecteurs mock/offline CSV, masquage CIN par rôle, audit sans plaque en clair, E2E API (identification, RBAC, finalité dossier obligatoire) ;
  - **intégration bout-en-bout** (420 images réelles) : détection → tracking → vitesse calibrée (±1,5 %) → infractions → ANPR → alertes critiques → dossiers avec images → file de sync ;
  - **cloud E2E** : SyncEngine réelle → serveur cloud réel (réception, déduplication, stats multisites, refus de jetons invalides) ;
  - sécurité applicative : authentification, RBAC, verrouillage après 5 échecs, injection SQL, traversée de répertoire ;
  - résilience : fin de flux, fichier absent, piste perdue puis retrouvée avec le même ID, handlers en échec isolés, payloads corrompus sans crash.
- **Démonstration fonctionnelle** (`python -m ga.cli demo`, 900 images, ~35 s) : événements incendie + arrêt + franchissements + intrusion + excès de vitesse, 3 alertes, 3 dossiers de preuve, rapport opérationnel, **vidéo annotée** (`demo_output/demo_annote.mp4`).
- **Serveur réel vérifié** : SPA React servie, bundle JS chargé, login API, flux MJPEG authentifié, routes SPA 200.

## 4. Limitations honnêtes

1. **Poids hors dépôt git** : `models/yolov8n.onnx` (12 Mo) n'est pas versionné dans git (politique binaire) ; il est **reproductible en une commande** (`python tools/fetch_model.py` : téléchargement officiel, conversion ONNX, enregistrement SHA-256, test d'inférence). L'inférence réelle est validée sur image réelle — **la mesure de vitesse reste à revalider sur caméras réelles avec calibration terrain**.
2. **MOG2** (repli hors-ligne) absorbe les objets immobiles après ~1-2 s (limite connue de la soustraction de fond) ; la détection d'arrêt par disparition compense ce cas, documentée dans le code.
3. **RTSP** : implémenté (reconnexion, transport auto) mais non testable sans caméra physique dans cet environnement — testé par simulation de coupures sur fichiers.
4. **PostgreSQL** : support complet via SQLAlchemy et `docker-compose` fourni ; l'exécution d'un PostgreSQL réel n'a pas été possible dans cet environnement (tests sur SQLite, API identique via ORM).
5. **Durcissement résiduel production** : rotation des journaux (5 Mo × 5) livrée ; restent à brancher : alertes email/SMS, sauvegardes chiffrées, TLS côté déploiement Windows.
6. **ANPR** : validée sur plaques synthétiques (7/7 formats variés + négatif) ; sur caméras réelles, la précision OCR dépend de l'angle, de l'éclairage et de la résolution — à revalider sur site, et si besoin brancher une caméra ANPR dédiée ou un détecteur de plaques entraîné (le connecteur et le format de dossier n'ont pas à changer).
7. **Registres officiels** : connecteurs livrés et testés avec fournisseur mock/offline ; aucun registre national réel n'était joignable sans habilitation — le raccordement au fournisseur habilité se fait par configuration (`registries.fournisseur: http` + `GA_REGISTRES_TOKEN`).

## 5. Travaux restants (priorisés)

1. **Validation terrain** : poids YOLO + ANPR sur les caméras réelles du site, calibration homographie réelle, revue des seuils (vitesse, arrêt, zones), précision OCR sur plaques du parc local.
2. **Raccordement aux registres réels** : habilitation légale de l'exploitant, choix du fournisseur (`http` endpoint de l'autorité ou `offline` extract CSV), consignation du fondement légal dans `registries.base_legale`, mise en service du jeton (`GA_REGISTRES_TOKEN`).
3. **Exécution PostgreSQL en production** (docker-compose fourni) + bascule `GA__DATA__DATABASE_URL`.
4. **Durcissement final** : alertes email/SMS, sauvegardes chiffrées, TLS côté déploiement Windows, tests de charge réguliers (`tools/load_test.py`).
5. **Packaging** : PyInstaller (exécutable Windows), signature du bundle, distribution des mises à jour via le serveur cloud.
6. **Multisite avancé** : consolidation des rapports inter-sites sur le cloud + redistribution des modèles versionnés.
