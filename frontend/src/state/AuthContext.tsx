// Contexte d'authentification : login/logout/me, rôle courant, gardes de routes.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { api, effacerJeton, EVENEMENT_DECONNEXION, obtenirJeton, definirJeton } from '../api/client';
import type { Role, Utilisateur } from '../api/types';
import { rangRole } from '../utils/format';

interface AuthContexte {
  utilisateur: Utilisateur | null;
  chargement: boolean;
  connecter: (username: string, password: string) => Promise<void>;
  deconnecter: () => void;
  roleMinimum: (min: Role) => boolean;
  estAdmin: boolean;
  peutOperation: boolean;
}

const Contexte = createContext<AuthContexte | null>(null);

export function FournisseurAuth({ children }: { children: ReactNode }) {
  const [utilisateur, setUtilisateur] = useState<Utilisateur | null>(null);
  const [chargement, setChargement] = useState<boolean>(() => obtenirJeton() !== null);

  const deconnecter = useCallback(() => {
    effacerJeton();
    setUtilisateur(null);
  }, []);

  useEffect(() => {
    const jeton = obtenirJeton();
    if (!jeton) {
      setChargement(false);
      return;
    }
    api
      .moi()
      .then((u) => setUtilisateur(u))
      .catch(() => {
        effacerJeton();
        setUtilisateur(null);
      })
      .finally(() => setChargement(false));
  }, []);

  useEffect(() => {
    const surDeconnexion = () => setUtilisateur(null);
    window.addEventListener(EVENEMENT_DECONNEXION, surDeconnexion);
    return () => window.removeEventListener(EVENEMENT_DECONNEXION, surDeconnexion);
  }, []);

  const connecter = useCallback(async (username: string, password: string) => {
    const reponse = await api.connexion(username, password);
    definirJeton(reponse.token);
    setUtilisateur(reponse.utilisateur);
  }, []);

  const valeur = useMemo<AuthContexte>(() => {
    const rang = utilisateur ? rangRole(utilisateur.role) : 0;
    return {
      utilisateur,
      chargement,
      connecter,
      deconnecter,
      roleMinimum: (min: Role) => rang >= rangRole(min),
      estAdmin: utilisateur?.role === 'admin',
      peutOperation: rang >= rangRole('operateur'),
    };
  }, [utilisateur, chargement, connecter, deconnecter]);

  return <Contexte.Provider value={valeur}>{children}</Contexte.Provider>;
}

export function useAuth(): AuthContexte {
  const ctx = useContext(Contexte);
  if (!ctx) throw new Error('useAuth doit être utilisé dans FournisseurAuth');
  return ctx;
}
