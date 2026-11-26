"""Serveur cloud GAtraking : reception des synchronisations, deduplication, statistiques multisites.

Deploiement (docker compose deploy/cloud-compose.yml ou uvicorn) :
    uvicorn cloud_server.app:create_app --factory --host 0.0.0.0 --port 8100
Variables : GA_CLOUD_TOKEN (jeton attendu des sites), GA_CLOUD_DB (chemin SQLite).
"""
