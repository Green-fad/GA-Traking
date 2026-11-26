// Mur vidéo : grille responsive des caméras actives, images rafraîchies toutes
// les 2 s via fetch snapshot → blob → objectURL (Authorization Bearer). Clic sur
// une tuile = plein écran.
import { useCallback, useEffect, useRef, useState } from 'react';
import { CameraOff, Maximize2, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import type { Camera } from '../api/types';
import { Badge, Card, Chargement, Erreur, PageHeader, Modal } from '../components/ui';
import { useTitrePage } from '../hooks/useTitrePage';

const PERIODE_MS = 2000;

function Tuile({ camera, grand = false }: { camera: Camera; grand?: boolean }) {
  const [url, setUrl] = useState<string | null>(null);
  const [indisponible, setIndisponible] = useState(false);
  const [dernierRafraichissement, setDernierRafraichissement] = useState<number | null>(null);
  const urlRef = useRef<string | null>(null);
  const occupeRef = useRef(false);

  useEffect(() => {
    let vivant = true;

    const rafraichir = async () => {
      if (occupeRef.current) return;
      occupeRef.current = true;
      try {
        const blob = await api.instantaneCamera(camera.id);
        if (!vivant) return;
        const nouvelle = URL.createObjectURL(blob);
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        urlRef.current = nouvelle;
        setUrl(nouvelle);
        setIndisponible(false);
        setDernierRafraichissement(Date.now());
      } catch {
        if (vivant) setIndisponible(true);
      } finally {
        occupeRef.current = false;
      }
    };

    void rafraichir();
    const interval = window.setInterval(() => void rafraichir(), PERIODE_MS);
    return () => {
      vivant = false;
      window.clearInterval(interval);
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    };
  }, [camera.id]);

  return (
    <div className="relative w-full h-full bg-black rounded-lg overflow-hidden border border-edge group">
      {url ? (
        <img src={url} alt={`Flux de la caméra ${camera.nom}`} className="w-full h-full object-cover" />
      ) : (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-dim">
          <CameraOff size={grand ? 36 : 22} />
          <span className={`text-center px-3 ${grand ? 'text-sm' : 'text-xs'}`}>
            {indisponible ? 'Flux indisponible' : 'Chargement du flux…'}
          </span>
        </div>
      )}
      {indisponible && url && (
        <span className="absolute top-2 left-2 badge bg-danger/20 text-danger border-danger/50 backdrop-blur">
          Flux indisponible
        </span>
      )}
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-3 py-2 flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className={`font-semibold truncate ${grand ? 'text-sm' : 'text-xs'}`}>{camera.nom}</p>
          <p className="text-[10px] text-dim font-mono truncate">{camera.id}</p>
        </div>
        <span className="text-[10px] text-dim whitespace-nowrap">
          {dernierRafraichissement ? new Date(dernierRafraichissement).toLocaleTimeString('fr-FR') : '—'}
        </span>
      </div>
    </div>
  );
}

export default function MurVideo() {
  useTitrePage('Mur vidéo');
  const [cameras, setCameras] = useState<Camera[] | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [pleinEcran, setPleinEcran] = useState<Camera | null>(null);
  const [seulementActives, setSeulementActives] = useState(true);

  const charger = useCallback(async () => {
    try {
      const liste = await api.cameras();
      setCameras(liste);
      setErreur(null);
    } catch (exc) {
      setErreur(exc instanceof Error ? exc.message : 'Erreur inconnue');
    }
  }, []);

  useEffect(() => {
    void charger();
  }, [charger]);

  if (!cameras) {
    return (
      <>
        <PageHeader titre="Mur vidéo" description="Surveillance visuelle des flux caméras en direct." />
        <Erreur message={erreur ?? ''} />
        <Chargement texte="Chargement des caméras…" />
      </>
    );
  }

  const affichees = seulementActives ? cameras.filter((c) => c.active) : cameras;

  return (
    <>
      <PageHeader
        titre="Mur vidéo"
        description="Instantanés rafraîchis toutes les 2 secondes (cadence d'échantillonnage GA-SECURITY). Cliquez sur une tuile pour l'agrandir."
        actions={
          <>
            <button
              type="button"
              onClick={() => setSeulementActives((v) => !v)}
              className="btn-neutre"
            >
              {seulementActives ? 'Afficher toutes les caméras' : 'Caméras actives uniquement'}
            </button>
            <button type="button" onClick={() => void charger()} className="btn-neutre">
              <RefreshCw size={15} /> Actualiser
            </button>
          </>
        }
      />
      {erreur && <div className="mb-4"><Erreur message={erreur} /></div>}

      {affichees.length === 0 ? (
        <Card>
          <p className="text-sm text-dim text-center py-8">
            Aucune caméra active — configurez des caméras dans le menu « Caméras ».
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
          {affichees.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setPleinEcran(c)}
              className="relative aspect-video text-left group/tuile"
              aria-label={`Agrandir le flux de ${c.nom}`}
            >
              <Tuile camera={c} />
              <span className="absolute top-2 right-2 opacity-0 group-hover/tuile:opacity-100 transition bg-black/60 rounded p-1.5 text-acc pointer-events-none">
                <Maximize2 size={14} />
              </span>
            </button>
          ))}
        </div>
      )}

      <Modal ouvert={pleinEcran !== null} fermer={() => setPleinEcran(null)} titre={pleinEcran ? `Flux — ${pleinEcran.nom}` : ''} large>
        {pleinEcran && (
          <div className="space-y-3">
            <div className="aspect-video">
              <Tuile camera={pleinEcran} grand />
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs text-dim">
              <Badge classes="bg-panel-soft text-dim border-edge">{pleinEcran.id}</Badge>
              <span className="font-mono break-all">{pleinEcran.source}</span>
              {pleinEcran.runtime && (
                <>
                  <span>· {pleinEcran.runtime.fps.toFixed(1)} img/s</span>
                  <span>· {pleinEcran.runtime.pistes_actives} piste(s) active(s)</span>
                </>
              )}
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}
