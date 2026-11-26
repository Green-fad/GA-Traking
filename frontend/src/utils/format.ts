// Utilitaires de formatage : dates françaises, libellés et couleurs de badges.
import type { Role } from '../api/types';

export function dateFr(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function heureFr(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

const LIBELLES_TYPES: Record<string, string> = {
  anomalie: 'Anomalie',
  incendie_suspecte: 'Incendie suspecté',
  intrusion: 'Intrusion',
  exces_vitesse: 'Excès de vitesse',
  mauvaise_direction: 'Mauvaise direction',
  vehicule_arrete: 'Véhicule arrêté',
  densite_anormale: 'Densité anormale',
  comptage: 'Comptage',
  security_intrusion: 'Intrusion',
  security_fire_suspected: 'Incendie suspecté',
  security_anomaly: 'Anomalie',
  road_speed_event: 'Excès de vitesse',
  road_traffic_event: 'Trafic',
  road_count_update: 'Comptage',
};

export function libelleType(type: string | null | undefined): string {
  if (!type) return '—';
  const direct = LIBELLES_TYPES[type];
  if (direct) return direct;
  const sansPrefixe = type.includes('.') ? type.split('.').slice(1).join('.') : type;
  return LIBELLES_TYPES[sansPrefixe] ?? sansPrefixe.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
}

const LIBELLES_GRAVITE: Record<string, string> = {
  info: 'Information',
  warning: 'Avertissement',
  critical: 'Critique',
};

export function libelleGravite(g: string | null | undefined): string {
  if (!g) return '—';
  return LIBELLES_GRAVITE[g] ?? g;
}

export function classesGravite(g: string | null | undefined): string {
  switch (g) {
    case 'critical':
      return 'bg-danger/15 text-danger border-danger/40';
    case 'warning':
      return 'bg-warn/15 text-warn border-warn/40';
    case 'info':
      return 'bg-acc/15 text-acc border-acc/40';
    default:
      return 'bg-panel-soft text-dim border-edge';
  }
}

const LIBELLES_STATUT_ALERTE: Record<string, string> = {
  nouveau: 'Nouveau',
  acquittee: 'Acquittée',
  resolue: 'Résolue',
};

export function libelleStatutAlerte(s: string | null | undefined): string {
  if (!s) return '—';
  return LIBELLES_STATUT_ALERTE[s] ?? s;
}

export function classesStatutAlerte(s: string | null | undefined): string {
  switch (s) {
    case 'nouveau':
      return 'bg-danger/15 text-danger border-danger/40';
    case 'acquittee':
      return 'bg-warn/15 text-warn border-warn/40';
    case 'resolue':
      return 'bg-ok/15 text-ok border-ok/40';
    default:
      return 'bg-panel-soft text-dim border-edge';
  }
}

const LIBELLES_STATUT_DOSSIER: Record<string, string> = {
  a_verifier: 'À vérifier',
  valide: 'Validé',
  rejete: 'Rejeté',
  conteste: 'Contesté',
};

export function libelleStatutDossier(s: string | null | undefined): string {
  if (!s) return '—';
  return LIBELLES_STATUT_DOSSIER[s] ?? s;
}

export function classesStatutDossier(s: string | null | undefined): string {
  switch (s) {
    case 'a_verifier':
      return 'bg-warn/15 text-warn border-warn/40';
    case 'valide':
      return 'bg-ok/15 text-ok border-ok/40';
    case 'rejete':
      return 'bg-danger/15 text-danger border-danger/40';
    case 'conteste':
      return 'bg-indigo-500/15 text-indigo-400 border-indigo-500/40';
    default:
      return 'bg-panel-soft text-dim border-edge';
  }
}

const LIBELLES_ROLES: Record<Role, string> = {
  admin: 'Administrateur',
  operateur: 'Opérateur',
  observateur: 'Observateur',
};

export function libelleRole(r: Role | string | null | undefined): string {
  if (!r) return '—';
  return LIBELLES_ROLES[r as Role] ?? r;
}

export function classesRole(r: Role | string | null | undefined): string {
  switch (r) {
    case 'admin':
      return 'bg-danger/15 text-danger border-danger/40';
    case 'operateur':
      return 'bg-acc/15 text-acc border-acc/40';
    default:
      return 'bg-indigo-500/15 text-indigo-400 border-indigo-500/40';
  }
}

export function rangRole(r: Role | string): number {
  switch (r) {
    case 'admin':
      return 3;
    case 'operateur':
      return 2;
    default:
      return 1;
  }
}
