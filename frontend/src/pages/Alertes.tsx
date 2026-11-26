// Alertes : filtres (statut, gravité, caméra, période), actions Acquitter /
// Résoudre selon le rôle, flux temps réel WebSocket (nouvelles alertes en haut
// + notification toast).
import { useCallback, useEffect, useState } from 'react';
import { BellOff, Check, RefreshCw, ShieldCheck } from 'lucide-react';
import { api, ApiError } from '../api/client';
import type { Alerte, Camera, MessageWsAlerte } from '../api/types';
import { Badge, Card, DataTable, Erreur, PageHeader } from '../components/ui';
import type { Colonne } from '../components/ui';
import { useAuth } from '../state/AuthContext';
import { useToast } from '../state/ToastContext';
import { estAlerteWs, useAlertesTempsReel } from '../hooks/useAlertesTempsReel';
import {
  classesGravite,
  classesStatutAlerte,
  dateFr,
  libelleGravite,
  libelleStatutAlerte,
  libelleType,
} from '../utils/format';
import { useTitrePage } from '../hooks/useTitrePage';

const STATUTS = [
  { valeur: 'tous', libelle: 'Tous les statuts' },
  { valeur: 'nouveau', libelle: 'Nouveau' },
  { valeur: 'acquittee', libelle: 'Acquittée' },
  { valeur: 'resolue', libelle: 'Résolue' },
];
const GRAVITES = [
  { valeur: 'toutes', libelle: 'Toutes les gravités' },
  { valeur: 'critical', libelle: 'Critique' },
  { valeur: 'warning', libelle: 'Avertissement' },
  { valeur: 'info', libelle: 'Information' },
];
const PERIODES = [1, 7, 30];
const TAILLE_PAGE = 50;

export default function Alertes() {
  useTitrePage('Alertes');
  const { peutOperation, utilisateur } = useAuth();
  const { notifier } = useToast();
  const [alertes, setAlertes] = useState<Alerte[] | null>(null);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [erreur, setErreur] = useState<string | null>(null);
  const [statut, setStatut] = useState('tous');
  const [gravite, setGravite] = useState('toutes');
  const [camera, setCamera] = useState('toutes');
  const [days, setDays] = useState(7);
  const [offset, setOffset] = useState(0);

  const charger = useCallback(async () => {
    try {
      const liste = await api.alertes({
        statut: statut === 'tous' ? undefined : statut,
        gravite: gravite === 'toutes' ? undefined : gravite,
        camera: camera === 'toutes' ? undefined : camera,
        days,
        limit: TAILLE_PAGE,
        offset,
      });
      setAlertes(liste);
      setErreur(null);
    } catch (exc) {
      setErreur(exc instanceof Error ? exc.message : 'Erreur inconnue');
    }
  }, [statut, gravite, camera, days, offset]);

  useEffect(() => {
    void charger();
  }, [charger]);

  useEffect(() => {
    api
      .cameras()
      .then(setCameras)
      .catch(() => {
        /* liste de filtre indisponible : pas bloquant */
      });
  }, []);

  useEffect(() => {
    setOffset(0);
  }, [statut, gravite, camera, days]);

  // WebSocket temps réel : les nouvelles alertes s'ajoutent en haut + toast.
  const surNouvelleAlerte = useCallback(
    (message: MessageWsAlerte) => {
      if (!estAlerteWs(message)) return;
      const nouvelle: Alerte = {
        uuid: message.uuid,
        ts: new Date().toISOString(),
        type: message.type ?? 'inconnu',
        gravite: message.severity,
        message: message.message,
        camera: message.camera_id ?? null,
        statut: 'nouveau',
        acquittee_par: null,
        resolue_par: null,
        payload: message as Record<string, unknown>,
      };
      setAlertes((liste) => (liste ? [nouvelle, ...liste] : [nouvelle]));
      notifier(`Nouvelle alerte (${libelleGravite(nouvelle.gravite)}) : ${nouvelle.message}`, 'avertissement');
    },
    [notifier],
  );
  useAlertesTempsReel(surNouvelleAlerte, true);

  const acquitter = async (a: Alerte) => {
    try {
      await api.acquitterAlerte(a.uuid);
      notifier(`Alerte acquittée par ${utilisateur?.username ?? '—'}`, 'succes');
      await charger();
    } catch (exc) {
      notifier(exc instanceof ApiError ? exc.message : 'Acquittement impossible', 'erreur');
    }
  };

  const resoudre = async (a: Alerte) => {
    try {
      await api.resoudreAlerte(a.uuid);
      notifier(`Alerte résolue par ${utilisateur?.username ?? '—'}`, 'succes');
      await charger();
    } catch (exc) {
      notifier(exc instanceof ApiError ? exc.message : 'Résolution impossible', 'erreur');
    }
  };

  const colonnes: Colonne<Alerte>[] = [
    {
      cle: 'ts',
      libelle: 'Horodatage',
      rendu: (a) => <span className="text-dim text-xs whitespace-nowrap">{dateFr(a.ts)}</span>,
    },
    {
      cle: 'gravite',
      libelle: 'Gravité',
      rendu: (a) => <Badge classes={classesGravite(a.gravite)}>{libelleGravite(a.gravite)}</Badge>,
    },
    { cle: 'type', libelle: 'Type', rendu: (a) => <span className="text-sm">{libelleType(a.type)}</span> },
    {
      cle: 'message',
      libelle: 'Message',
      rendu: (a) => <span className="text-sm block max-w-[420px] break-words">{a.message}</span>,
    },
    { cle: 'camera', libelle: 'Caméra', rendu: (a) => <span className="font-mono text-xs text-acc">{a.camera ?? '—'}</span> },
    {
      cle: 'statut',
      libelle: 'Statut',
      rendu: (a) => (
        <div className="space-y-1">
          <Badge classes={classesStatutAlerte(a.statut)}>{libelleStatutAlerte(a.statut)}</Badge>
          {(a.acquittee_par || a.resolue_par) && (
            <p className="text-[11px] text-dim">
              {a.acquittee_par && `acq. ${a.acquittee_par}`}
              {a.resolue_par && ` · rés. ${a.resolue_par}`}
            </p>
          )}
        </div>
      ),
    },
    {
      cle: 'actions',
      libelle: 'Actions',
      rendu: (a) =>
        peutOperation ? (
          <div className="flex items-center gap-1.5">
            {a.statut === 'nouveau' && (
              <button type="button" onClick={() => void acquitter(a)} className="btn-neutre !px-2 !py-1 text-xs">
                <Check size={13} /> Acquitter
              </button>
            )}
            {a.statut !== 'resolue' && (
              <button type="button" onClick={() => void resoudre(a)} className="btn-succes !px-2 !py-1 text-xs">
                <ShieldCheck size={13} /> Résoudre
              </button>
            )}
          </div>
        ) : (
          <span className="text-xs text-dim">Lecture seule</span>
        ),
    },
  ];

  const pagePrecedente = offset > 0;
  const pageSuivante = alertes !== null && alertes.length === TAILLE_PAGE;

  return (
    <>
      <PageHeader
        titre="Alertes"
        description="Gestion des alertes de sécurité. Le flux temps réel est actif : les nouvelles alertes apparaissent automatiquement en tête de liste."
        actions={
          <button type="button" onClick={() => void charger()} className="btn-neutre">
            <RefreshCw size={15} /> Actualiser
          </button>
        }
      />

      <Card className="mb-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <label className="block">
            <span className="block text-xs uppercase tracking-wide text-dim mb-1">Statut</span>
            <select className="champ" value={statut} onChange={(e) => setStatut(e.target.value)}>
              {STATUTS.map((s) => (
                <option key={s.valeur} value={s.valeur}>
                  {s.libelle}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="block text-xs uppercase tracking-wide text-dim mb-1">Gravité</span>
            <select className="champ" value={gravite} onChange={(e) => setGravite(e.target.value)}>
              {GRAVITES.map((g) => (
                <option key={g.valeur} value={g.valeur}>
                  {g.libelle}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="block text-xs uppercase tracking-wide text-dim mb-1">Caméra</span>
            <select className="champ" value={camera} onChange={(e) => setCamera(e.target.value)}>
              <option value="toutes">Toutes les caméras</option>
              {cameras.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nom} ({c.id})
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="block text-xs uppercase tracking-wide text-dim mb-1">Période</span>
            <select className="champ" value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {PERIODES.map((p) => (
                <option key={p} value={p}>
                  {p === 1 ? 'Dernières 24 heures' : `Derniers ${p} jours`}
                </option>
              ))}
            </select>
          </label>
        </div>
      </Card>

      {erreur && <div className="mb-4"><Erreur message={erreur} /></div>}

      <Card>
        <DataTable
          colonnes={colonnes}
          lignes={alertes}
          cle={(a) => a.uuid}
          vide={
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <BellOff size={28} className="text-dim" />
              <p className="text-sm font-medium text-ink">Aucune alerte sur ces critères</p>
              <p className="text-xs text-dim">Élargissez la période ou changez les filtres.</p>
            </div>
          }
        />
        <div className="flex items-center justify-between gap-3 pt-3 mt-1 border-t border-edge text-xs text-dim">
          <span>
            {alertes ? `${offset + 1} – ${offset + (alertes?.length ?? 0)}` : '—'} · 50 alertes par page
          </span>
          <div className="flex gap-2">
            <button type="button" className="btn-neutre !py-1 !px-2" disabled={!pagePrecedente} onClick={() => setOffset(Math.max(0, offset - TAILLE_PAGE))}>
              Précédent
            </button>
            <button type="button" className="btn-neutre !py-1 !px-2" disabled={!pageSuivante} onClick={() => setOffset(offset + TAILLE_PAGE)}>
              Suivant
            </button>
          </div>
        </div>
      </Card>
    </>
  );
}
