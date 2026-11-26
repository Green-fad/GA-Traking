# Rapport final — Reconstruction de la plateforme GAtraking

**Date :** 26/11/2026 — **Dépôt :** https://github.com/Green-fad/Mssa (branche `main`)

## 1. Audit du dépôt existant

Le dépôt cible était **vide** (aucune branche, aucun commit) : la reconstruction a été faite de zéro, sans écrasement de code existant.

## 2. Fonctionnalités réellement implémentées et testées

Chaque module ci-dessous contient du code fonctionnel (aucune interface fictive), sa configuration, ses tests et une démonstration :

| Module | Contenu livré | Preuve |
|---|---|---|
| **GA-CORE** | Bus d'événements typé (33 types, isolation des erreurs, handlers sync/async), registre de services avec santé, routage local/cloud (charges essentielles toujours locales), pipeline analytique orchestrateur | tests `test_resilience.py`, intégration |
| **GA-VISION** | Capture RTSP/fichier/webcam avec reconnexion réseau, détecteur YOLO ONNX (GPU auto-détecté) **+ repli MOG2 hors-ligne**, gestion multi-caméras threadée, registre de modèles versionné (SHA-256) | `test_vision.py` (détection réelle sur scène synthétique) |
| **GA-TRACK** | Kalman à vitesse constante (bruit normalisé par taille d'objet), **ByteTrack complet** (association en 2 étapes, récupération d'occlusions à faible confiance), trajectoires, comptage bidirectionnel | `test_track.py` : identité stable, 2 objets séparés, occlusion, anti-double comptage |
| **GA-ROAD** | Calibration homographie 4 points, vitesse filtrée (anti-tremblement < 5 cm, anti-accélération irréaliste, détection d'arrêt par absorption du fond), événements (excès candidat, arrêt, mauvaise direction, franchissement), **dossiers de preuves avec images horodatées** | `test_road.py` + intégration : vitesse mesurée à ±1,5 % de la vérité terrain |
| **GA-SECURITY** | Zones polygonales (ray casting, N images consécutives), incendie (HSV + scintillement temporel), anomalies (z-score), alertes dédoublonnées par (type, caméra) | `test_security.py` : flamme confirmée, aucune fausse alerte sur scène calme |
| **GA-INTELLIGENCE** | Clients LLM cloud (OpenAI-compatible) et local (Ollama), **rapports calculés depuis les données réelles** (LLM optionnel en synthèse), assistant en liste blanche (aucune donnée personnelle) | `test_api.py` : rapport généré, assistant répond |
| **GA-OPERATIONS** | API REST complète (caméras, alertes, événements, dossiers, utilisateurs, paramètres IA, système, journaux, médias), WebSocket d'alertes, JWT/PBKDF2 200k itérations, RBAC 3 rôles, anti force brute, **audit immuable**, console web opérationnelle | `test_api.py` : 18 tests (login, 401/403, verrouillage, injection SQL, traversée de chemin) |
| **GA-DATA** | SQLAlchemy 2.0 (SQLite hors-ligne / PostgreSQL), cache Redis + repli mémoire TTL, médias avec rétention, **file de synchronisation persistante idempotente** (reprise, backoff, 409 déjà-connu) | `test_data.py` : idempotence, coupure réseau sans perte, purge rétention |

## 3. Tests exécutés (résultat réel)

- **79 tests pytest — tous verts** (`python -m pytest tests/ -q` → `79 passed`) :
  - unitaires : Kalman, ByteTrack, comptage, calibration, vitesse, zones, incendie, anomalies, alertes, sync, médias, registre de modèles ;
  - **intégration bout-en-bout** (420 images réelles) : détection MOG2 → tracking → vitesse calibrée (mesure à ±1,5 % de la vérité terrain) → franchissement, arrêt, intrusion → alertes critiques → dossiers avec images → file de sync ;
  - sécurité applicative : authentification, RBAC, verrouillage après 5 échecs, injection SQL, traversée de répertoire ;
  - résilience : fin de flux, fichier absent, piste perdue puis retrouvée avec le même ID, handlers en échec isolés, payloads corrompus sans crash.
- **Démonstration fonctionnelle** (`python -m ga.cli demo`, 900 images, 34,7 s de traitement) :
  événements incendie + arrêt + franchissement×2 + intrusion + excès de vitesse, 3 alertes,
  3 dossiers de preuve, rapport opérationnel généré, **vidéo annotée** (`demo_output/demo_annote.mp4`).

## 4. Limitations honnêtes

1. **Poids YOLO non fournis** : le détecteur YOLO ONNX est implémenté et testé à l'import, mais aucun fichier `.onnx` n'est livré (poids non versionnables) ; sans modèle, le repli MOG2 prend le relais. Mesure de vitesse validée sur scène synthétique — **à revalider sur caméras réelles avec calibration terrain**.
2. **MOG2** absorbe les objets immobiles après ~1-2 s (limite connue de la soustraction de fond) ; la détection d'arrêt par disparition compense ce cas, documentée dans le code.
3. **RTSP** : implémenté (reconnexion, transport auto) mais non testable sans caméra physique dans cet environnement — testé par simulation de coupures sur fichiers.
4. **Cloud/LLM** : clients implémentés et testés avec serveurs simulés ; aucun cloud réel n'était disponible.
5. **Console web** : une console d'exploitation opérationnelle est livrée (dashboard, alertes avec actions, événements, dossiers avec validation, caméras, cartographie, assistant, système/journaux, temps réel WebSocket). Le **frontend React/TypeScript complet (build Vite, 12 vues enrichies)** reste à développer — la console actuelle est une SPA autonome servie par l'API, fonctionnelle dès `python -m ga.cli serve`.
6. PostgreSQL testé via la couche SQLAlchemy (SQLite en tests) ; déploiement `docker-compose` fourni mais non exécuté dans cet environnement.

## 5. Travaux restants (priorisés)

1. Frontend React/TypeScript complet (12 vues du cahier des charges, build Vite, murs vidéo MJPEG).
2. Acquisition de poids YOLO + calibration terrain des caméras réelles + validation vitesse/infractions sur site.
3. Serveur cloud (réception `/sync/batch` avec déduplication par clé d'idempotence) et statistiques multisites.
4. CI (GitHub Actions : pytest + lint), packaging PyInstaller pour Windows.
5. Durcissement production : rotation des journaux, HTTPS/TLS, sauvegardes chiffrées, alertes email/SMS.
