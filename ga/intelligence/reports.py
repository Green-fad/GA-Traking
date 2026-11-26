"""Generation de rapports : agregats reels de la base + synthese LLM optionnelle.

Rapport entierement construit hors-ligne (chiffres calcules depuis les donnees
reelles) ; le LLM, s'il est configure, ajoute uniquement une synthese narrative.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from ga.core.logging import get_logger
from ga.data import database as db
from ga.data.repositories import AlertRepo, DossierRepo, EventRepo, ReportRepo

log = get_logger("ga.intelligence.reports")


def _collect_stats(days: int, camera_id: str | None) -> dict:
    """Agregats reels : evenements par type, alertes, dossiers, series journalieres."""
    with db.session_scope() as session:
        events = EventRepo(session).query(camera_id=camera_id, days=days, limit=5000)
        events_by_day = EventRepo(session).by_day(days)
        alerts = AlertRepo(session).query(camera_id=camera_id, days=days, limit=5000)
        dossiers = DossierRepo(session).query(limit=5000)
        counts: dict[str, int] = {}
        for ev in events:
            counts[ev.type] = counts.get(ev.type, 0) + 1
        alert_counts: dict[str, int] = {}
        for a in alerts:
            alert_counts[a.type] = alert_counts.get(a.type, 0) + 1
        dossiers_in_period = [d for d in dossiers
                              if d.created_at.replace(tzinfo=timezone.utc)
                              >= datetime.now(timezone.utc) - timedelta(days=days)]
        return {
            "evenements_total": len(events),
            "evenements_par_type": counts,
            "evenements_par_jour": events_by_day,
            "alertes_total": len(alerts),
            "alertes_par_type": alert_counts,
            "alertes_ouvertes": sum(1 for a in alerts if a.status == "nouveau"),
            "dossiers_total": len(dossiers_in_period),
            "dossiers_a_verifier": sum(1 for d in dossiers_in_period if d.status == "a_verifier"),
            "dossiers_valides": sum(1 for d in dossiers_in_period if d.status == "valide"),
        }


def render_report(stats: dict, period_days: int, site_name: str) -> str:
    """Construire le rapport markdown (deterministe, sans invention)."""
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    lines = [
        f"# Rapport operationnel — {site_name}",
        f"**Periode :** {period_days} derniers jour(s) — **Genere le :** {now}",
        "",
        "## 1. Vue d'ensemble",
        f"- Evenements enregistres : **{stats['evenements_total']}**",
        f"- Alertes generees : **{stats['alertes_total']}** "
        f"(dont {stats['alertes_ouvertes']} encore ouvertes)",
        f"- Dossiers de preuve : **{stats['dossiers_total']}** "
        f"({stats['dossiers_a_verifier']} a verifier, {stats['dossiers_valides']} valides)",
        "",
        "## 2. Evenements par type",
    ]
    if stats["evenements_par_type"]:
        for kind, count in sorted(stats["evenements_par_type"].items(), key=lambda kv: -kv[1]):
            lines.append(f"- {kind} : {count}")
    else:
        lines.append("- Aucun evenement sur la periode.")
    lines += ["", "## 3. Alertes par type"]
    if stats["alertes_par_type"]:
        for kind, count in sorted(stats["alertes_par_type"].items(), key=lambda kv: -kv[1]):
            lines.append(f"- {kind} : {count}")
    else:
        lines.append("- Aucune alerte sur la periode.")
    lines += ["", "## 4. Serie journaliere (tous types)"]
    if stats["evenements_par_jour"]:
        per_day: dict[str, int] = {}
        for row in stats["evenements_par_jour"]:
            per_day[row["day"]] = per_day.get(row["day"], 0) + row["count"]
        for day in sorted(per_day):
            lines.append(f"- {day} : {per_day[day]} evenement(s)")
    else:
        lines.append("- Aucune activite enregistree.")
    lines += [
        "",
        "## 5. Limites et recommandations",
        "- Les infractions candidates demeurent des propositions : validation humaine obligatoire avant toute suite.",
        "- Les vitesses ne sont exploitable que sur les cameras calibrees (homographie a 4 points).",
        "- Ce rapport repose exclusivement sur les donnees locales ; les agregats multisites requierent la synchronisation cloud.",
    ]
    return "\n".join(lines)


class ReportGenerator:
    """Genere un rapport (fichier markdown dans data/reports) + enregistrement en base."""

    def __init__(self, llm=None, site_name: str = "Site") -> None:
        self.llm = llm
        self.site_name = site_name

    def generate(self, days: int = 7, camera_id: str | None = None) -> dict:
        stats = _collect_stats(days, camera_id)
        body = render_report(stats, days, self.site_name)
        generated_by = "modele_de_rapport_local"
        if self.llm is not None:
            try:
                summary = self.llm.chat(
                    system="Tu es un analyste d'exploitation. Redige une synthese concise (5 lignes max) "
                           "du rapport d'exploitation fourni. Aucune invention de chiffres.",
                    user=body,
                )
                body = body.replace("## 1. Vue d'ensemble",
                                    f"## 0. Synthese (IA)\n{summary.strip()}\n\n## 1. Vue d'ensemble")
                generated_by = self.llm.name
            except Exception as exc:
                log.warning("synthese LLM en echec, rapport sans IA", extra={"ctx": {"erreur": str(exc)}})
        report_uuid = uuid.uuid4().hex
        path = Path("data/reports") / f"rapport_{report_uuid[:12]}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        with db.session_scope() as session:
            ReportRepo(session).add(
                uuid=report_uuid,
                period_start=datetime.now(timezone.utc) - timedelta(days=days),
                period_end=datetime.now(timezone.utc),
                path=str(path), kind="operationnel", generated_by=generated_by,
            )
        log.info("rapport genere", extra={"ctx": {"uuid": report_uuid, "chemin": str(path)}})
        return {"uuid": report_uuid, "chemin": str(path), "genere_par": generated_by,
                "resume": body[:800]}
