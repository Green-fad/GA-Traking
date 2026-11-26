// Utilisateurs : CRUD réservé au rôle admin — badges de rôle, activation /
// désactivation, réinitialisation de mot de passe.
import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Pencil, Plus, RefreshCw, Trash2, UserPlus } from 'lucide-react';
import { api, ApiError } from '../api/client';
import type { Role, UtilisateurItem } from '../api/types';
import { Badge, Card, Champ, ConfirmButton, DataTable, Erreur, Modal, PageHeader } from '../components/ui';
import type { Colonne } from '../components/ui';
import { useAuth } from '../state/AuthContext';
import { useToast } from '../state/ToastContext';
import { classesRole, dateFr, libelleRole } from '../utils/format';
import { useTitrePage } from '../hooks/useTitrePage';

const ROLES: Role[] = ['admin', 'operateur', 'observateur'];

interface FormeCreation {
  username: string;
  password: string;
  role: Role;
}

interface FormeEdition {
  role: Role;
  actif: boolean;
  motDePasse: string;
}

export default function Utilisateurs() {
  useTitrePage('Utilisateurs');
  const { utilisateur } = useAuth();
  const { notifier } = useToast();
  const [utilisateurs, setUtilisateurs] = useState<UtilisateurItem[] | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [creationOuverte, setCreationOuverte] = useState(false);
  const [edition, setEdition] = useState<UtilisateurItem | null>(null);
  const [formeCreation, setFormeCreation] = useState<FormeCreation>({ username: '', password: '', role: 'observateur' });
  const [formeEdition, setFormeEdition] = useState<FormeEdition>({ role: 'observateur', actif: true, motDePasse: '' });
  const [enCours, setEnCours] = useState(false);

  const charger = useCallback(async () => {
    try {
      setUtilisateurs(await api.utilisateurs());
      setErreur(null);
    } catch (exc) {
      setErreur(exc instanceof Error ? exc.message : 'Erreur inconnue');
    }
  }, []);

  useEffect(() => {
    void charger();
  }, [charger]);

  const creer = async (e: FormEvent) => {
    e.preventDefault();
    setEnCours(true);
    try {
      await api.creerUtilisateur(formeCreation.username.trim(), formeCreation.password, formeCreation.role);
      notifier(`Utilisateur « ${formeCreation.username} » créé`, 'succes');
      setCreationOuverte(false);
      setFormeCreation({ username: '', password: '', role: 'observateur' });
      await charger();
    } catch (exc) {
      notifier(exc instanceof ApiError ? exc.message : 'Création impossible', 'erreur');
    } finally {
      setEnCours(false);
    }
  };

  const enregistrerEdition = async (e: FormEvent) => {
    e.preventDefault();
    if (!edition) return;
    setEnCours(true);
    try {
      await api.modifierUtilisateur(edition.id, {
        role: formeEdition.role,
        active: formeEdition.actif,
        password: formeEdition.motDePasse.length >= 8 ? formeEdition.motDePasse : undefined,
      });
      notifier(`Utilisateur « ${edition.username} » modifié`, 'succes');
      setEdition(null);
      await charger();
    } catch (exc) {
      notifier(exc instanceof ApiError ? exc.message : 'Modification impossible', 'erreur');
    } finally {
      setEnCours(false);
    }
  };

  const supprimer = async (u: UtilisateurItem) => {
    try {
      await api.supprimerUtilisateur(u.id);
      notifier(`Utilisateur « ${u.username} » supprimé`, 'succes');
      await charger();
    } catch (exc) {
      notifier(exc instanceof ApiError ? exc.message : 'Suppression impossible', 'erreur');
    }
  };

  const basculerActif = async (u: UtilisateurItem) => {
    try {
      await api.modifierUtilisateur(u.id, { active: !u.actif });
      notifier(`Compte « ${u.username} » ${u.actif ? 'désactivé' : 'activé'}`, 'succes');
      await charger();
    } catch (exc) {
      notifier(exc instanceof ApiError ? exc.message : 'Action impossible', 'erreur');
    }
  };

  const colonnes: Colonne<UtilisateurItem>[] = [
    {
      cle: 'username',
      libelle: 'Identifiant',
      rendu: (u) => (
        <span className="font-medium">
          {u.username}
          {u.username === utilisateur?.username && <span className="ml-2 text-[11px] text-dim">(vous)</span>}
        </span>
      ),
    },
    {
      cle: 'role',
      libelle: 'Rôle',
      rendu: (u) => <Badge classes={classesRole(u.role)}>{libelleRole(u.role)}</Badge>,
    },
    {
      cle: 'actif',
      libelle: 'Compte',
      rendu: (u) => (
        <Badge classes={u.actif ? 'bg-ok/15 text-ok border-ok/40' : 'bg-danger/15 text-danger border-danger/40'}>
          {u.actif ? 'Actif' : 'Désactivé'}
        </Badge>
      ),
    },
    {
      cle: 'derniere_connexion',
      libelle: 'Dernière connexion',
      rendu: (u) => <span className="text-xs text-dim">{dateFr(u.derniere_connexion)}</span>,
    },
    {
      cle: 'actions',
      libelle: 'Actions',
      rendu: (u) => (
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => {
              setEdition(u);
              setFormeEdition({ role: u.role, actif: u.actif, motDePasse: '' });
            }}
            className="p-1.5 rounded-md text-dim hover:text-acc hover:bg-acc/10"
            aria-label={`Modifier ${u.username}`}
          >
            <Pencil size={15} />
          </button>
          <button
            type="button"
            onClick={() => void basculerActif(u)}
            className="btn-neutre !px-2 !py-1 text-xs"
            disabled={u.username === utilisateur?.username && u.actif}
            title={u.username === utilisateur?.username ? 'Impossible de désactiver son propre compte' : undefined}
          >
            {u.actif ? 'Désactiver' : 'Activer'}
          </button>
          <ConfirmButton
            libelle={<Trash2 size={15} />}
            libelleConfirmation="Confirmer"
            onConfirmer={() => void supprimer(u)}
            className="p-1.5 rounded-md text-dim hover:text-danger hover:bg-danger/10"
          />
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        titre="Utilisateurs"
        description="Comptes et rôles de la console. Trois niveaux : administrateur (tout), opérateur (alertes, dossiers, caméras), observateur (lecture seule)."
        actions={
          <>
            <button type="button" onClick={() => setCreationOuverte(true)} className="btn-primaire">
              <UserPlus size={15} /> Nouvel utilisateur
            </button>
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
          lignes={utilisateurs}
          cle={(u) => String(u.id)}
          vide={<p className="text-sm text-dim text-center py-8">Aucun utilisateur.</p>}
        />
      </Card>

      {/* création */}
      <Modal ouvert={creationOuverte} fermer={() => setCreationOuverte(false)} titre="Nouvel utilisateur">
        <form onSubmit={creer} className="space-y-4">
          <Champ libelle="Identifiant" aide="3 caractères minimum">
            <input
              className="champ"
              value={formeCreation.username}
              onChange={(e) => setFormeCreation({ ...formeCreation, username: e.target.value })}
              minLength={3}
              maxLength={64}
              required
            />
          </Champ>
          <Champ libelle="Mot de passe" aide="8 caractères minimum">
            <input
              type="password"
              className="champ"
              value={formeCreation.password}
              onChange={(e) => setFormeCreation({ ...formeCreation, password: e.target.value })}
              minLength={8}
              required
            />
          </Champ>
          <Champ libelle="Rôle">
            <select
              className="champ"
              value={formeCreation.role}
              onChange={(e) => setFormeCreation({ ...formeCreation, role: e.target.value as Role })}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {libelleRole(r)}
                </option>
              ))}
            </select>
          </Champ>
          <div className="flex justify-end gap-2 pt-2 border-t border-edge">
            <button type="button" onClick={() => setCreationOuverte(false)} className="btn-neutre">
              Annuler
            </button>
            <button type="submit" className="btn-primaire" disabled={enCours}>
              <Plus size={15} /> Créer
            </button>
          </div>
        </form>
      </Modal>

      {/* édition */}
      <Modal ouvert={edition !== null} fermer={() => setEdition(null)} titre={edition ? `Modifier « ${edition.username} »` : ''}>
        <form onSubmit={enregistrerEdition} className="space-y-4">
          <Champ libelle="Rôle">
            <select
              className="champ"
              value={formeEdition.role}
              onChange={(e) => setFormeEdition({ ...formeEdition, role: e.target.value as Role })}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {libelleRole(r)}
                </option>
              ))}
            </select>
          </Champ>
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              checked={formeEdition.actif}
              onChange={(e) => setFormeEdition({ ...formeEdition, actif: e.target.checked })}
              className="accent-acc"
            />
            Compte actif
          </label>
          <Champ libelle="Nouveau mot de passe" aide="laisser vide pour conserver le mot de passe actuel (8 caractères min. si renseigné)">
            <input
              type="password"
              className="champ"
              value={formeEdition.motDePasse}
              onChange={(e) => setFormeEdition({ ...formeEdition, motDePasse: e.target.value })}
              minLength={8}
            />
          </Champ>
          <div className="flex justify-end gap-2 pt-2 border-t border-edge">
            <button type="button" onClick={() => setEdition(null)} className="btn-neutre">
              Annuler
            </button>
            <button type="submit" className="btn-primaire" disabled={enCours}>
              Enregistrer
            </button>
          </div>
        </form>
      </Modal>
    </>
  );
}
