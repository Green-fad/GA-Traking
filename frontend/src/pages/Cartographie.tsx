// Cartographie : plan du site plaçant les caméras selon position.x/y.
// Vert = flux actif, rouge = hors ligne (état d'exécution « runtime »).
import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import type { Camera } from '../api/types';
import { Card, Chargement, Erreur, PageHeader } from '../components/ui';
import { useTitrePage } from '../hooks/useTitrePage';

function Marqueur({ camera, surSurvol }: { camera: Camera; surSurvol: (c: Camera | null) => void }) {
  const actif = camera.runtime?.actif === true;
  return (
    <button
      type="button"
      onMouseEnter={() => surSurvol(camera)}
      onMouseLeave={() => surSurvol(null)}
      onFocus={() => surSurvol(camera)}
      onBlur={() => surSurvol(null)}
      className="absolute -translate-x-1/2 -translate-y-1/2 flex items-center justify-center"
      style={{ left: `${Math.min(Math.max(camera.position.x, 0.02), 0.98) * 100}%`, top: `${Math.min(Math.max(camera.position.y, 0.04), 0.96) * 100}%` }}
      aria-label={`Caméra ${camera.nom}`}
    >
      {actif && (
        <span
          className="absolute w-6 h-6 rounded-full bg-ok/30 animate-ping"
          style={{ animationDuration: '2.5s' }}
        />
      )}
      <span
        className={`relative w-4 h-4 rounded-full border-2 ${actif ? 'bg-ok border-ok/70 shadow-[0_0_8px_rgba(16,185,129,0.7)]' : 'bg-danger border-danger/70 shadow-[0_0_8px_rgba(239,68,68,0.6)]'}`}
      />
      <span className="absolute top-5 text-[10px] font-mono text-dim whitespace-nowrap bg-app/70 rounded px-1">
        {camera.id}
      </span>
    </button>
  );
}

export default function Cartographie() {
  useTitrePage('Cartographie');
  const [cameras, setCameras] = useState<Camera[] | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [survol, setSurvol] = useState<Camera | null>(null);

  const charger = useCallback(async () => {
    try {
      setCameras(await api.cameras());
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

  return (
    <>
      <PageHeader
        titre="Cartographie"
        description="Plan du site : chaque point représente une caméra positionnée (coordonnées x/y normalisées). Point vert = flux actif, point rouge = hors ligne."
        actions={
          <button type="button" onClick={() => void charger()} className="btn-neutre">
            <RefreshCw size={15} /> Actualiser
          </button>
        }
      />
      {erreur && <div className="mb-4"><Erreur message={erreur} /></div>}

      <Card>
        {!cameras ? (
          <Chargement texte="Chargement du plan…" />
        ) : cameras.length === 0 ? (
          <p className="text-sm text-dim text-center py-10">
            Aucune caméra à positionner — ajoutez des caméras et définissez leur position (x ; y).
          </p>
        ) : (
          <div
            className="relative w-full rounded-lg border border-edge overflow-hidden bg-app"
            style={{ aspectRatio: '5 / 3' }}
          >
            {/* fond : grille + zones de référence */}
            <svg className="absolute inset-0 w-full h-full" aria-hidden="true">
              <defs>
                <pattern id="grille" width="40" height="40" patternUnits="userSpaceOnUse">
                  <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e2a44" strokeWidth="1" />
                </pattern>
              </defs>
              <rect width="100%" height="100%" fill="url(#grille)" />
              <rect x="6%" y="10%" width="26%" height="30%" fill="#152238" stroke="#1e2a44" rx="6" />
              <text x="8%" y="16%" fill="#3d4c6b" fontSize="11" fontFamily="system-ui">Zone A — entrée</text>
              <rect x="60%" y="14%" width="32%" height="26%" fill="#152238" stroke="#1e2a44" rx="6" />
              <text x="62%" y="20%" fill="#3d4c6b" fontSize="11" fontFamily="system-ui">Zone B — parking</text>
              <rect x="34%" y="56%" width="38%" height="34%" fill="#152238" stroke="#1e2a44" rx="6" />
              <text x="36%" y="62%" fill="#3d4c6b" fontSize="11" fontFamily="system-ui">Zone C — voirie surveillée</text>
              <rect x="0%" y="48%" width="100%" height="4%" fill="#0e1626" />
              <line x1="0%" y1="50%" x2="100%" y2="50%" stroke="#2a3a5e" strokeWidth="1" strokeDasharray="8 8" />
            </svg>

            {/* marqueurs */}
            {cameras.map((c) => (
              <Marqueur key={c.id} camera={c} surSurvol={setSurvol} />
            ))}

            {/* légende */}
            <div className="absolute bottom-2 left-2 flex items-center gap-4 text-[11px] text-dim bg-panel/90 border border-edge rounded-md px-2.5 py-1.5">
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-ok inline-block" /> Flux actif
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-danger inline-block" /> Hors ligne
              </span>
            </div>

            {/* infobulle */}
            {survol && (
              <div
                className="absolute z-10 bg-panel border border-edge rounded-lg px-3 py-2 text-xs shadow-xl pointer-events-none max-w-[220px]"
                style={{
                  left: `${Math.min(Math.max(survol.position.x, 0.02), 0.7) * 100}%`,
                  top: `${Math.min(Math.max(survol.position.y - 0.09, 0.02), 0.85) * 100}%`,
                }}
              >
                <p className="font-semibold text-ink text-sm">{survol.nom}</p>
                <p className="font-mono text-dim">{survol.id}</p>
                <p className={survol.runtime?.actif ? 'text-ok mt-1' : 'text-danger mt-1'}>
                  {survol.runtime?.actif ? 'Flux actif' : 'Hors ligne'}
                </p>
                {survol.runtime && (
                  <p className="text-dim mt-0.5">
                    {survol.runtime.fps.toFixed(1)} img/s · {survol.runtime.pistes_actives} piste(s)
                  </p>
                )}
                <p className="text-dim mt-0.5 font-mono break-all">{survol.source}</p>
              </div>
            )}
          </div>
        )}
      </Card>
    </>
  );
}
