"""Assistant conversationnel : interroge UNIQUEMENT les donnees autorisees (requetes
parametrees en liste blanche). Aucune requete libre, aucune donnee personnelle
ne quitte le site local.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from ga.core.logging import get_logger
from ga.data import database as db
from ga.data.repositories import AlertRepo, CameraRepo, DossierRepo, EventRepo

log = get_logger("ga.intelligence.assistant")

CAPABILITIES = (
    "Je peux répondre aux questions suivantes sur les données du site :\n"
    "- « Combien d'alertes aujourd'hui ? » / « alertes critiques des 7 derniers jours »\n"
    "- « Combien d'événements de type intrusion cette semaine ? »\n"
    "- « Statut des caméras » / « caméras hors ligne »\n"
    "- « Combien de dossiers à vérifier ? »\n"
    "- « Génère un rapport des 7 derniers jours »\n\n"
    "Conformité : je n'accède qu'aux agrégats opérationnels, jamais aux documents "
    "d'identité ni aux données biométriques."
)


class Assistant:
    """Assistant d'exploitation : intention -> requete en liste blanche -> reponse."""

    def __init__(self, llm=None) -> None:
        self.llm = llm

    def answer(self, question: str) -> dict:
        question_l = question.lower().strip()
        handler = self._route(question_l)
        data_result = handler(question_l)
        if self.llm is not None and data_result.get("formuler_avec_ia"):
            try:
                phrased = self.llm.chat(
                    system="Tu es l'assistant d'exploitation GAtraking. Reformule la reponse "
                           "fournie (donnees reelles) en 2 phrases maximum. N'invente aucun chiffre.",
                    user=f"Question : {question}\nDonnees : {data_result['reponse']}",
                )
                return {"reponse": phrased.strip(), "source": self.llm.name}
            except Exception as exc:
                log.warning("formulation IA en echec", extra={"ctx": {"erreur": str(exc)}})
        return {"reponse": data_result["reponse"], "source": "base_locale"}

    # ---- routage des intentions -------------------------------------------
    def _route(self, q: str):
        if "camera" in q and ("statut" in q or "hors ligne" in q or "état" in q or "etat" in q):
            return self._cameras
        if "dossier" in q:
            return self._dossiers
        if "rapport" in q:
            return self._report
        if "aide" in q or "que peux-tu" in q or "help" in q:
            return self._help
        if "alerte" in q or "alert" in q:
            return self._alerts
        if "evenement" in q or "événement" in q or "evenements" in q or "événements" in q:
            return self._events
        return self._fallback

    # ---- requetes en liste blanche ------------------------------------------
    def _alerts(self, q: str) -> dict:
        days = _extract_days(q)
        severity = "critical" if ("critique" in q or "critical" in q) else None
        with db.session_scope() as session:
            rows = AlertRepo(session).query(severity=severity, days=days, limit=1000)
            open_count = sum(1 for a in rows if a.status == "nouveau")
            by_type: dict[str, int] = {}
            for a in rows:
                by_type[a.type] = by_type.get(a.type, 0) + 1
        detail = ", ".join(f"{t}: {n}" for t, n in sorted(by_type.items(), key=lambda kv: -kv[1])) or "aucune"
        return {"reponse": f"Sur les {days} dernier(s) jour(s) : {len(rows)} alerte(s) "
                           f"({open_count} encore ouverte(s)). Par type — {detail}.",
                "formuler_avec_ia": False}

    def _events(self, q: str) -> dict:
        days = _extract_days(q)
        type_match = re.search(r"(intrusion|incendie|anomalie|exces_vitesse|mauvaise_direction|vehicule_arrete)", q)
        type_ = type_match.group(1) if type_match else None
        with db.session_scope() as session:
            count = EventRepo(session).count(days=days, type_=type_)
        label = f" de type « {type_} »" if type_ else ""
        return {"reponse": f"{count} evenement(s){label} sur les {days} dernier(s) jour(s).",
                "formuler_avec_ia": False}

    def _cameras(self, q: str) -> dict:
        with db.session_scope() as session:
            cams = CameraRepo(session).list()
            total = len(cams)
            offline = [c.id for c in cams if c.last_seen is None or
                       (datetime.now(timezone.utc) - c.last_seen.replace(tzinfo=timezone.utc)).total_seconds() > 120]
        if "hors ligne" in q:
            return {"reponse": f"Cameras sans flux recent ({len(offline)}/{total}) : "
                               f"{', '.join(offline) if offline else 'aucune — toutes les cameras emettent'}.",
                    "formuler_avec_ia": False}
        return {"reponse": f"{total} camera(s) configuree(s). Flux recent : "
                           f"{total - len(offline)}. Sans flux recent : {len(offline)}.",
                "formuler_avec_ia": False}

    def _dossiers(self, q: str) -> dict:
        with db.session_scope() as session:
            rows = DossierRepo(session).query(limit=1000)
        by_status: dict[str, int] = {}
        for d in rows:
            by_status[d.status] = by_status.get(d.status, 0) + 1
        detail = ", ".join(f"{s}: {n}" for s, n in sorted(by_status.items())) or "aucun"
        return {"reponse": f"Dossiers de preuve — {detail}.", "formuler_avec_ia": False}

    def _report(self, q: str) -> dict:
        # report generation delegated to caller via flag (pas de generation dans la reponse)
        return {"reponse": "Pour generer un rapport, utiliser la vue Rapports ou "
                           "POST /api/intelligence/report {\"days\": 7}.",
                "formuler_avec_ia": False}

    def _help(self, q: str) -> dict:
        return {"reponse": CAPABILITIES, "formuler_avec_ia": False}

    def _fallback(self, q: str) -> dict:
        return {"reponse": "Je n'ai pas reconnu cette demande.\n\n" + CAPABILITIES,
                "formuler_avec_ia": False}


def _extract_days(q: str, default: int = 7) -> int:
    if "aujourd" in q or "aujourdhui" in q:
        return 1
    match = re.search(r"(\d+)\s*(jour|day)", q)
    if match:
        return max(1, min(int(match.group(1)), 365))
    if "semaine" in q:
        return 7
    if "mois" in q:
        return 30
    return default
