// Événements : historique filtrable (type, caméra, période), pagination simple,
// payload consultable par ligne.
import { useCallback, useEffect, useState } from 'react';
import { Activity, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import type { Camera, Evenement, SerieJour } from '../api/types';
import { Badge, Card, DataTable, Erreur, PageHeader } from '../components/ui';
import type { Colonne } from '../components/ui';
import { classesGravite, dateFr, libelleGravite, libelleType } from '../utils/format';
import { useTitrePage } from '../hooks/useTitrePage';

const PERIODES = [1, 7, 30];
const TAILLE_PAGE = 50;

export default function Evenements() {
  useTitrePage('Événements');
  const [evenements, setEvenements] = useState<Evenement[] | null>(null);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [types, setTypes] = useState<string[]>([]);
  const [erreur, setErreur] = useState<string | null>(null);
  const [camera, setCamera] = useState('toutes');
  const [type, setType] = useState('tous');
  const [days, setDays] = useState(7);
  const [offset, setOffset] = useState(0);
  const [ouvert, setOuvert] = useState<string | null>(null);

  const charger = useCallback(async () => {
    try {
      const liste = await api.evenements({
        camera: camera === 'toutes' ? undefined : camera,
        type: type === 'tous' ? undefined : type,
        days,
        limit: TAILLE_PAGE,
        offset,
      });
      setEvenements(liste);
      setErreur(null);
    } catch (exc) {
      setErreur(exc instanceof Error ? exc.message : 'Erreur inconnue');
    }
  }, [camera, type, days, offset]);

  useEffect(() => {
    void charger();
  }, [charger]);

  useEffect(() => {
    Promise.all([api.cameras(), api.seriesEvenements(30)])
      .then(([cams, series]: [Camera[], SerieJour[]]) => {
        setCameras(cams);
        setTypes(Array.from(new Set(series.map((s) => s.type))).sort());
      })
      .catch(() => {
        /* filtres indisponibles : pas bloquant */
      });
  }, []);

  useEffect(() => {
    setOffset(0);
  }, [camera, type, days]);

  const colonnes: Colonne<Evenement>[] = [
    {
      cle: 'ts',
      libelle: 'Horodatage',
      rendu: (e) => <span className="text-dim text-xs whitespace-nowrap">{dateFr(e.ts)}</span>,
    },
    {
      cle: 'type',
      libelle: 'Type',
      rendu: (e) => <span className="text-sm">{libelleType(e.type)}</span>,
    },
    {
      cle: 'gravite',
      libelle: 'Gravité',
      rendu: (e) => <Badge classes={classesGravite(e.gravite)}>{libelleGravite(e.gravite)}</Badge>,
    },
    { cle: 'camera', libelle: 'Caméra', rendu: (e) => <span className="font-mono text-xs text-acc">{e.camera ?? '—'}</span> },
    {
      cle: 'payload',
      libelle: 'Détails',
      rendu: (e) => (
        <button
          type="button"
          onClick={(ev) => {
            ev.stopPropagation();
            setOuvert((o) => (o === e.uuid ? null : e.uuid));
          }}
          className="text-xs text-acc hover:underline"
        >
          {ouvert === e.uuid ? 'Masquer' : 'Afficher'}
        </button>
      ),
    },
  ];

  const pagePrecedente = offset > 0;
  const pageSuivante = evenements !== null && evenements.length === TAILLE_PAGE;

  return (
    <>
      <PageHeader
        titre="Événements"
        description="Historique des événements détectés par les modules vision, route et security (détections, comptages, pistes…)."
        actions={
          <button type="button" onClick={() => void charger()} className="btn-neutre">
            <RefreshCw size={15} /> Actualiser
          </button>
        }
      />

      <Card className="mb-4">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          <label className="block">
            <span className="block text-xs uppercase tracking-wide text-dim mb-1">Type</span>
            <select className="champ" value={type} onChange={(e) => setType(e.target.value)}>
              <option value="tous">Tous les types</option>
              {types.map((t) => (
                <option key={t} value={t}>
                  {libelleType(t)} ({t})
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
          lignes={evenements}
          cle={(e) => e.uuid}
          vide={
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <Activity size={28} className="text-dim" />
              <p className="text-sm font-medium text-ink">Aucun événement sur ces critères</p>
              <p className="text-xs text-dim">Élargissez la période ou changez les filtres.</p>
            </div>
          }
        />
        {ouvert && evenements?.find((e) => e.uuid === ouvert) && (
          <div className="mt-2 rounded-md border border-edge bg-app p-3">
            <p className="text-xs uppercase tracking-wide text-dim mb-1.5">
              Charge utile — {libelleType(evenements.find((e) => e.uuid === ouvert)?.type ?? '')}
            </p>
            <pre className="text-xs text-acc font-mono whitespace-pre-wrap break-all max-h-48 overflow-y-auto">
              {JSON.stringify(evenements.find((e) => e.uuid === ouvert)?.payload ?? {}, null, 2)}
            </pre>
          </div>
        )}
        <div className="flex items-center justify-between gap-3 pt-3 mt-1 border-t border-edge text-xs text-dim">
          <span>{evenements ? `${offset} – ${offset + (evenements?.length ?? 0)}` : '—'} · 50 événements par page</span>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-neutre !py-1 !px-2"
              disabled={!pagePrecedente}
              onClick={() => setOffset(Math.max(0, offset - TAILLE_PAGE))}
            >
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
