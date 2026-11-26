// Client fetch typé pour l'API GAtraking. Base « /api », jeton Bearer injecté
// depuis le localStorage (« ga_token »), déconnexion automatique sur 401.
import type {
  Alerte,
  Camera,
  CameraUpsert,
  Dossier,
  DossierDetail,
  EntreeJournal,
  EtatCloud,
  Evenement,
  ParametresIA,
  Rapport,
  ReponseAssistant,
  ReponseConnexion,
  ReponseParametresIA,
  RessourcesSysteme,
  ResumeTableauDeBord,
  SerieJour,
  SanteModule,
  Utilisateur,
  UtilisateurItem,
} from './types';

export const BASE = '/api';
export const CLE_JETON = 'ga_token';
export const EVENEMENT_DECONNEXION = 'ga:deconnexion';

export function obtenirJeton(): string | null {
  return localStorage.getItem(CLE_JETON);
}

export function definirJeton(jeton: string): void {
  localStorage.setItem(CLE_JETON, jeton);
}

export function effacerJeton(): void {
  localStorage.removeItem(CLE_JETON);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

// Options de requête : body accepte tout objet (sérialisé en JSON ci-dessous).
type OptionsRequete = Omit<RequestInit, 'body'> & { body?: unknown };

async function requete<T>(chemin: string, options: OptionsRequete = {}): Promise<T> {
  const entetes: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  };
  const jeton = obtenirJeton();
  if (jeton) entetes['Authorization'] = `Bearer ${jeton}`;

  const brut = options.body;
  let corps: BodyInit | null | undefined = undefined;
  if (brut !== undefined && brut !== null) {
    if (brut instanceof Blob || typeof brut === 'string') corps = brut;
    else {
      entetes['Content-Type'] = 'application/json';
      corps = JSON.stringify(brut);
    }
  }

  const reponse = await fetch(BASE + chemin, { ...options, headers: entetes, body: corps });

  if (reponse.status === 401) {
    effacerJeton();
    window.dispatchEvent(new Event(EVENEMENT_DECONNEXION));
    throw new ApiError(401, 'Session expirée — veuillez vous reconnecter');
  }
  if (!reponse.ok) {
    let message = `Erreur ${reponse.status}`;
    try {
      const donnees = (await reponse.json()) as { detail?: unknown };
      if (typeof donnees?.detail === 'string') message = donnees.detail;
      else if (donnees?.detail !== undefined) message = JSON.stringify(donnees.detail);
    } catch {
      /* corps non JSON : message par défaut */
    }
    throw new ApiError(reponse.status, message);
  }
  if (reponse.status === 204) return undefined as T;
  const typeContenu = reponse.headers.get('content-type') ?? '';
  if (typeContenu.includes('application/json')) return (await reponse.json()) as T;
  return (await reponse.blob()) as unknown as T;
}

function chaine(quest: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  for (const [cle, valeur] of Object.entries(quest)) {
    if (valeur !== undefined && valeur !== '' && valeur !== 'tous' && valeur !== 'toutes') {
      params.set(cle, String(valeur));
    }
  }
  const s = params.toString();
  return s ? `?${s}` : '';
}

// ---- authentification --------------------------------------------------------
export const api = {
  connexion: (username: string, password: string) =>
    requete<ReponseConnexion>('/auth/login', {
      method: 'POST',
      body: { username, password },
    }),
  moi: () => requete<Utilisateur>('/auth/me'),

  // ---- tableau de bord -----------------------------------------------------
  resume: () => requete<ResumeTableauDeBord>('/dashboard/summary'),

  // ---- caméras ---------------------------------------------------------------
  cameras: () => requete<Camera[]>('/cameras'),
  ajouterCamera: (donnees: CameraUpsert) => requete<{ id: string; note: string }>('/cameras', { method: 'POST', body: donnees }),
  modifierCamera: (id: string, donnees: CameraUpsert) => requete<{ id: string }>(`/cameras/${encodeURIComponent(id)}`, { method: 'PUT', body: donnees }),
  supprimerCamera: (id: string) => requete<{ supprimee: string }>(`/cameras/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  instantaneCamera: (id: string) => requete<Blob>(`/cameras/${encodeURIComponent(id)}/snapshot`),

  // ---- alertes ------------------------------------------------------------------
  alertes: (filtres: { statut?: string; camera?: string; gravite?: string; days?: number; limit?: number; offset?: number }) =>
    requete<Alerte[]>(
      `/alerts${chaine({
        statut: filtres.statut,
        camera: filtres.camera,
        gravite: filtres.gravite,
        days: filtres.days,
        limit: filtres.limit,
        offset: filtres.offset,
      })}`,
    ),
  acquitterAlerte: (uuid: string) => requete<{ uuid: string; statut: string }>(`/alerts/${uuid}/ack`, { method: 'POST' }),
  resoudreAlerte: (uuid: string) => requete<{ uuid: string; statut: string }>(`/alerts/${uuid}/resolve`, { method: 'POST' }),

  // ---- événements -----------------------------------------------------------------
  evenements: (filtres: { camera?: string; type?: string; days?: number; limit?: number; offset?: number }) =>
    requete<Evenement[]>(
      `/events${chaine({
        camera: filtres.camera,
        type: filtres.type,
        days: filtres.days,
        limit: filtres.limit,
        offset: filtres.offset,
      })}`,
    ),
  seriesEvenements: (days = 7) => requete<SerieJour[]>(`/events/series${chaine({ days })}`),

  // ---- dossiers ----------------------------------------------------------------------
  dossiers: (statut?: string) => requete<Dossier[]>(`/dossiers${chaine({ statut, limit: 500 })}`),
  dossier: (uuid: string) => requete<DossierDetail>(`/dossiers/${uuid}`),
  deciderDossier: (uuid: string, decision: 'valide' | 'rejete', commentaire?: string) =>
    requete<{ uuid: string; statut: string }>(`/dossiers/${uuid}/decide`, {
      method: 'POST',
      body: { decision, comment: commentaire || null },
    }),
  contesterDossier: (uuid: string, motif: string) =>
    requete<{ uuid: string; statut: string }>(`/dossiers/${uuid}/contest`, { method: 'POST', body: { reason: motif } }),

  // ---- utilisateurs ---------------------------------------------------------------------
  utilisateurs: () => requete<UtilisateurItem[]>('/users'),
  creerUtilisateur: (username: string, password: string, role: string) =>
    requete<{ id: number; username: string; role: string }>('/users', { method: 'POST', body: { username, password, role } }),
  modifierUtilisateur: (id: number, donnees: { role?: string; active?: boolean; password?: string }) =>
    requete<{ id: number }>(`/users/${id}`, { method: 'PUT', body: donnees }),
  supprimerUtilisateur: (id: number) => requete<{ supprime: number }>(`/users/${id}`, { method: 'DELETE' }),

  // ---- paramètres IA ------------------------------------------------------------------------
  parametresIA: () => requete<ParametresIA>('/settings/ai'),
  enregistrerParametresIA: (valeurs: { conf_threshold?: number; iou_threshold?: number; speed_limit_kmh?: number; intrusion_min_frames?: number }) =>
    requete<ReponseParametresIA>('/settings/ai', { method: 'PUT', body: valeurs }),

  // ---- système ------------------------------------------------------------------------------
  ressources: () => requete<RessourcesSysteme>('/system/resources'),
  cloud: () => requete<EtatCloud>('/system/cloud'),
  modules: () => requete<Record<string, SanteModule>>('/system/modules'),
  journaux: (niveau?: string, limit = 300) => requete<EntreeJournal[]>(`/system/logs${chaine({ niveau, limit })}`),

  // ---- GA-INTELLIGENCE -------------------------------------------------------------------------
  rapports: () => requete<Rapport[]>('/intelligence/reports'),
  genererRapport: (days: number) => requete<Record<string, unknown>>('/intelligence/report', { method: 'POST', body: { days } }),
  assistant: (message: string) => requete<ReponseAssistant>('/intelligence/assistant', { method: 'POST', body: { message } }),
};

// ---- médias protégés ------------------------------------------------------------------------
// Les images (snapshots, preuves) exigent l'en-tête Authorization : un <img src>
// natif ne peut pas les charger — passer par fetch → blob → objectURL.
export async function chargerMediaBlob(chemin: string): Promise<Blob> {
  const jeton = obtenirJeton();
  const entetes: Record<string, string> = {};
  if (jeton) entetes['Authorization'] = `Bearer ${jeton}`;
  const reponse = await fetch(`${BASE}/media/${chemin.replace(/^\/+/, '')}`, { headers: entetes });
  if (!reponse.ok) throw new ApiError(reponse.status, 'média indisponible');
  return reponse.blob();
}

export function urlWebSocketAlertes(): string {
  const jeton = obtenirJeton() ?? '';
  const protocole = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${protocole}://${window.location.host}/ws/alerts?token=${encodeURIComponent(jeton)}`;
}
