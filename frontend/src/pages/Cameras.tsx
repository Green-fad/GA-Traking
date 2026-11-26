// Caméras : tableau du parc + formulaire création/édition + suppression
// (actions réservées opérateur et admin).
import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { api, ApiError } from '../api/client';
import type { Camera, CameraUpsert } from '../api/types';
import { Badge, Card, Champ, ConfirmButton, DataTable, Erreur, Modal, PageHeader } from '../components/ui';
import type { Colonne } from '../components/ui';
import { useAuth } from '../state/AuthContext';
import { useToast } from '../state/ToastContext';
import { dateFr } from '../utils/format';
import { useTitrePage } from '../hooks/useTitrePage';

const FORME_VIDE: CameraUpsert = {
  id: '',
  name: '',
  source: '',
  enabled: true,
  fps_limit: 15,
  location: { x: 0.5, y: 0.5 },
};

export default function Cameras() {
  useTitrePage('Caméras');
  const { peutOperation } = useAuth();
  const { notifier } = useToast();
  const [cameras, setCameras] = useState<Camera[] | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [modaleOuverte, setModaleOuverte] = useState(false);
  const [editionId, setEditionId] = useState<string | null>(null);
  const [forme, setForme] = useState<CameraUpsert>(FORME_VIDE);
  const [enregistre, setEnregistre] = useState(false);

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
  }, [charger]);

  const ouvrirCreation = () => {
    setEditionId(null);
    setForme(FORME_VIDE);
    setModaleOuverte(true);
  };

  const ouvrirEdition = (c: Camera) => {
    setEditionId(c.id);
    setForme({
      id: c.id,
      name: c.nom,
      source: c.source,
      enabled: c.active,
      fps_limit: c.fps_limite,
      location: { x: c.position.x, y: c.position.y },
    });
    setModaleOuverte(true);
  };

  const soumettre = async (e: FormEvent) => {
    e.preventDefault();
    setEnregistre(true);
    try {
      if (editionId) {
        await api.modifierCamera(editionId, forme);
        notifier(`Caméra « ${forme.name} » modifiée`, 'succes');
      } else {
        const reponse = await api.ajouterCamera(forme);
        notifier(reponse.note ?? `Caméra « ${forme.name} » ajoutée`, 'avertissement');
      }
      setModaleOuverte(false);
      await charger();
    } catch (exc) {
      notifier(exc instanceof ApiError ? exc.message : 'Enregistrement impossible', 'erreur');
    } finally {
      setEnregistre(false);
    }
  };

  const supprimer = async (c: Camera) => {
    try {
      await api.supprimerCamera(c.id);
      notifier(`Caméra « ${c.id} » supprimée`, 'succes');
      await charger();
    } catch (exc) {
      notifier(exc instanceof ApiError ? exc.message : 'Suppression impossible', 'erreur');
    }
  };

  const colonnes: Colonne<Camera>[] = [
    {
      cle: 'id',
      libelle: 'Identifiant',
      rendu: (c) => <span className="font-mono text-xs text-acc">{c.id}</span>,
    },
    { cle: 'nom', libelle: 'Nom', rendu: (c) => <span className="font-medium">{c.nom}</span> },
    {
      cle: 'source',
      libelle: 'Source',
      rendu: (c) => <span className="font-mono text-xs text-dim break-all max-w-[260px] block">{c.source}</span>,
    },
    {
      cle: 'active',
      libelle: 'Config',
      rendu: (c) => (
        <Badge classes={c.active ? 'bg-ok/15 text-ok border-ok/40' : 'bg-panel-soft text-dim border-edge'}>
          {c.active ? 'Active' : 'Désactivée'}
        </Badge>
      ),
    },
    {
      cle: 'runtime',
      libelle: 'Flux',
      rendu: (c) =>
        c.runtime ? (
          <Badge classes={c.runtime.actif ? 'bg-ok/15 text-ok border-ok/40' : 'bg-danger/15 text-danger border-danger/40'}>
            {c.runtime.actif ? `En ligne · ${c.runtime.fps.toFixed(1)} img/s` : 'Hors ligne'}
          </Badge>
        ) : (
          <span className="text-dim text-xs">Non démarré</span>
        ),
    },
    {
      cle: 'pistes',
      libelle: 'Pistes',
      rendu: (c) => <span className="text-dim">{c.runtime ? c.runtime.pistes_actives : '—'}</span>,
    },
    {
      cle: 'position',
      libelle: 'Position',
      rendu: (c) => (
        <span className="font-mono text-xs text-dim">
          ({c.position.x.toFixed(2)} ; {c.position.y.toFixed(2)})
        </span>
      ),
    },
    { cle: 'derniere_vue', libelle: 'Dernière vue', rendu: (c) => <span className="text-dim text-xs">{dateFr(c.derniere_vue)}</span> },
    {
      cle: 'actions',
      libelle: 'Actions',
      rendu: (c) =>
        peutOperation ? (
          <div className="flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              onClick={() => ouvrirEdition(c)}
              className="p-1.5 rounded-md text-dim hover:text-acc hover:bg-acc/10"
              aria-label={`Modifier ${c.nom}`}
            >
              <Pencil size={15} />
            </button>
            <ConfirmButton
              libelle={<Trash2 size={15} />}
              libelleConfirmation="Confirmer"
              onConfirmer={() => void supprimer(c)}
              className="p-1.5 rounded-md text-dim hover:text-danger hover:bg-danger/10"
            />
          </div>
        ) : (
          <span className="text-xs text-dim">Lecture seule</span>
        ),
    },
  ];

  return (
    <>
      <PageHeader
        titre="Caméras"
        description="Parc de caméras : configuration des flux, position sur le plan et état d'exécution. Les modifications de flux s'appliquent au redémarrage du service."
        actions={
          <>
            {peutOperation && (
              <button type="button" onClick={ouvrirCreation} className="btn-primaire">
                <Plus size={15} /> Nouvelle caméra
              </button>
            )}
            <button type="button" onClick={() => void charger()} className="btn-neutre">
              <RefreshCw size={15} /> Actualiser
            </button>
          </>
        }
      />
      {erreur && <div className="mb-4"><Erreur message={erreur} /></div>}

      <Card>
        <DataTable
          colonnes={colonnes}
          lignes={cameras}
          cle={(c) => c.id}
          vide={<p className="text-sm text-dim text-center py-8">Aucune caméra configurée.</p>}
        />
      </Card>

      <Modal
        ouvert={modaleOuverte}
        fermer={() => setModaleOuverte(false)}
        titre={editionId ? `Modifier la caméra ${editionId}` : 'Nouvelle caméra'}
      >
        <form onSubmit={soumettre} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Champ libelle="Identifiant" aide="lettres, chiffres, - et _ uniquement">
              <input
                className="champ font-mono"
                value={forme.id}
                onChange={(e) => setForme({ ...forme, id: e.target.value })}
                pattern="[A-Za-z0-9_-]{2,64}"
                required
                disabled={editionId !== null}
              />
            </Champ>
            <Champ libelle="Nom">
              <input
                className="champ"
                value={forme.name}
                onChange={(e) => setForme({ ...forme, name: e.target.value })}
                required
              />
            </Champ>
          </div>
          <Champ libelle="Source du flux" aide="ex. rtsp://192.168.1.10:554/flux ou 0 pour une caméra locale">
            <input
              className="champ font-mono"
              value={forme.source}
              onChange={(e) => setForme({ ...forme, source: e.target.value })}
              required
            />
          </Champ>
          <div className="grid grid-cols-3 gap-3">
            <Champ libelle="FPS limite">
              <input
                type="number"
                min={1}
                max={60}
                step={0.5}
                className="champ"
                value={forme.fps_limit}
                onChange={(e) => setForme({ ...forme, fps_limit: Number(e.target.value) })}
                required
              />
            </Champ>
            <Champ libelle="Position X" aide="0 à 1">
              <input
                type="number"
                min={0}
                max={1}
                step={0.01}
                className="champ"
                value={forme.location.x}
                onChange={(e) => setForme({ ...forme, location: { ...forme.location, x: Number(e.target.value) } })}
                required
              />
            </Champ>
            <Champ libelle="Position Y" aide="0 à 1">
              <input
                type="number"
                min={0}
                max={1}
                step={0.01}
                className="champ"
                value={forme.location.y}
                onChange={(e) => setForme({ ...forme, location: { ...forme.location, y: Number(e.target.value) } })}
                required
              />
            </Champ>
          </div>
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              checked={forme.enabled}
              onChange={(e) => setForme({ ...forme, enabled: e.target.checked })}
              className="accent-acc"
            />
            Caméra activée (analyse démarrée au prochain lancement du pipeline)
          </label>
          <div className="flex justify-end gap-2 pt-2 border-t border-edge">
            <button type="button" onClick={() => setModaleOuverte(false)} className="btn-neutre">
              Annuler
            </button>
            <button type="submit" className="btn-primaire" disabled={enregistre}>
              {editionId ? 'Enregistrer' : 'Créer la caméra'}
            </button>
          </div>
        </form>
      </Modal>
    </>
  );
}
