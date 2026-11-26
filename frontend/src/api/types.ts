// Types du contrat API GAtraking (cf. ga/operations/app.py) — champs 100 % français.

export type Role = 'admin' | 'operateur' | 'observateur';

export interface Utilisateur {
  username: string;
  role: Role;
}

export interface ReponseConnexion {
  token: string;
  utilisateur: Utilisateur;
}

// ---- caméras -------------------------------------------------------------
export interface CameraRuntime {
  camera_id: string;
  nom: string;
  source: string;
  actif: boolean;
  images_traitees: number;
  fps: number;
  pistes_actives: number;
  derniere_image: number | null;
  source_infos: {
    source: string;
    images_lues: number;
    reconnexions: number;
    derniere_erreur: string | null;
  };
}

export interface Camera {
  id: string;
  nom: string;
  source: string;
  active: boolean;
  fps_limite: number;
  position: { x: number; y: number };
  derniere_vue: string | null;
  runtime: CameraRuntime | null;
}

export interface CameraUpsert {
  id: string;
  name: string;
  source: string;
  enabled: boolean;
  fps_limit: number;
  location: { x: number; y: number };
}

// ---- alertes / événements -------------------------------------------------
export interface Alerte {
  uuid: string;
  ts: string;
  type: string;
  gravite: string;
  message: string;
  camera: string | null;
  statut: string;
  acquittee_par: string | null;
  resolue_par: string | null;
  payload: Record<string, unknown>;
}

export interface Evenement {
  uuid: string;
  ts: string;
  type: string;
  gravite: string;
  camera: string | null;
  payload: Record<string, unknown>;
}

export interface SerieJour {
  type: string;
  day: string;
  count: number;
}

export interface ResumeTableauDeBord {
  alertes_ouvertes: number;
  alertes_24h: number;
  evenements_24h: number;
  dossiers_a_verifier: number;
  cameras_total: number;
  cameras_en_ligne: number;
  serie_journaliere: SerieJour[];
  alertes_recentes: Alerte[];
}

// ---- dossiers --------------------------------------------------------------
export interface Dossier {
  uuid: string;
  ts: string;
  type: string;
  statut: string;
  camera: string | null;
  plaque: string | null;
  identifie: boolean;
  images: string[];
  metriques: Record<string, unknown>;
  decision_par: string | null;
  commentaire: string | null;
}

export interface DossierDetail extends Dossier {
  preuves: Record<string, unknown>;
  decision_ts: string | null;
  motif_contestation: string | null;
}

// identification du titulaire via les registres officiels (CIN masqué selon le rôle)
export interface IdentificationTitulaire {
  trouve: boolean;
  plaque?: string;
  source: string;
  horodatage: string;
  nom?: string;
  prenom?: string;
  cin?: string;
  vehicule?: string;
  couleur?: string;
}

export interface EtatRegistres {
  actif: boolean;
  base_legale: string;
  fournisseur: string;
  limite_minute: number;
  masquer_adresse: boolean;
  connecteur: string;
}

// ---- utilisateurs -----------------------------------------------------------
export interface UtilisateurItem {
  id: number;
  username: string;
  role: Role;
  actif: boolean;
  derniere_connexion: string | null;
}

// ---- paramètres IA ------------------------------------------------------------
export interface ParametresIA {
  detector?: string;
  model_path?: string;
  conf_threshold: number;
  iou_threshold: number;
  speed_limit_kmh: number;
  intrusion_min_frames: number;
  [cle: string]: unknown;
}

export interface ReponseParametresIA {
  parametres: ParametresIA;
  note: string;
}

// ---- système -------------------------------------------------------------------
export interface RessourcesSysteme {
  cpu_percent: number;
  cpu_coeurs: number;
  ram_percent: number;
  ram_total_go: number;
  disque_percent: number;
  acceleration: { providers_onnx: string[]; detecteur: string };
  medias: Record<string, unknown>;
}

export interface EtatCloud {
  cloud_active: boolean;
  synchronisation: Record<string, unknown>;
  llm: { provider: string; modele: string; connecte: boolean };
}

export interface SanteModule {
  healthy: boolean;
  detail: string;
  uptime_s: number;
  [cle: string]: unknown;
}

export interface EntreeJournal {
  ts: string;
  level: string;
  logger: string;
  msg: string;
  ctx?: Record<string, unknown>;
  exc?: string;
  [cle: string]: unknown;
}

// ---- GA-INTELLIGENCE -------------------------------------------------------------
export interface Rapport {
  uuid: string;
  ts: string;
  periode: [string, string];
  genere_par: string;
  chemin: string;
}

export interface ReponseAssistant {
  reponse: string;
  source: string;
}

// ---- WebSocket /ws/alerts -----------------------------------------------------------
// NB : le champ « type » du message WS est écrasé par le type d'alerte (spread du
// payload côté serveur). On détecte donc une nouvelle alerte par la présence
// conjointe de uuid + message + severity.
export interface MessageWsAlerte {
  uuid: string;
  type: string;
  message: string;
  severity: string;
  camera_id?: string;
  [cle: string]: unknown;
}
