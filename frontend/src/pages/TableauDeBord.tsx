// Tableau de bord : 4 KPI, activité 7 jours (barres empilées par type),
// dernières alertes, état des caméras.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BellRing,
  Camera as CameraIcon,
  FolderSearch,
  MonitorPlay,
  Radio,
  RefreshCw,
  Siren,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api } from '../api/client';
import type { Camera, ResumeTableauDeBord } from '../api/types';
import { Badge, Card, Chargement, Erreur, PageHeader } from '../components/ui';
import { classesGravite, classesStatutAlerte, dateFr, libelleGravite, libelleStatutAlerte, libelleType } from '../utils/format';
import { useTitrePage } from '../hooks/useTitrePage';

const COULEURS_SERIES = ['#22d3ee', '#6366f1', '#10b981', '#f59e0b', '#ef4444', '#a855f7', '#f472b6', '#94a3b8'];

function Kpi({
  icone,
  libelle,
  valeur,
  accent,
}: {
  icone: React.ReactNode;
  libelle: string;
  valeur: number | string;
  accent: string;
}) {
  return (
    <div className="bg-panel border border-edge rounded-lg p-4 flex items-center gap-3">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${accent}`}>{icone}</div>
      <div className="min-w-0">
        <p className="text-2xl font-bold leading-tight">{valeur}</p>
        <p className="text-xs text-dim truncate">{libelle}</p>
      </div>
    </div>
  );
}

export default function TableauDeBord() {
  useTitrePage('Tableau de bord');
  const navigate = useNavigate();
  const [resume, setResume] = useState<ResumeTableauDeBord | null>(null);
  const [cameras, setCameras] = useState<Camera[] | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [rafraichit, setRafraichit] = useState(false);

  const charger = useCallback(async () => {
    setRafraichit(true);
    try {
      const [r, c] = await Promise.all([api.resume(), api.cameras()]);
      setResume(r);
      setCameras(c);
      setErreur(null);
    } catch (exc) {
      setErreur(exc instanceof Error ? exc.message : 'Erreur inconnue');
    } finally {
      setRafraichit(false);
    }
  }, []);

  useEffect(() => {
    void charger();
    const interval = window.setInterval(() => void charger(), 60000);
    return () => window.clearInterval(interval);
  }, [charger]);

  const donneesGraphe = useMemo(() => {
    if (!resume) return [];
    const jours = new Set<string>();
    const types = new Set<string>();
    for (const s of resume.serie_journaliere) {
      jours.add(s.day);
      types.add(s.type);
    }
    const joursTries = Array.from(jours).sort();
    const typesListe = Array.from(types);
    return joursTries.map((jour) => {
      const ligne: Record<string, string | number> = { jour: jour.slice(5) };
      for (const t of typesListe) {
        const trouve = resume.serie_journaliere.find((s) => s.day === jour && s.type === t);
        ligne[t] = trouve?.count ?? 0;
      }
      return ligne;
    });
  }, [resume]);

  const typesGraphe = useMemo(() => {
    if (!resume) return [];
    return Array.from(new Set(resume.serie_journaliere.map((s) => s.type)));
  }, [resume]);

  if (erreur && resume === null) {
    return (
      <>
        <PageHeader titre="Tableau de bord" description="Vue d'ensemble de l'exploitation en temps réel." />
        <Erreur message={erreur} />
      </>
    );
  }

  if (!resume || !cameras) {
    return <Chargement texte="Chargement du tableau de bord…" />;
  }

  return (
    <>
      <PageHeader
        titre="Tableau de bord"
        description="Vue d'ensemble de l'exploitation : alertes, événements, dossiers et parc caméras."
        actions={
          <button type="button" onClick={() => void charger()} className="btn-neutre" disabled={rafraichit}>
            <RefreshCw size={15} className={rafraichit ? 'animate-spin' : ''} /> Actualiser
          </button>
        }
      />
      {erreur && <div className="mb-4"><Erreur message={erreur} /></div>}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <Kpi icone={<Siren size={18} />} libelle="Alertes ouvertes" valeur={resume.alertes_ouvertes} accent="bg-danger/15 text-danger" />
        <Kpi icone={<BellRing size={18} />} libelle="Alertes 24 h" valeur={resume.alertes_24h} accent="bg-warn/15 text-warn" />
        <Kpi icone={<Radio size={18} />} libelle="Événements 24 h" valeur={resume.evenements_24h} accent="bg-acc/15 text-acc" />
        <Kpi icone={<FolderSearch size={18} />} libelle="Dossiers à vérifier" valeur={resume.dossiers_a_verifier} accent="bg-indigo-500/15 text-indigo-400" />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card titre="Activité des 7 derniers jours (événements par jour)" className="xl:col-span-2">
          {donneesGraphe.length === 0 ? (
            <p className="text-sm text-dim py-8 text-center">Aucun événement enregistré sur la période.</p>
          ) : (
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={donneesGraphe} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e2a44" vertical={false} />
                  <XAxis dataKey="jour" tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={{ stroke: '#1e2a44' }} tickLine={false} />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={{ stroke: '#1e2a44' }} tickLine={false} allowDecimals={false} />
                  <RechartsTooltip
                    cursor={{ fill: '#152238' }}
                    contentStyle={{ background: '#101a2e', border: '1px solid #1e2a44', borderRadius: 8, fontSize: 12 }}
                    labelStyle={{ color: '#e2e8f0' }}
                    itemStyle={{ color: '#e2e8f0' }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  {typesGraphe.map((t, i) => (
                    <Bar
                      key={t}
                      dataKey={t}
                      name={libelleType(t)}
                      stackId="jour"
                      fill={COULEURS_SERIES[i % COULEURS_SERIES.length]}
                      radius={i === typesGraphe.length - 1 ? [3, 3, 0, 0] : [0, 0, 0, 0]}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card
          titre="Dernières alertes"
          actions={
            <button type="button" onClick={() => navigate('/alertes')} className="text-xs text-acc hover:underline">
              Tout voir
            </button>
          }
          corpsClassName="p-0"
        >
          {resume.alertes_recentes.length === 0 ? (
            <p className="text-sm text-dim py-8 text-center">Aucune alerte sur les 7 derniers jours.</p>
          ) : (
            <ul className="divide-y divide-edge/60 max-h-80 overflow-y-auto">
              {resume.alertes_recentes.map((a) => (
                <li key={a.uuid} className="px-4 py-2.5">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <Badge classes={classesGravite(a.gravite)}>{libelleGravite(a.gravite)}</Badge>
                    <span className="text-[11px] text-dim">{dateFr(a.ts)}</span>
                  </div>
                  <p className="text-sm text-ink line-clamp-2">{a.message}</p>
                  <div className="flex items-center gap-2 mt-1 text-[11px] text-dim">
                    <span>{libelleType(a.type)}</span>
                    {a.camera && <span className="font-mono">· {a.camera}</span>}
                    <Badge classes={classesStatutAlerte(a.statut)}>{libelleStatutAlerte(a.statut)}</Badge>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card titre="État des caméras" className="mt-4">
        {cameras.length === 0 ? (
          <p className="text-sm text-dim text-center py-6">Aucune caméra configurée.</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {cameras.map((c) => {
              const enLigne = c.runtime?.actif === true;
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => navigate('/mur-video')}
                  className="text-left bg-panel-soft border border-edge rounded-lg p-3 hover:border-acc/50 transition"
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className="text-sm font-semibold truncate">{c.nom}</span>
                    <Badge classes={enLigne ? 'bg-ok/15 text-ok border-ok/40' : 'bg-danger/15 text-danger border-danger/40'}>
                      {enLigne ? 'En ligne' : 'Hors ligne'}
                    </Badge>
                  </div>
                  <p className="text-xs text-dim font-mono truncate">{c.id}</p>
                  <div className="flex items-center gap-3 mt-2 text-xs text-dim">
                    <span className="inline-flex items-center gap-1">
                      <CameraIcon size={12} /> {c.active ? 'Active' : 'Désactivée'}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <MonitorPlay size={12} /> {c.runtime ? `${c.runtime.fps.toFixed(1)} img/s` : '—'}
                    </span>
                    <span>{c.runtime ? `${c.runtime.pistes_actives} piste(s)` : ''}</span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </Card>
    </>
  );
}
