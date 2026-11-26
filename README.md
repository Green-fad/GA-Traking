# GAtraking
 
Plateforme professionnelle de **vision artificielle, surveillance d'infrastructures, analyse des événements et gestion opérationnelle**, à architecture hybride (exécution locale Windows + calcul cloud complémentaire, continuité sans Internet).

## Modules

| Module | Rôle | Code |
|---|---|---|
| **GA-CORE** | Orchestration, bus d'événements typé, registre de services, routage local/cloud, pipeline analytique | `ga/core/` |
| **GA-VISION** | Capture RTSP/fichier/webcam (reconnexion auto), détection YOLO ONNX + repli MOG2 hors-ligne, multi-caméras threadées, registre de modèles versionné | `ga/vision/` |
| **GA-TRACK** | Filtre de Kalman, ByteTrack (association 2 étapes), trajectoires, comptage bidirectionnel | `ga/track/` |
| **GA-ROAD** | Calibration homographie (4 points), mesure de vitesse filtrée, événements routiers, **dossiers de preuves à validation humaine** | `ga/road/` |
| **GA-SECURITY** | Zones d'intrusion polygonales, détection incendie (couleur + scintillement), anomalies statistiques (z-score), alertes dédoublonnées | `ga/security/` |
| **GA-INTELLIGENCE** | LLM local (Ollama) / cloud (OpenAI-compatible), rapports depuis données réelles, assistant en liste blanche | `ga/intelligence/` |
| **GA-OPERATIONS** | API REST + WebSocket, JWT/PBKDF2, RBAC (admin/opérateur/observateur), audit immuable, console web | `ga/operations/` + `frontend/dist/` |
| **GA-DATA** | SQLAlchemy SQLite/PostgreSQL, cache Redis + repli mémoire, médias avec rétention, file de synchronisation idempotente | `ga/data/` |

## Démarrage rapide (Linux/macOS)

```bash
pip install -r requirements.txt
python -m ga.cli migrate          # schema de base
python -m ga.cli demo             # demonstration bout-en-bout (video synthetique)
python -m ga.cli serve            # console : http://localhost:8000
```

Première connexion : **admin / GAt Admin#2026** (à changer immédiatement).

## Démarrage Windows

```powershell
powershell -ExecutionPolicy Bypass -File deploy/windows/install.ps1   # venv + config guidée + migrate
.\run.ps1                                                             # service + console
powershell -File deploy/windows/backup.ps1                            # sauvegarde
powershell -File deploy/windows/restore.ps1 -Archive backups\xxx.zip  # restauration
powershell -File deploy/windows/uninstall.ps1                         # desinstallation propre
```

## Configuration

Copier `config/gatraking.example.yaml` vers `config/gatraking.yaml`. Toute valeur est
surchargable par variable d'environnement `GA__SECTION__CLE` (ex. `GA__SERVER__PORT=8100`).
Caméras : `analysis.counting_lines`, `analysis.zones`, `analysis.calibration`
(4 points image ↔ 4 points mètres — **la mesure de vitesse exige cette calibration**).

## Modèle IA (YOLO)

```bash
python tools/fetch_model.py   # télécharge yolov8n.pt officiel, convertit ONNX,
                              # enregistre la version (SHA-256) et teste l'inférence réelle
```

Sans modèle, le détecteur de secours MOG2 prend automatiquement le relais (100 % hors-ligne).

## ANPR : lecture des plaques (immatriculation)

```python
from ga.vision.anpr import PlateReader
lecteur = PlateReader()          # OpenCV 5 (candidats contours) + tesseract (OCR offline)
lecture = lecteur.read(image)    # -> PlateReading(plaque="AB123CD", score, bbox)
```

- 100 % hors-ligne : aucune image n'est envoyée à un service externe, seule la chaîne
  de caractères lue peut quitter la machine (vers les registres habilités).
- La plaque est capturée **au moment de l'infraction** et stockée dans le dossier de
  preuve (`evidence.plaque`) — visible dans la console, synchronisée au cloud.
- Requis : paquet `tesseract-ocr` (inclus dans la CI). Sans tesseract, l'ANPR se
  désactive proprement et les dossiers restent valides sans plaque.

## Registres officiels (plaque → titulaire, identité)

> **Cadre légal** : l'accès aux registres nationaux (propriétaires de véhicules,
> carte d'identité) est réservé aux exploitants **habilités** par l'autorité
> compétente. La couche est **inactive par défaut** (`registries.active: false`) et
> exige un fondement légal consigné. Chaque interrogation est **audité**, **limitée
> en débit** (anti-requetes massives), attachée à un **dossier d'instruction** et le
> n° CIN est **masqué** hors rôle administrateur.

```bash
GA_REGISTRES_TOKEN=jeton-fourni-par-l-autorite python -m ga.cli serve
# 3 fournisseurs configurables : "mock" (fictif, tests), "offline" (extract CSV
# autorisé : vehicules.csv + identites.csv), "http" (endpoint REST habilité)
# POST /api/dossiers/{uuid}/identifier      GET /api/registres/vehicule/{plaque}?dossier=UUID
# GET  /api/registres/etat                  (admin)
```

## Frontend

Console React/TypeScript (12 vues, français, thème security-ops) : le **build est
versionné** dans `frontend/dist/` et servi par l'API — aucun Node requis pour l'exploitation.

```bash
cd frontend && npm install && npm run dev    # développement (proxy /api → :8000)
npm run build                                # régénérer dist/ (tsc strict)
```

## Serveur cloud (réception multisites)

```bash
GA_CLOUD_TOKEN=jeton uvicorn cloud_server.app:create_app --factory --port 8100
# GET  /api/v1/health           POST /api/v1/sync/batch (idempotent)
# GET  /api/v1/stats/multisite  GET /api/v1/sites
```

## Tests

```bash
python -m pytest tests/ -q        # 113 tests : unitaires, YOLO réel, ANPR, registres, intégration, cloud E2E, sécurité, résilience
python tools/load_test.py         # test de charge API (usage : python tools/load_test.py --users 30 --seconds 15)
python tools/demo_pipeline.py     # démonstration complète avec vérité terrain
```

## Sécurité et conformité

- Authentification PBKDF2 (200 000 itérations) + JWT HS256, limiteur anti force brute.
- RBAC : observateur < opérateur < admin ; chaque action sensible est journalisée (audit immuable).
- **Aucune sanction automatique** : les infractions candidates sont des dossiers `à vérifier`, décision humaine obligatoire, contestation et audit possibles.
- Aucune reconnaissance faciale ni biométrie ; aucun transfert automatique de données personnelles vers le cloud.
- Journalisation JSON structurée ; politiques de rétention des médias configurables.

Voir `docs/rapport_final.md` pour l'état détaillé (fonctionnalités terminées, tests exécutés, limitations, travaux restants).
