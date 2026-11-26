// Page de connexion : authentification + note premier démarrage.
import { useState } from 'react';
import type { FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { KeyRound, ShieldCheck, User } from 'lucide-react';
import { ApiError } from '../api/client';
import { useAuth } from '../state/AuthContext';
import { Champ, Erreur, Spin } from '../components/ui';
import { useTitrePage } from '../hooks/useTitrePage';

export default function Connexion() {
  useTitrePage('Connexion');
  const { connecter, utilisateur } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);

  if (utilisateur) {
    // déjà connecté : retour au tableau de bord
    return <Navigate to="/tableau-de-bord" replace />;
  }

  const soumettre = async (e: FormEvent) => {
    e.preventDefault();
    setErreur(null);
    setEnCours(true);
    try {
      await connecter(username.trim(), password);
      navigate('/tableau-de-bord', { replace: true });
    } catch (exc) {
      setErreur(exc instanceof ApiError ? exc.message : 'Connexion impossible — vérifiez que le service GAtraking est démarré');
    } finally {
      setEnCours(false);
    }
  };

  return (
    <div className="min-h-screen bg-app text-ink flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center gap-2 mb-6">
          <div className="w-14 h-14 rounded-xl bg-acc/15 border border-acc/40 flex items-center justify-center">
            <ShieldCheck size={28} className="text-acc" />
          </div>
          <h1 className="text-2xl font-bold tracking-wide">GAtraking</h1>
          <p className="text-sm text-dim">Console d'exploitation de vidéosurveillance intelligente</p>
        </div>

        <form onSubmit={soumettre} className="bg-panel border border-edge rounded-xl p-5 space-y-4">
          {erreur && <Erreur message={erreur} />}
          <Champ libelle="Identifiant">
            <div className="relative">
              <User size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-dim" />
              <input
                className="champ pl-9"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                required
              />
            </div>
          </Champ>
          <Champ libelle="Mot de passe">
            <div className="relative">
              <KeyRound size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-dim" />
              <input
                type="password"
                className="champ pl-9"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>
          </Champ>
          <button type="submit" disabled={enCours} className="btn-primaire w-full">
            {enCours ? <Spin taille={16} /> : null} Se connecter
          </button>
          <p className="text-xs text-dim leading-relaxed border-t border-edge pt-3">
            Premier démarrage : compte <span className="text-ink font-medium">admin</span> /{' '}
            <span className="text-ink font-medium">GAt Admin#2026</span> — mot de passe à changer dès la première
            connexion (menu Utilisateurs).
          </p>
        </form>
      </div>
    </div>
  );
}
