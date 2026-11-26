"""Connecteurs aux registres officiels (immatriculation, identite) avec garde-fous legaux.

CADRE D'USAGE — a lire avant d'activer :
- l'acces aux registres nationaux (proprietaires de vehicules, carte nationale
  d'identite) est reserve aux exploitants HABILITES par l'autorite competente ;
- le service est desactive par defaut (`registries.active: false`) et l'activation
  exige un fondement legal consigne (`base_legale`) ;
- chaque interrogation est auditee (qui, quand, pour quel dossier) et le debit est
  limite par utilisateur (anti-requetes massives) ;
- minimisation : seuls les champs necessaires a l'instruction de l'infraction sont
  exploites ; l'adresse est masquee par defaut ; les CIN sont masques pour les roles
  non admin ;
- la plaque est normalisee localement (ANPR offline) : aucune image ni aucun flux
  video n'est envoye au registre, uniquement la chaine de caracteres lue.

Fournisseurs supportes :
- "http"    : endpoint REST du registre habite (Bearer, champs canoniques);
- "offline" : extract autorise fourni par l'exploitant (CSV locaux, maj periodique);
- "mock"    : jeu d'essai determinant (demonstration/tests) — NE JAMAIS utiliser
  en production ; les donnees sont fictives.
"""
from __future__ import annotations

import csv
import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from ga.core.config import RegistriesConfig
from ga.core.logging import get_logger
from ga.vision.anpr import normaliser_plaque

log = get_logger("ga.intelligence.registries")


class RegistryInactive(Exception):
    """Le service registres n'est pas active (aucune habilitation configuree)."""


class RegistryRateLimited(Exception):
    """Limite d'interrogations atteinte pour cet utilisateur (anti-masse)."""


class RegistryUnavailable(Exception):
    """Le fournisseur est joignable mais en echec, ou l'extract est absent."""


@dataclass
class TitulaireVehicule:
    plaque: str
    nom: str = ""
    prenom: str = ""
    cin: str = ""
    vehicule: str = ""
    couleur: str = ""


@dataclass
class IdentitePersonne:
    cin: str
    nom: str = ""
    prenom: str = ""
    date_naissance: str = ""
    adresse: str = ""


class RegistryConnector(Protocol):
    """Contrat d'un fournisseur de registre (brut, sans garde-fous)."""

    def cherche_titulaire(self, plaque: str) -> dict[str, Any] | None: ...
    def cherche_identite(self, cin: str) -> dict[str, Any] | None: ...


def _normaliser_champs(brut: dict[str, Any]) -> dict[str, Any]:
    """Accepter les noms canoniques francais ou anglais courants des registres."""
    alias = {"plate": "plaque", "name": "nom", "firstname": "prenom", "last_name": "nom",
             "first_name": "prenom", "national_id": "cin", "brand": "marque",
             "model": "modele", "color": "couleur", "birthdate": "date_naissance",
             "birth_date": "date_naissance", "address": "adresse"}
    out = {}
    for cle, valeur in brut.items():
        out[alias.get(str(cle).lower(), str(cle).lower())] = valeur
    return out


class MockRegistryConnector:
    """Jeu d'essai determinant — demontration et tests uniquement."""

    _VEHICULES = {
        "AB123CD": {"plaque": "AB123CD", "cin": "C198745", "nom": "Benali", "prenom": "Karim",
                    "marque": "Renault", "modele": "Clio", "couleur": "blanc"},
        "1234AB56": {"plaque": "1234AB56", "cin": "C203314", "nom": "Haddad", "prenom": "Sonia",
                     "marque": "Peugeot", "modele": "308", "couleur": "gris"},
        "12D4567": {"plaque": "12D4567", "cin": "C178902", "nom": "Traore", "prenom": "Moussa",
                    "marque": "Dacia", "modele": "Logan", "couleur": "bleu"},
    }
    _IDENTITES = {
        "C198745": {"cin": "C198745", "nom": "Benali", "prenom": "Karim",
                    "date_naissance": "1987-04-12", "adresse": "12 rue des Palmiers"},
        "C203314": {"cin": "C203314", "nom": "Haddad", "prenom": "Sonia",
                    "date_naissance": "1992-11-03", "adresse": "5 avenue Hassan II"},
        "C178902": {"cin": "C178902", "nom": "Traore", "prenom": "Moussa",
                    "date_naissance": "1980-06-25", "adresse": "78 boulevard de la Republique"},
    }

    def cherche_titulaire(self, plaque: str) -> dict[str, Any] | None:
        return self._VEHICULES.get(normaliser_plaque(plaque))

    def cherche_identite(self, cin: str) -> dict[str, Any] | None:
        return self._IDENTITES.get(cin)


class OfflineRegistryConnector:
    """Extract autorise fourni par l'exploitant (CSV locaux, maj periodique).

    Format attendu (separateur ';', encodage UTF-8) :
      vehicules : plaque;cin;nom;prenom;marque;modele;couleur
      identites : cin;nom;prenom;date_naissance;adresse
    """

    def __init__(self, chemin_extract: str) -> None:
        from pathlib import Path

        base = Path(chemin_extract)
        self._vehicules: dict[str, dict[str, Any]] = {}
        self._identites: dict[str, dict[str, Any]] = {}
        if not base.exists():
            raise RegistryUnavailable(f"extract absent : {chemin_extract}")
        fichier_veh = base if base.suffix == ".csv" and "ident" not in base.stem else base / "vehicules.csv"
        fichier_id = base if base.suffix == ".csv" else base / "identites.csv"
        if fichier_veh.suffix == ".csv" and fichier_veh.exists():
            self._lire(fichier_veh, self._vehicules, cle="plaque")
        if fichier_id.exists():
            self._lire(fichier_id, self._identites, cle="cin")

    def _lire(self, chemin, cible: dict, cle: str) -> None:
        with open(chemin, newline="", encoding="utf-8") as fh:
            for ligne in csv.DictReader(fh, delimiter=";"):
                if ligne.get(cle):
                    cible[ligne[cle].strip().upper()] = _normaliser_champs(ligne)

    def cherche_titulaire(self, plaque: str) -> dict[str, Any] | None:
        return self._vehicules.get(normaliser_plaque(plaque))

    def cherche_identite(self, cin: str) -> dict[str, Any] | None:
        return self._identites.get(cin.upper())


class HttpRegistryConnector:
    """Endpoint REST du registre habite : GET ?plaque=... / ?cin=... avec Bearer.

    Le jeton est lu depuis la variable d'environnement NOMMEE par la configuration
    (jamais stocke en clair) et n'apparait jamais dans les journaux.
    """

    def __init__(self, cfg: RegistriesConfig) -> None:
        self._cfg = cfg

    def _get(self, url: str, params: dict[str, str]) -> dict[str, Any] | None:
        import httpx

        jeton = os.environ.get(self._cfg.jeton_env, "")
        headers = {"Authorization": f"Bearer {jeton}"} if jeton else {}
        try:
            reponse = httpx.get(url, params=params, headers=headers, timeout=10.0)
        except Exception as exc:
            raise RegistryUnavailable(f"registre injoignable : {type(exc).__name__}") from exc
        if reponse.status_code == 404:
            return None
        if reponse.status_code != 200:
            raise RegistryUnavailable(f"registre reponse {reponse.status_code}")
        return _normaliser_champs(reponse.json())

    def cherche_titulaire(self, plaque: str) -> dict[str, Any] | None:
        if not self._cfg.url_immatriculation:
            raise RegistryUnavailable("url_immatriculation non configuree")
        return self._get(self._cfg.url_immatriculation, {"plaque": normaliser_plaque(plaque)})

    def cherche_identite(self, cin: str) -> dict[str, Any] | None:
        if not self._cfg.url_identite:
            raise RegistryUnavailable("url_identite non configuree")
        return self._get(self._cfg.url_identite, {"cin": cin})


def creer_connecteur(cfg: RegistriesConfig) -> RegistryConnector:
    if cfg.fournisseur == "mock":
        return MockRegistryConnector()
    if cfg.fournisseur == "offline":
        return OfflineRegistryConnector(cfg.fichier_extract)
    return HttpRegistryConnector(cfg)


def masquer_cin(cin: str) -> str:
    return (cin[:2] + "***" + cin[-1]) if len(cin) >= 4 else "***"


def masquer_plaque(plaque: str) -> str:
    """Pour les journaux : la plaque n'est jamais ecrite en clair dans les logs."""
    return (plaque[:2] + "***" + plaque[-1]) if len(plaque) >= 4 else "***"


class RegistryService:
    """Facade registres : garde-fous legaux + audit + limitation + masquage par role."""

    def __init__(self, cfg: RegistriesConfig, connecteur: RegistryConnector | None = None,
                 audit_fn: Callable[..., None] | None = None) -> None:
        self.cfg = cfg
        self._connecteur = connecteur or creer_connecteur(cfg)
        self._audit = audit_fn
        self._fenetres: dict[str, deque[float]] = {}

    # ---- garde-fous -----------------------------------------------------------
    def _gardes(self, utilisateur: str) -> None:
        if not self.cfg.active:
            raise RegistryInactive("registres inactifs : habilitation legale requise")
        if not self.cfg.base_legale:
            raise RegistryInactive("base_legale non consignee : activation refusee")
        fenetre = self._fenetres.setdefault(utilisateur, deque(maxlen=200))
        maintenant = time.monotonic()
        while fenetre and maintenant - fenetre[0] > 60.0:
            fenetre.popleft()
        if len(fenetre) >= max(1, self.cfg.limite_minute):
            raise RegistryRateLimited(
                f"limite de {self.cfg.limite_minute} interrogations/minute atteinte")
        fenetre.append(maintenant)

    def _tracer(self, action: str, utilisateur: str, cible: str, details: dict) -> None:
        if self._audit:
            self._audit(action=action, username=utilisateur, target=cible, details=details)
        log.info("interrogation registre", extra={"ctx": {"action": action, "utilisateur": utilisateur, **details}})

    # ---- interrogations ---------------------------------------------------------
    def identifier_vehicule(self, plaque: str, utilisateur: str,
                            dossier_uuid: str | None = None, role: str = "operateur") -> dict[str, Any]:
        """Plaque -> titulaire. Finalite obligatoire : instruction d'un dossier."""
        self._gardes(utilisateur)
        plaque_norm = normaliser_plaque(plaque)
        self._tracer("registre_vehicule", utilisateur, f"dossier:{dossier_uuid or '-'}",
                     {"plaque": masquer_plaque(plaque_norm), "fournisseur": self.cfg.fournisseur})
        brut = self._connecteur.cherche_titulaire(plaque_norm)
        if brut is None:
            return {"trouve": False, "plaque": plaque_norm, "source": self.cfg.fournisseur,
                    "horodatage": datetime.now(timezone.utc).isoformat()}
        record = TitulaireVehicule(
            plaque=brut.get("plaque", plaque_norm), nom=str(brut.get("nom", "")),
            prenom=str(brut.get("prenom", "")), cin=str(brut.get("cin", "")),
            vehicule=" ".join(str(brut.get(k, "")) for k in ("marque", "modele")).strip(),
            couleur=str(brut.get("couleur", "")))
        return {"trouve": True, "source": self.cfg.fournisseur,
                "horodatage": datetime.now(timezone.utc).isoformat(),
                **self._masquer_vehicule(record, role)}

    def identifier_identite(self, cin: str, utilisateur: str,
                            dossier_uuid: str | None = None, role: str = "operateur") -> dict[str, Any]:
        """Numero de CIN -> identite. Meme finalite et meme garde-fous."""
        self._gardes(utilisateur)
        self._tracer("registre_identite", utilisateur, f"dossier:{dossier_uuid or '-'}",
                     {"cin": masquer_cin(cin), "fournisseur": self.cfg.fournisseur})
        brut = self._connecteur.cherche_identite(cin)
        if brut is None:
            return {"trouve": False, "cin": cin, "source": self.cfg.fournisseur,
                    "horodatage": datetime.now(timezone.utc).isoformat()}
        record = IdentitePersonne(cin=str(brut.get("cin", cin)), nom=str(brut.get("nom", "")),
                                  prenom=str(brut.get("prenom", "")),
                                  date_naissance=str(brut.get("date_naissance", "")),
                                  adresse=str(brut.get("adresse", "")))
        return {"trouve": True, "source": self.cfg.fournisseur,
                "horodatage": datetime.now(timezone.utc).isoformat(),
                **self._masquer_identite(record, role)}

    # ---- masquage par role -------------------------------------------------------
    def _masquer_vehicule(self, record: TitulaireVehicule, role: str) -> dict[str, Any]:
        if role == "admin":
            return {"plaque": record.plaque, "nom": record.nom, "prenom": record.prenom,
                    "cin": record.cin, "vehicule": record.vehicule, "couleur": record.couleur}
        return {"plaque": record.plaque, "nom": record.nom, "prenom": record.prenom,
                "cin": masquer_cin(record.cin) if record.cin else "",
                "vehicule": record.vehicule, "couleur": record.couleur}

    def _masquer_identite(self, record: IdentitePersonne, role: str) -> dict[str, Any]:
        base = {"cin": record.cin, "nom": record.nom, "prenom": record.prenom,
                "date_naissance": record.date_naissance}
        if role == "admin":
            base["adresse"] = record.adresse
            return base
        base["cin"] = masquer_cin(record.cin)
        if self.cfg.masquer_adresse:
            base["adresse"] = "***"
        return base

    def etat(self) -> dict[str, Any]:
        return {"actif": self.cfg.active, "base_legale": self.cfg.base_legale,
                "fournisseur": self.cfg.fournisseur, "limite_minute": self.cfg.limite_minute,
                "masquer_adresse": self.cfg.masquer_adresse,
                "connecteur": type(self._connecteur).__name__}
