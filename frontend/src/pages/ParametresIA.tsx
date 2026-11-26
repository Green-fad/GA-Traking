// Paramètres IA : seuils de détection (confiance, IoU, limite de vitesse,
// images d'intrusion). Écriture réservée à l'admin — valeurs appliquées au
// prochain démarrage du pipeline.
import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { BrainCircuit, Save } from 'lucide-react';
import { api, ApiError } from '../api/client';
import type { ParametresIA } from '../api/types';
import { Card, Champ, Erreur, PageHeader, Chargement } from '../components/ui';
import { useAuth } from '../state/AuthContext';
import { useToast } from '../state/ToastContext';
import { useTitrePage } from '../hooks/useTitrePage';

export default function ParametresIA() {
  useTitrePage('Paramètres IA');
  const { estAdmin } = useAuth();
  const { notifier } = useToast();
  const [parametres, setParametres] = useState<ParametresIA | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);

  const charger = useCallback(async () => {
    try {
      setParametres(await api.parametresIA());
      setErreur(null);
    } catch (exc) {
      setErreur(exc instanceof Error ? exc.message : 'Erreur inconnue');
    }
  }, []);

  useEffect(() => {
    void charger();
  }, [charger]);

  const maj = (cle: keyof ParametresIA) => (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!parametres) return;
    setParametres({ ...parametres, [cle]: Number(e.target.value) });
  };

  const enregistrer = async (e: FormEvent) => {
    e.preventDefault();
    if (!parametres) return;
    setEnCours(true);
    try {
      const reponse = await api.enregistrerParametresIA({
        conf_threshold: parametres.conf_threshold,
        iou_threshold: parametres.iou_threshold,
        speed_limit_kmh: parametres.speed_limit_kmh,
        intrusion_min_frames: parametres.intrusion_min_frames,
      });
      notifier(reponse.note ?? 'Paramètres enregistrés', 'avertissement');
      await charger();
    } catch (exc) {
      notifier(exc instanceof ApiError ? exc.message : 'Enregistrement impossible', 'erreur');
    } finally {
      setEnCours(false);
    }
  };

  if (!parametres) {
    return (
      <>
        <PageHeader titre="Paramètres IA" description="Seuils des modèles de détection et des règles métier." />
        {erreur ? <Erreur message={erreur} /> : <Chargement texte="Chargement des paramètres…" />}
      </>
    );
  }

  return (
    <>
      <PageHeader
        titre="Paramètres IA"
        description="Réglages du pipeline d'analyse : seuils du détecteur, règles de vitesse et d'intrusion."
      />

      <div className="mb-4 rounded-lg border border-warn/30 bg-warn/10 px-4 py-3 text-sm text-warn">
        <span className="font-semibold">Note —</span> les valeurs enregistrées sont{' '}
        <span className="font-semibold">appliquées au prochain démarrage du pipeline</span> (configuration persistée
        dans la base).
      </div>

      {erreur && <div className="mb-4"><Erreur message={erreur} /></div>}

      <form onSubmit={enregistrer}>
        <Card titre="Détection et règles">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Champ libelle="Seuil de confiance" aide="entre 0.05 et 0.95 — plus bas = plus de détections (et plus de faux positifs)">
              <input
                type="number"
                className="champ"
                min={0.05}
                max={0.95}
                step={0.01}
                value={parametres.conf_threshold}
                onChange={maj('conf_threshold')}
                disabled={!estAdmin}
                required
              />
            </Champ>
            <Champ libelle="Seuil IoU" aide="0.05 à 0.95 — fusion des boîtes englobantes chevauchantes (suppression non-maximale)">
              <input
                type="number"
                className="champ"
                min={0.05}
                max={0.95}
                step={0.01}
                value={parametres.iou_threshold}
                onChange={maj('iou_threshold')}
                disabled={!estAdmin}
                required
              />
            </Champ>
            <Champ libelle="Limite de vitesse (km/h)" aide="seuil de déclenchement des dossiers d'excès de vitesse">
              <input
                type="number"
                className="champ"
                min={1}
                step={1}
                value={parametres.speed_limit_kmh}
                onChange={maj('speed_limit_kmh')}
                disabled={!estAdmin}
                required
              />
            </Champ>
            <Champ libelle="Images d'intrusion minimum" aide="nombre d'images consécutives confirmant une intrusion">
              <input
                type="number"
                className="champ"
                min={1}
                step={1}
                value={parametres.intrusion_min_frames}
                onChange={maj('intrusion_min_frames')}
                disabled={!estAdmin}
                required
              />
            </Champ>
          </div>

          <div className="mt-4 pt-4 border-t border-edge grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            <div className="flex items-center gap-2 text-dim">
              <BrainCircuit size={16} className="text-acc shrink-0" />
              <span>
                Modèle : <span className="text-ink font-medium">{String(parametres.detector ?? '—')}</span>
              </span>
            </div>
            <div className="text-dim truncate">
              Chemin : <span className="text-ink font-mono text-xs">{String(parametres.model_path ?? '—')}</span>
            </div>
          </div>

          <div className="mt-4 flex items-center justify-between gap-3 border-t border-edge pt-4">
            {!estAdmin && (
              <p className="text-xs text-dim">
                Lecture seule : seuls les administrateurs peuvent modifier ces seuils.
              </p>
            )}
            {estAdmin && (
              <button type="submit" className="btn-primaire ml-auto" disabled={enCours}>
                <Save size={15} /> Enregistrer
              </button>
            )}
          </div>
        </Card>
      </form>
    </>
  );
}
