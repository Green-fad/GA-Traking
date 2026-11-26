// Layout : barre latérale 220 px + barre supérieure avec pastilles système.
// Responsive : sur mobile la navigation passe en bandeau horizontal défilant.
import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity,
  Bell,
  Bot,
  Camera,
  FolderSearch,
  LayoutDashboard,
  LogOut,
  Map,
  MonitorPlay,
  ServerCog,
  ShieldCheck,
  SlidersHorizontal,
  Users,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { api } from '../api/client';
import type { RessourcesSysteme } from '../api/types';
import { useAuth } from '../state/AuthContext';
import { libelleRole } from '../utils/format';
import type { Role } from '../api/types';

interface EntreeNav {
  chemin: string;
  libelle: string;
  icone: LucideIcon;
  roleMin?: Role;
}

const NAV: EntreeNav[] = [
  { chemin: '/tableau-de-bord', libelle: 'Tableau de bord', icone: LayoutDashboard },
  { chemin: '/mur-video', libelle: 'Mur vidéo', icone: MonitorPlay },
  { chemin: '/cameras', libelle: 'Caméras', icone: Camera },
  { chemin: '/cartographie', libelle: 'Cartographie', icone: Map },
  { chemin: '/alertes', libelle: 'Alertes', icone: Bell },
  { chemin: '/evenements', libelle: 'Événements', icone: Activity },
  { chemin: '/dossiers', libelle: 'Dossiers', icone: FolderSearch },
  { chemin: '/parametres-ia', libelle: 'Paramètres IA', icone: SlidersHorizontal },
  { chemin: '/systeme', libelle: 'Système', icone: ServerCog },
  { chemin: '/assistant', libelle: 'Assistant', icone: Bot },
  { chemin: '/utilisateurs', libelle: 'Utilisateurs', icone: Users, roleMin: 'admin' },
];

function Pastille({ icone, texte, classes }: { icone: React.ReactNode; texte: string; classes: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium whitespace-nowrap ${classes}`}
    >
      {icone}
      {texte}
    </span>
  );
}

function classeCharge(pct: number): string {
  if (pct > 80) return 'border-danger/40 bg-danger/10 text-danger';
  if (pct > 60) return 'border-warn/40 bg-warn/10 text-warn';
  return 'border-edge bg-panel-soft text-dim';
}

export default function Layout() {
  const { utilisateur, deconnecter } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [ressources, setRessources] = useState<RessourcesSysteme | null>(null);

  useEffect(() => {
    let vivant = true;
    const charger = () => {
      api
        .ressources()
        .then((r) => {
          if (vivant) setRessources(r);
        })
        .catch(() => {
          /* pastilles indisponibles : silencieux */
        });
    };
    charger();
    const interval = window.setInterval(charger, 30000);
    return () => {
      vivant = false;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  const liensVisibles = NAV.filter((n) => !n.roleMin || utilisateur?.role === 'admin');

  return (
    <div className="min-h-screen bg-app text-ink">
      {/* barre latérale — desktop */}
      <aside className="hidden md:flex fixed inset-y-0 left-0 w-[220px] flex-col bg-panel border-r border-edge z-30">
        <div className="flex items-center gap-2.5 px-4 h-14 border-b border-edge">
          <ShieldCheck size={22} className="text-acc shrink-0" />
          <div className="leading-tight">
            <p className="font-bold text-sm tracking-wide">GAtraking</p>
            <p className="text-[10px] text-dim uppercase">Console d'exploitation</p>
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
          {liensVisibles.map((entree) => (
            <NavLink
              key={entree.chemin}
              to={entree.chemin}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition ${
                  isActive
                    ? 'bg-acc/15 text-acc font-semibold'
                    : 'text-dim hover:text-ink hover:bg-panel-soft'
                }`
              }
            >
              <entree.icone size={17} className="shrink-0" />
              <span className="truncate">{entree.libelle}</span>
            </NavLink>
          ))}
        </nav>
        <div className="px-3 py-3 border-t border-edge text-xs text-dim">
          <p className="truncate text-ink font-medium">{utilisateur?.username}</p>
          <p>{libelleRole(utilisateur?.role)}</p>
        </div>
      </aside>

      <div className="md:pl-[220px] flex flex-col min-h-screen">
        {/* barre supérieure */}
        <header className="sticky top-0 z-20 h-14 flex items-center justify-between gap-3 px-4 bg-panel/95 backdrop-blur border-b border-edge">
          <div className="md:hidden flex items-center gap-2">
            <ShieldCheck size={20} className="text-acc" />
            <span className="font-bold text-sm">GAtraking</span>
          </div>
          <div className="hidden md:flex items-center gap-2 flex-wrap">
            <Pastille
              icone="CPU"
              texte={ressources ? `${ressources.cpu_percent.toFixed(0)} %` : '—'}
              classes={classeCharge(ressources?.cpu_percent ?? 0)}
            />
            <Pastille
              icone="RAM"
              texte={ressources ? `${ressources.ram_percent.toFixed(0)} % · ${ressources.ram_total_go} Go` : '—'}
              classes={classeCharge(ressources?.ram_percent ?? 0)}
            />
            <Pastille
              icone="DISQUE"
              texte={ressources ? `${ressources.disque_percent.toFixed(0)} %` : '—'}
              classes={classeCharge(ressources?.disque_percent ?? 0)}
            />
            <Pastille
              icone="ONNX"
              texte={ressources?.acceleration.detecteur ?? '—'}
              classes="border-edge bg-panel-soft text-dim"
            />
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right leading-tight hidden sm:block">
              <p className="text-xs font-semibold text-ink">{utilisateur?.username}</p>
              <p className="text-[10px] text-dim">{libelleRole(utilisateur?.role)}</p>
            </div>
            <button
              type="button"
              onClick={() => {
                deconnecter();
                navigate('/connexion');
              }}
              className="inline-flex items-center gap-1.5 rounded-md border border-edge bg-panel-soft px-2.5 py-1.5 text-xs text-dim hover:text-danger hover:border-danger/40 transition"
            >
              <LogOut size={14} /> Déconnexion
            </button>
          </div>
        </header>

        {/* navigation mobile */}
        <nav className="md:hidden flex overflow-x-auto bg-panel border-b border-edge px-2 py-1.5 gap-1">
          {liensVisibles.map((entree) => (
            <NavLink
              key={entree.chemin}
              to={entree.chemin}
              className={({ isActive }) =>
                `inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs whitespace-nowrap transition ${
                  isActive ? 'bg-acc/15 text-acc font-semibold' : 'text-dim hover:text-ink'
                }`
              }
            >
              <entree.icone size={14} />
              {entree.libelle}
            </NavLink>
          ))}
        </nav>

        <main className="flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
