// Racine : routeur avec routes protégées et gardes par rôle.
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';
import { FournisseurAuth, useAuth } from './state/AuthContext';
import { FournisseurToast } from './state/ToastContext';
import Layout from './components/Layout';
import Connexion from './pages/Connexion';
import TableauDeBord from './pages/TableauDeBord';
import MurVideo from './pages/MurVideo';
import Cameras from './pages/Cameras';
import Cartographie from './pages/Cartographie';
import Alertes from './pages/Alertes';
import Evenements from './pages/Evenements';
import Dossiers from './pages/Dossiers';
import Utilisateurs from './pages/Utilisateurs';
import ParametresIA from './pages/ParametresIA';
import Systeme from './pages/Systeme';
import Assistant from './pages/Assistant';
import { Chargement } from './components/ui';
import type { Role } from './api/types';

function ExigeAuth({ children }: { children: ReactNode }) {
  const { utilisateur, chargement } = useAuth();
  const location = useLocation();
  if (chargement) {
    return (
      <div className="min-h-screen bg-app flex items-center justify-center">
        <Chargement texte="Vérification de la session…" />
      </div>
    );
  }
  if (!utilisateur) {
    return <Navigate to="/connexion" replace state={{ depuis: location.pathname }} />;
  }
  return <>{children}</>;
}

function ExigeRole({ minimum, children }: { minimum: Role; children: ReactNode }) {
  const { roleMinimum } = useAuth();
  if (!roleMinimum(minimum)) {
    return <Navigate to="/tableau-de-bord" replace />;
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <FournisseurAuth>
      <FournisseurToast>
        <BrowserRouter>
          <Routes>
            <Route path="/connexion" element={<Connexion />} />
            <Route
              path="/"
              element={
                <ExigeAuth>
                  <Layout />
                </ExigeAuth>
              }
            >
              <Route index element={<Navigate to="/tableau-de-bord" replace />} />
              <Route path="tableau-de-bord" element={<TableauDeBord />} />
              <Route path="mur-video" element={<MurVideo />} />
              <Route path="cameras" element={<Cameras />} />
              <Route path="cartographie" element={<Cartographie />} />
              <Route path="alertes" element={<Alertes />} />
              <Route path="evenements" element={<Evenements />} />
              <Route path="dossiers" element={<Dossiers />} />
              <Route path="parametres-ia" element={<ParametresIA />} />
              <Route path="systeme" element={<Systeme />} />
              <Route path="assistant" element={<Assistant />} />
              <Route
                path="utilisateurs"
                element={
                  <ExigeRole minimum="admin">
                    <Utilisateurs />
                  </ExigeRole>
                }
              />
              <Route path="*" element={<Navigate to="/tableau-de-bord" replace />} />
            </Route>
            <Route path="*" element={<Navigate to="/tableau-de-bord" replace />} />
          </Routes>
        </BrowserRouter>
      </FournisseurToast>
    </FournisseurAuth>
  );
}
