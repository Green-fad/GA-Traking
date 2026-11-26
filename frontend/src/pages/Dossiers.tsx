// Dossiers : liste par statut, visionneuse d'images de preuve (via /api/media +
// blob), décision Valider / Rejeter avec commentaire (opérateur+), contestation
// d'un dossier validé, identification du titulaire via les registres officiels.
// Conformité : aucune sanction automatique ; interrogation registre audité.
import { useCallback, useEffect, useState } from 'react';
import {
  BadgeCheck,
  Ban,
  CarFront,
  FileSearch,
  FolderSearch,
  ImageOff,
  MessageSquareWarning,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';
import { api, chargerMediaBlob } from '../api/client';
import type { Dossier, DossierDetail, IdentificationTitulaire } from '../api/types';
import { Badge, Card, Champ, Erreur, Modal, PageHeader, Spin } from '../components/ui';
import { classesStatutDossier, dateFr, libelleStatutDossier, libelleType } from '../utils/format';
import { useAuth } from '../state/AuthContext';
import { useToast } from '../state/ToastContext';
import { useTitrePage } from '../hooks/useTitrePage';

const STATUTS = ['a_verifier', 'valide', 'rejete', 'conteste', 'tous'] as const;

function ImagePreuve({ chemin, selectionnee, surClic }: { chemin: string; selectionnee: boolean; surClic: () => void }) {
  const [url, setUrl] = useState<string | null>(null);
  const [echec, setEchec] = useState(false);

  useEffect(() => {
    let vivant = true;
    let objet: string | null = null;
    chargerMediaBlob(chemin)
      .then((blob) => {
        if (!vivant) return;
        objet = URL.createObjectURL(blob);
        setUrl(objet);
      })
      .catch(() => {
        if (vivant) setEchec(true);
      });
    return () => {
      vivant = false;
      if (objet) URL.revokeObjectURL(objet);
    };
  }, [chemin]);

  if (echec) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center gap-1 text-dim bg-app rounded-md border border-edge">
        <ImageOff size={18} />
        <span className="text-[10px]">Preuve indisponible</span>
      </div>
    );
  }
  if (!url) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-app rounded-md border border-edge">
        <Spin taille={16} />
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={surClic}
      className={`w-full h-full rounded-md overflow-hidden border transition ${selectionnee ? 'border-acc ring-1 ring-acc' : 'border-edge hover:border-dim'}`}
    >
      <img src={url} alt={`Preuve ${chemin}`} className="w-full h-full object-cover" />
    </button>
  );
}

export default function Dossiers() {
  useTitrePage('Dossiers');
  const { peutOperation } = useAuth();
  const { notifier } = useToast();
  const [dossiers, setDossiers] = useState<Dossier[] | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [statut, setStatut] = useState<(typeof STATUTS)[number]>('a_verifier');
  const [detail, setDetail] = useState<DossierDetail | null>(null);
  const [commentaire, setCommentaire] = useState('');
  const [motifContestation, setMotifContestation] = useState('');
  const [enCours, setEnCours] = useState(false);
  const [imageActive, setImageActive] = useState<string | null>(null);
  const [identification, setIdentification] = useState<IdentificationTitulaire | null>(null);
  const [plaqueManuelle, setPlaqueManuelle] = useState('');
  const [identificationEnCours, setIdentificationEnCours] = useState(false);

  const charger = useCallback(
    async (statutCible?: string) => {
      try {
        const s = statutCible ?? statut;
        const liste = await api.dossiers(s === 'tous' ? undefined : s);
        setDossiers(liste);
        setErreur(null);
      } catch (exc) {
        setErreur(exc instanceof Error ? exc.message : 'Erreur inconnue');
      }
    },
    [statut],
  );

  useEffect(() => {
    void charger();
  }, [charger]);

  const ouvrirDetail = async (d: Dossier) => {
    try {
      const complet = await api.dossier(d.uuid);
      setDetail(complet);
      setCommentaire('');
      setMotifContestation('');
      setPlaqueManuelle('');
      setImageActive(complet.images[0] ?? null);
      setIdentification((complet.preuves['identification'] as IdentificationTitulaire | undefined) ?? null);
    } catch (exc) {
      notifier(exc instanceof Error ? exc.message : 'Dossier introuvable', 'erreur');
    }
  };

  const decider = async (decision: 'valide' | 'rejete') => {
    if (!detail) return;
    setEnCours(true);
    try {
      await api.deciderDossier(detail.uuid, decision, commentaire.trim() || undefined);
      notifier(`Dossier ${decision === 'valide' ? 'validé' : 'rejeté'} — décision enregistrée`, 'succes');
      setDetail(null);
      await charger();
    } catch (exc) {
      notifier(exc instanceof Error ? exc.message : 'Décision impossible', 'erreur');
    } finally {
      setEnCours(false);
    }
  };

  const contester = async () => {
    if (!detail) return;
    setEnCours(true);
    try {
      await api.contesterDossier(detail.uuid, motifContestation.trim());
      notifier('Dossier contesté — le motif est enregistré dans le registre d\u2019audit', 'avertissement');
      setDetail(null);
      await charger();
    } catch (exc) {
      notifier(exc instanceof Error ? exc.message : 'Contestation impossible', 'erreur');
    } finally {
      setEnCours(false);
    }
  };

  // Identification du titulaire via les registres officiels : finalité = instruction
  // de ce dossier ; interrogation limitée en débit et audité côté serveur.
  const identifier = async () => {
    if (!detail) return;
    setIdentificationEnCours(true);
    try {
      const plaque = plaqueManuelle.trim() || (detail.preuves['plaque'] as string | undefined);
      const resultat = await api.identifierDossier(detail.uuid, plaque || undefined);
      if (resultat.trouve) {
        setIdentification(resultat);
        notifier(`Titulaire identifié (source : ${resultat.source}) — interrogation audité`, 'succes');
        const complet = await api.dossier(detail.uuid);
        setDetail(complet);
      } else {
        notifier('Aucun titulaire trouvé pour cette plaque dans le registre', 'avertissement');
      }
    } catch (exc) {
      notifier(exc instanceof Error ? exc.message : 'Identification impossible', 'erreur');
    } finally {
      setIdentificationEnCours(false);
    }
  };

  const metriques = detail
    ? ((detail.preuves['metriques'] as Record<string, unknown> | undefined) ?? detail.metriques ?? {})
    : {};

  return (
    <>
      <PageHeader
        titre="Dossiers"
        description="Preuves d'infractions candidates soumises à validation humaine : vitesse, direction, intrusion."
      />

      <div className="mb-4 rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-4 py-3 text-sm text-indigo-200">
        <span className="font-semibold">Conformité —</span> le système ne prononce{' '}
        <span className="font-semibold">aucune sanction automatique</span> : chaque dossier est analysé puis décidé
        par un opérateur humain. Toute décision et contestation est journalisée dans le registre d'audit immuable.
      </div>

      <div className="flex flex-wrap gap-2 mb-4">
        {STATUTS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStatut(s)}
            className={`btn !px-3 !py-1.5 text-xs ${statut === s ? 'bg-acc/15 text-acc border border-acc/40' : 'bg-panel-soft text-dim border border-edge hover:text-ink'}`}
          >
            {s === 'tous' ? 'Tous' : libelleStatutDossier(s)}
          </button>
        ))}
        <button type="button" onClick={() => void charger()} className="btn-neutre !px-3 !py-1.5 text-xs ml-auto">
          <RefreshCw size={14} /> Actualiser
        </button>
      </div>

      {erreur && <div className="mb-4"><Erreur message={erreur} /></div>}

      <Card>
        {!dossiers ? (
          <p className="text-sm text-dim py-8 text-center">Chargement des dossiers…</p>
        ) : dossiers.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-10 text-center">
            <FolderSearch size={28} className="text-dim" />
            <p className="text-sm font-medium text-ink">Aucun dossier pour ce statut</p>
            <p className="text-xs text-dim">Les dossiers sont créés automatiquement par les modules de détection.</p>
          </div>
        ) : (
          <ul className="divide-y divide-edge/60">
            {dossiers.map((d) => (
              <li key={d.uuid}>
                <button
                  type="button"
                  onClick={() => void ouvrirDetail(d)}
                  className="w-full text-left px-2 py-3 hover:bg-panel-soft/60 rounded-md transition flex flex-wrap items-center gap-3"
                >
                  <Badge classes={classesStatutDossier(d.statut)}>{libelleStatutDossier(d.statut)}</Badge>
                  <span className="text-sm font-medium text-ink">{libelleType(d.type)}</span>
                  <span className="font-mono text-xs text-acc">{d.camera ?? '—'}</span>
                  {d.plaque && (
                    <span className="font-mono text-[11px] text-succ border border-succ/30 bg-succ/10 px-1.5 py-0.5 rounded">
                      {d.plaque}
                    </span>
                  )}
                  {d.identifie && (
                    <span className="inline-flex items-center gap-1 text-[11px] text-indigo-300">
                      <ShieldCheck size={13} /> identifié
                    </span>
                  )}
                  <span className="text-xs text-dim">{dateFr(d.ts)}</span>
                  <span className="text-xs text-dim ml-auto inline-flex items-center gap-1">
                    <FileSearch size={13} /> {d.images.length} preuve(s)
                  </span>
                  {d.decision_par && <span className="text-xs text-dim">décidé par {d.decision_par}</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Modal ouvert={detail !== null} fermer={() => setDetail(null)} titre={detail ? `Dossier ${detail.uuid.slice(0, 8)} — ${libelleType(detail.type)}` : ''} large>
        {detail && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge classes={classesStatutDossier(detail.statut)}>{libelleStatutDossier(detail.statut)}</Badge>
              <span className="text-dim text-xs">{dateFr(detail.ts)}</span>
              <span className="font-mono text-xs text-acc">{detail.camera ?? '—'}</span>
            </div>

            {/* preuves */}
            {detail.images.length === 0 ? (
              <p className="text-sm text-dim text-center py-6 border border-edge rounded-md bg-app">
                Aucune image de preuve associée à ce dossier.
              </p>
            ) : (
              <div>
                <p className="text-xs uppercase tracking-wide text-dim mb-2">Preuves ({detail.images.length})</p>
                <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 mb-2">
                  {detail.images.map((chemin) => (
                    <div key={chemin} className="aspect-video">
                      <ImagePreuve chemin={chemin} selectionnee={imageActive === chemin} surClic={() => setImageActive(chemin)} />
                    </div>
                  ))}
                </div>
                {imageActive && (
                  <div className="rounded-md border border-edge bg-app p-2">
                    <PreuveAgrandie chemin={imageActive} />
                  </div>
                )}
              </div>
            )}

            {/* métriques */}
            {Object.keys(metriques).length > 0 && (
              <div>
                <p className="text-xs uppercase tracking-wide text-dim mb-2">Métriques mesurées</p>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {Object.entries(metriques).map(([cle, valeur]) => (
                    <div key={cle} className="bg-panel-soft border border-edge rounded-md px-3 py-2">
                      <p className="text-[11px] text-dim truncate">{cle}</p>
                      <p className="text-sm font-semibold text-ink">{String(valeur)}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* identification du titulaire (registres officiels) */}
            <div>
              <p className="text-xs uppercase tracking-wide text-dim mb-2 inline-flex items-center gap-1">
                <CarFront size={13} /> Identification du véhicule
              </p>
              {Boolean(detail.preuves['plaque']) && (
                <p className="text-sm text-dim mb-2">
                  Plaque lue par l'ANPR :{' '}
                  <span className="font-mono text-succ font-semibold">{String(detail.preuves['plaque'])}</span>
                </p>
              )}
              {identification ? (
                <div className="rounded-md border border-indigo-500/30 bg-indigo-500/5 px-3 py-3 space-y-2">
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {[
                      ['Nom', identification.nom],
                      ['Prénom', identification.prenom],
                      ['N° CIN', identification.cin],
                      ['Véhicule', identification.vehicule],
                      ['Couleur', identification.couleur],
                    ]
                      .filter(([, v]) => Boolean(v))
                      .map(([cle, valeur]) => (
                        <div key={cle} className="bg-panel-soft border border-edge rounded-md px-3 py-2">
                          <p className="text-[11px] text-dim">{cle}</p>
                          <p className="text-sm font-semibold text-ink">{valeur}</p>
                        </div>
                      ))}
                  </div>
                  <p className="text-[11px] text-dim">
                    Source : {identification.source} — interrogé le {dateFr(identification.horodatage)}.
                    Interrogation <span className="text-ink">limitée en débit et audité</span> (finalité :
                    instruction de ce dossier). Le n° CIN est masqué hors rôle administrateur.
                  </p>
                </div>
              ) : peutOperation ? (
                <div className="flex flex-wrap items-end gap-2">
                  <div className="min-w-40">
                    <Champ libelle="Plaque (si l'ANPR n'a rien lu)">
                      <input
                        className="champ"
                        value={plaqueManuelle}
                        onChange={(e) => setPlaqueManuelle(e.target.value.toUpperCase())}
                        placeholder="AB-123-CD"
                        maxLength={20}
                      />
                    </Champ>
                  </div>
                  <button
                    type="button"
                    onClick={() => void identifier()}
                    className="btn-neutre border-indigo-500/40 text-indigo-300"
                    disabled={identificationEnCours || (!plaqueManuelle.trim() && !detail.preuves['plaque'])}
                  >
                    {identificationEnCours ? <Spin taille={14} /> : <ShieldCheck size={15} />}
                    Identifier via le registre
                  </button>
                </div>
              ) : (
                <p className="text-xs text-dim">
                  Identification réservée aux opérateurs et administrateurs (habilitation registres).
                </p>
              )}
            </div>

            {/* décisions existantes */}
            {(detail.commentaire || detail.motif_contestation || detail.decision_par) && (
              <div className="rounded-md border border-edge bg-app px-3 py-2 text-sm space-y-1">
                {detail.decision_par && (
                  <p className="text-dim">
                    Décision par <span className="text-ink">{detail.decision_par}</span>
                    {detail.decision_ts && ` — ${dateFr(detail.decision_ts)}`}
                  </p>
                )}
                {detail.commentaire && <p className="text-dim">Commentaire : <span className="text-ink">{detail.commentaire}</span></p>}
                {detail.motif_contestation && (
                  <p className="text-warn">Motif de contestation : {detail.motif_contestation}</p>
                )}
              </div>
            )}

            {/* actions selon statut et rôle */}
            {detail.statut === 'a_verifier' && (
              <>
                {peutOperation ? (
                  <div className="border-t border-edge pt-3 space-y-3">
                    <Champ libelle="Commentaire de décision (facultatif)">
                      <textarea
                        className="champ"
                        rows={2}
                        value={commentaire}
                        onChange={(e) => setCommentaire(e.target.value)}
                        placeholder="Justification de la décision…"
                      />
                    </Champ>
                    <div className="flex flex-wrap justify-end gap-2">
                      <button type="button" onClick={() => void decider('rejete')} className="btn-danger" disabled={enCours}>
                        <Ban size={15} /> Rejeter
                      </button>
                      <button type="button" onClick={() => void decider('valide')} className="btn-succes" disabled={enCours}>
                        <BadgeCheck size={15} /> Valider
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-dim border-t border-edge pt-3">
                    Votre rôle est en lecture seule : seuls un opérateur ou un administrateur peuvent décider.
                  </p>
                )}
              </>
            )}

            {detail.statut === 'valide' && (
              <div className="border-t border-edge pt-3 space-y-3">
                {peutOperation ? (
                  <>
                    <Champ libelle="Motif de contestation" aide="uniquement pour un dossier déjà validé (min. 3 caractères)">
                      <textarea
                        className="champ"
                        rows={2}
                        value={motifContestation}
                        onChange={(e) => setMotifContestation(e.target.value)}
                        placeholder="Ex. plaque mal lue, véhicule non concerné…"
                      />
                    </Champ>
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => void contester()}
                        className="btn-neutre border-warn/40 text-warn"
                        disabled={enCours || motifContestation.trim().length < 3}
                      >
                        <MessageSquareWarning size={15} /> Contester la décision
                      </button>
                    </div>
                  </>
                ) : (
                  <p className="text-xs text-dim">
                    Contestation réservée aux opérateurs et administrateurs.
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </Modal>
    </>
  );
}

function PreuveAgrandie({ chemin }: { chemin: string }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let vivant = true;
    let objet: string | null = null;
    chargerMediaBlob(chemin)
      .then((b) => {
        if (!vivant) return;
        objet = URL.createObjectURL(b);
        setUrl(objet);
      })
      .catch(() => setUrl(null));
    return () => {
      vivant = false;
      if (objet) URL.revokeObjectURL(objet);
    };
  }, [chemin]);
  if (!url) return <Spin taille={16} />;
  return <img src={url} alt={`Preuve agrandie ${chemin}`} className="max-h-72 w-auto mx-auto rounded" />;
}
