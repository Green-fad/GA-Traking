// Notifications toast empilées (coins haut-droit), auto-dismiss 5 s.
import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react';

export type TypeToast = 'succes' | 'erreur' | 'info' | 'avertissement';

interface Toast {
  id: number;
  type: TypeToast;
  texte: string;
}

interface ToastContexte {
  notifier: (texte: string, type?: TypeToast) => void;
}

const Contexte = createContext<ToastContexte | null>(null);

const STYLE: Record<TypeToast, string> = {
  succes: 'border-ok/50 bg-ok/10 text-ok',
  erreur: 'border-danger/50 bg-danger/10 text-danger',
  info: 'border-acc/50 bg-acc/10 text-acc',
  avertissement: 'border-warn/50 bg-warn/10 text-warn',
};

const ICONE: Record<TypeToast, ReactNode> = {
  succes: <CheckCircle2 size={16} />,
  erreur: <XCircle size={16} />,
  info: <Info size={16} />,
  avertissement: <AlertTriangle size={16} />,
};

export function FournisseurToast({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const compteur = useRef(0);

  const retirer = useCallback((id: number) => {
    setToasts((liste) => liste.filter((t) => t.id !== id));
  }, []);

  const notifier = useCallback(
    (texte: string, type: TypeToast = 'info') => {
      compteur.current += 1;
      const id = compteur.current;
      setToasts((liste) => [...liste.slice(-4), { id, type, texte }]);
      window.setTimeout(() => retirer(id), 5000);
    },
    [retirer],
  );

  const valeur = useMemo(() => ({ notifier }), [notifier]);

  return (
    <Contexte.Provider value={valeur}>
      {children}
      <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 w-[min(92vw,360px)]">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-sm shadow-lg backdrop-blur ${STYLE[t.type]}`}
            role="status"
          >
            <span className="mt-0.5 shrink-0">{ICONE[t.type]}</span>
            <span className="flex-1 break-words text-ink">{t.texte}</span>
            <button
              type="button"
              onClick={() => retirer(t.id)}
              className="shrink-0 text-dim hover:text-ink"
              aria-label="Fermer la notification"
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </Contexte.Provider>
  );
}

export function useToast(): ToastContexte {
  const ctx = useContext(Contexte);
  if (!ctx) throw new Error('useToast doit être utilisé dans FournisseurToast');
  return ctx;
}
