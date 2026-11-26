// Système : onglets Ressources (CPU/RAM/disque/accélération), Cloud (sync + LLM),
// Modules (santé), Journaux (table JSON filtrable par niveau, rafraîchissement auto).
import { useCallback, useEffect, useState } from 'react';
import { Cloud, Cpu, HardDrive, HeartPulse, RefreshCw, ScrollText } from 'lucide-react';
import { api } from '../api/client';
import type { EntreeJournal, EtatCloud, RessourcesSysteme, SanteModule } from '../api/types';
import { Badge, Card, Chargement, Erreur, PageHeader } from '../components/ui';
import { heureFr } from '../utils/format';
import { useTitrePage } from '../hooks/useTitrePage';

const ONGLETS = [
  { id: 'ressources', libelle: 'Ressources', icone: Cpu },
  { id: 'cloud', libelle: 'Cloud', icone: Cloud },
  { id: 'modules', libelle: 'Modules', icone: HeartPulse },
  { id: 'journaux', libelle: 'Journaux', icone: ScrollText },
] as const;

type OngletId = (typeof ONGLETS)[number]['id'];

const NIVEAUX = ['tous', 'debug', 'info', 'warning', 'error', 'critical'];

function Jauge({ libelle, pourcent, detail }: { libelle: string; pourcent: number; detail: string }) {
  const couleur = pourcent > 80 ? 'bg-danger' : pourcent > 60 ? 'bg-warn' : 'bg-ok';
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-sm font-medium">{libelle}</span>
        <span className="text-sm text-dim">{pourcent.toFixed(0)} %</span>
      </div>
      <div className="h-2.5 rounded-full bg-panel-soft border border-edge overflow-hidden">
        <div className={`h-full ${couleur} transition-all`} style={{ width: `${Math.min(100, Math.max(0, pourcent))}%` }} />
      </div>
      <p className="mt-1 text-xs text-dim">{detail}</p>
    </div>
  );
}

function OngletRessources() {
  const [r, setR] = useState<RessourcesSysteme | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  const charger = useCallback(async () => {
    try {
      setR(await api.ressources());
      setErreur(null);
    } catch (exc) {
      setErreur(exc instanceof Error ? exc.message : 'Erreur inconnue');
    }
  }, []);

  useEffect(() => {
    void charger();
    const interval = window.setInterval(() => void charger(), 10000);
    return () => window.clearInterval(interval);
  }, [charger]);

  if (erreur) return <Erreur message={erreur} />;
  if (!r) return <Chargement texte="Mesure des ressources…" />;

  const medias = Object.entries(r.medias ?? {});

  return (
    <div className="space-y-4">
      <Card titre="Charge machine" actions={<button type="button" onClick={() => void charger()} className="btn-neutre !px-2 !py-1 text-xs"><RefreshCw size={13} /> Actualiser</button>}>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <Jauge libelle="CPU" pourcent={r.cpu_percent} detail={`${r.cpu_coeurs} cœurs logiques`} />
          <Jauge libelle="Mémoire vive" pourcent={r.ram_percent} detail={`total ${r.ram_total_go} Go`} />
          <Jauge libelle="Disque" pourcent={r.disque_percent} detail="volume de travail GAtraking" />
        </div>
      </Card>

      <Card titre="Accélération matérielle">
        <div className="flex flex-wrap items-center gap-2">
          <Badge classes="bg-acc/15 text-acc border-acc/40">
            <Cpu size={12} /> Détecteur : {r.acceleration.detecteur}
          </Badge>
          {r.acceleration.providers_onnx.length === 0 ? (
            <span className="text-sm text-dim">Aucun fournisseur ONNX Runtime disponible.</span>
          ) : (
            r.acceleration.providers_onnx.map((p) => (
              <Badge key={p} classes="bg-panel-soft text-dim border-edge">{p}</Badge>
            ))
          )}
        </div>
      </Card>

      <Card titre="Médias stockés">
        {medias.length === 0 ? (
          <p className="text-sm text-dim">Aucune statistique média disponible.</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {medias.map(([cle, valeur]) => (
              <div key={cle} className="bg-panel-soft border border-edge rounded-md px-3 py-2 flex items-center gap-2">
                <HardDrive size={14} className="text-acc shrink-0" />
                <div className="min-w-0">
                  <p className="text-[11px] text-dim truncate">{cle}</p>
                  <p className="text-sm font-semibold truncate">{String(valeur)}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function OngletCloud() {
  const [c, setC] = useState<EtatCloud | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    api
      .cloud()
      .then(setC)
      .catch((exc: unknown) => setErreur(exc instanceof Error ? exc.message : 'Erreur inconnue'));
  }, []);

  if (erreur) return <Erreur message={erreur} />;
  if (!c) return <Chargement texte="Consultation de l'état cloud…" />;

  return (
    <div className="space-y-4">
      <Card titre="Synchronisation cloud">
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <Badge classes={c.cloud_active ? 'bg-ok/15 text-ok border-ok/40' : 'bg-panel-soft text-dim border-edge'}>
            {c.cloud_active ? 'Cloud activé' : 'Cloud désactivé'}
          </Badge>
        </div>
        <pre className="text-xs text-acc font-mono bg-app border border-edge rounded-md p-3 overflow-x-auto max-h-60">
          {JSON.stringify(c.synchronisation ?? {}, null, 2)}
        </pre>
      </Card>
      <Card titre="Assistant LLM">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="bg-panel-soft border border-edge rounded-md px-3 py-2">
            <p className="text-[11px] text-dim">Fournisseur</p>
            <p className="text-sm font-semibold">{c.llm.provider}</p>
          </div>
          <div className="bg-panel-soft border border-edge rounded-md px-3 py-2">
            <p className="text-[11px] text-dim">Modèle</p>
            <p className="text-sm font-semibold">{c.llm.modele}</p>
          </div>
          <div className="bg-panel-soft border border-edge rounded-md px-3 py-2">
            <p className="text-[11px] text-dim">Connexion</p>
            <Badge classes={c.llm.connecte ? 'bg-ok/15 text-ok border-ok/40' : 'bg-danger/15 text-danger border-danger/40'}>
              {c.llm.connecte ? 'Connecté' : 'Non connecté'}
            </Badge>
          </div>
        </div>
      </Card>
    </div>
  );
}

function OngletModules() {
  const [modules, setModules] = useState<Record<string, SanteModule> | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  const charger = useCallback(async () => {
    try {
      setModules(await api.modules());
      setErreur(null);
    } catch (exc) {
      setErreur(exc instanceof Error ? exc.message : 'Erreur inconnue');
    }
  }, []);

  useEffect(() => {
    void charger();
    const interval = window.setInterval(() => void charger(), 15000);
    return () => window.clearInterval(interval);
  }, [charger]);

  if (erreur) return <Erreur message={erreur} />;
  if (!modules) return <Chargement texte="Diagnostic des modules…" />;

  const noms = Object.keys(modules).sort();

  return (
    <Card
      titre="Santé des modules"
      actions={
        <button type="button" onClick={() => void charger()} className="btn-neutre !px-2 !py-1 text-xs">
          <RefreshCw size={13} /> Actualiser
        </button>
      }
    >
      {noms.length === 0 ? (
        <p className="text-sm text-dim text-center py-6">Aucun module déclaré dans le registre.</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {noms.map((nom) => {
            const m = modules[nom];
            if (!m) return null;
            const extra = Object.entries(m).filter(
              ([cle]) => !['healthy', 'detail', 'uptime_s'].includes(cle),
            );
            return (
              <div key={nom} className="bg-panel-soft border border-edge rounded-lg p-3">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-sm font-semibold">{nom}</span>
                  <Badge classes={m.healthy ? 'bg-ok/15 text-ok border-ok/40' : 'bg-danger/15 text-danger border-danger/40'}>
                    {m.healthy ? 'Sain' : 'Dégradé'}
                  </Badge>
                </div>
                <p className="text-xs text-dim mb-2">
                  {m.detail} · démarré depuis {Math.round(m.uptime_s)} s
                </p>
                {extra.length > 0 && (
                  <pre className="text-[11px] text-acc font-mono bg-app rounded p-2 overflow-x-auto max-h-32">
                    {JSON.stringify(Object.fromEntries(extra), null, 2)}
                  </pre>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

function OngletJournaux() {
  const [entrees, setEntrees] = useState<EntreeJournal[] | null>(null);
  const [niveau, setNiveau] = useState('tous');
  const [limit, setLimit] = useState(300);
  const [auto, setAuto] = useState(true);
  const [erreur, setErreur] = useState<string | null>(null);

  const charger = useCallback(async () => {
    try {
      setEntrees(await api.journaux(niveau === 'tous' ? undefined : niveau, limit));
      setErreur(null);
    } catch (exc) {
      setErreur(exc instanceof Error ? exc.message : 'Erreur inconnue');
    }
  }, [niveau, limit]);

  useEffect(() => {
    void charger();
    if (!auto) return;
    const interval = window.setInterval(() => void charger(), 5000);
    return () => window.clearInterval(interval);
  }, [charger, auto]);

  const classeNiveau = (n: string) => {
    switch (n.toLowerCase()) {
      case 'error':
      case 'critical':
        return 'bg-danger/15 text-danger border-danger/40';
      case 'warning':
        return 'bg-warn/15 text-warn border-warn/40';
      case 'debug':
        return 'bg-indigo-500/15 text-indigo-400 border-indigo-500/40';
      default:
        return 'bg-acc/15 text-acc border-acc/40';
    }
  };

  return (
    <Card
      titre="Journaux système (JSON structuré)"
      actions={
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-dim">
            <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} className="accent-acc" />
            Auto (5 s)
          </label>
          <button type="button" onClick={() => void charger()} className="btn-neutre !px-2 !py-1 text-xs">
            <RefreshCw size={13} /> Actualiser
          </button>
        </div>
      }
    >
      <div className="flex flex-wrap gap-3 mb-3">
        <label className="flex items-center gap-2 text-xs text-dim">
          Niveau
          <select className="champ !w-auto !py-1" value={niveau} onChange={(e) => setNiveau(e.target.value)}>
            {NIVEAUX.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs text-dim">
          Lignes
          <select className="champ !w-auto !py-1" value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
            {[100, 300, 1000].map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </label>
      </div>
      {erreur && <Erreur message={erreur} />}
      {!entrees && !erreur ? (
        <Chargement texte="Lecture des journaux…" />
      ) : entrees?.length === 0 ? (
        <p className="text-sm text-dim text-center py-6">Aucune entrée de journal pour ce niveau.</p>
      ) : (
        <div className="overflow-x-auto border border-edge rounded-md">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-dim uppercase tracking-wide bg-panel-soft">
                <th className="px-3 py-2 font-semibold whitespace-nowrap">Heure</th>
                <th className="px-3 py-2 font-semibold whitespace-nowrap">Niveau</th>
                <th className="px-3 py-2 font-semibold whitespace-nowrap">Module</th>
                <th className="px-3 py-2 font-semibold">Message</th>
                <th className="px-3 py-2 font-semibold">Contexte</th>
              </tr>
            </thead>
            <tbody>
              {entrees?.map((e, i) => (
                <tr key={i} className="border-t border-edge/60 hover:bg-panel-soft/60">
                  <td className="px-3 py-1.5 text-dim whitespace-nowrap">{heureFr(e.ts)}</td>
                  <td className="px-3 py-1.5">
                    <Badge classes={classeNiveau(e.level ?? 'info')}>{e.level ?? '—'}</Badge>
                  </td>
                  <td className="px-3 py-1.5 font-mono text-dim whitespace-nowrap max-w-[180px] truncate">{e.logger}</td>
                  <td className="px-3 py-1.5 text-ink max-w-[340px] break-words">{e.msg}</td>
                  <td className="px-3 py-1.5">
                    {e.ctx && Object.keys(e.ctx).length > 0 ? (
                      <code className="text-acc font-mono break-all">{JSON.stringify(e.ctx)}</code>
                    ) : (
                      <span className="text-dim">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export default function Systeme() {
  useTitrePage('Système');
  const [onglet, setOnglet] = useState<OngletId>('ressources');

  return (
    <>
      <PageHeader
        titre="Système"
        description="Santé de la plateforme : charge machine, accélération IA, synchronisation cloud, modules et journaux structurés."
      />
      <div className="flex flex-wrap gap-2 mb-4">
        {ONGLETS.map((o) => (
          <button
            key={o.id}
            type="button"
            onClick={() => setOnglet(o.id)}
            className={`btn !px-3 !py-1.5 text-xs ${onglet === o.id ? 'bg-acc/15 text-acc border border-acc/40' : 'bg-panel-soft text-dim border border-edge hover:text-ink'}`}
          >
            <o.icone size={14} /> {o.libelle}
          </button>
        ))}
      </div>
      {onglet === 'ressources' && <OngletRessources />}
      {onglet === 'cloud' && <OngletCloud />}
      {onglet === 'modules' && <OngletModules />}
      {onglet === 'journaux' && <OngletJournaux />}
    </>
  );
}
