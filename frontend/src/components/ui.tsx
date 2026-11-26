// Bibliothèque de composants communs : Card, Badge, DataTable, Modal,
// ConfirmButton, PageHeader, EmptyState, Spin.
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Loader2, X, XCircle } from 'lucide-react';

export function Spin({ taille = 20 }: { taille?: number }) {
  return <Loader2 size={taille} className="animate-spin text-acc" aria-label="Chargement en cours" />;
}

export function Chargement({ texte = 'Chargement…' }: { texte?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-dim">
      <Spin /> <span>{texte}</span>
    </div>
  );
}

export function Card({
  titre,
  actions,
  children,
  className = '',
  corpsClassName = '',
}: {
  titre?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  corpsClassName?: string;
}) {
  return (
    <section className={`bg-panel border border-edge rounded-lg ${className}`}>
      {(titre !== undefined || actions !== undefined) && (
        <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-edge">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-dim">{titre}</h2>
          {actions !== undefined && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={`p-4 ${corpsClassName}`}>{children}</div>
    </section>
  );
}

export function Badge({ children, classes = 'bg-panel-soft text-dim border-edge' }: { children: ReactNode; classes?: string }) {
  return <span className={`badge ${classes}`}>{children}</span>;
}

export function PageHeader({
  titre,
  description,
  actions,
}: {
  titre: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 mb-5">
      <div>
        <h1 className="text-xl md:text-2xl font-bold text-ink">{titre}</h1>
        {description && <p className="mt-1 text-sm text-dim max-w-2xl">{description}</p>}
      </div>
      {actions !== undefined && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ icone, titre, texte }: { icone?: ReactNode; titre: string; texte?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
      {icone && <div className="text-dim">{icone}</div>}
      <p className="text-sm font-medium text-ink">{titre}</p>
      {texte && <p className="text-xs text-dim max-w-sm">{texte}</p>}
    </div>
  );
}

export function Erreur({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
      <XCircle size={16} className="shrink-0" /> <span className="break-words">{message}</span>
    </div>
  );
}

// ---- DataTable générique -------------------------------------------------------
export interface Colonne<T> {
  cle: string;
  libelle: string;
  rendu?: (ligne: T) => ReactNode;
  className?: string;
}

interface PropsTableau<T> {
  colonnes: Colonne<T>[];
  lignes: T[] | null;
  cle: (ligne: T) => string;
  surClic?: (ligne: T) => void;
  vide?: ReactNode;
}

export function DataTable<T>({ colonnes, lignes, cle, surClic, vide }: PropsTableau<T>) {
  if (lignes === null) return <Chargement />;
  if (lignes.length === 0) return <>{vide ?? <EmptyState titre="Aucune donnée" />}</>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-dim border-b border-edge">
            {colonnes.map((c) => (
              <th key={c.cle} className={`px-3 py-2 font-semibold whitespace-nowrap ${c.className ?? ''}`}>
                {c.libelle}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lignes.map((ligne) => (
            <tr
              key={cle(ligne)}
              onClick={surClic ? () => surClic(ligne) : undefined}
              className={`border-b border-edge/60 last:border-0 ${surClic ? 'cursor-pointer hover:bg-panel-soft' : 'hover:bg-panel-soft/60'} transition`}
            >
              {colonnes.map((c) => (
                <td key={c.cle} className={`px-3 py-2 align-middle ${c.className ?? ''}`}>
                  {c.rendu ? c.rendu(ligne) : String((ligne as Record<string, unknown>)[c.cle] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---- Modal -----------------------------------------------------------------------
export function Modal({
  ouvert,
  fermer,
  titre,
  children,
  large = false,
}: {
  ouvert: boolean;
  fermer: () => void;
  titre: string;
  children: ReactNode;
  large?: boolean;
}) {
  useEffect(() => {
    if (!ouvert) return;
    const surTouche = (e: KeyboardEvent) => {
      if (e.key === 'Escape') fermer();
    };
    window.addEventListener('keydown', surTouche);
    return () => window.removeEventListener('keydown', surTouche);
  }, [ouvert, fermer]);

  if (!ouvert) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={fermer}
      role="dialog"
      aria-modal="true"
      aria-label={titre}
    >
      <div
        className={`bg-panel border border-edge rounded-xl w-full ${large ? 'max-w-4xl' : 'max-w-lg'} max-h-[90vh] overflow-y-auto shadow-2xl`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-edge sticky top-0 bg-panel rounded-t-xl">
          <h3 className="text-sm font-semibold text-ink">{titre}</h3>
          <button type="button" onClick={fermer} className="text-dim hover:text-ink" aria-label="Fermer">
            <X size={18} />
          </button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

// ---- ConfirmButton : double clic pour confirmer -----------------------------------
export function ConfirmButton({
  onConfirmer,
  libelle,
  libelleConfirmation = 'Confirmer ?',
  className = 'btn-danger',
  disabled = false,
}: {
  onConfirmer: () => void;
  libelle: ReactNode;
  libelleConfirmation?: string;
  className?: string;
  disabled?: boolean;
}) {
  const [enConfirmation, setEnConfirmation] = useState(false);
  const minuteur = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(minuteur.current), []);

  const cliquer = () => {
    if (!enConfirmation) {
      setEnConfirmation(true);
      minuteur.current = window.setTimeout(() => setEnConfirmation(false), 3000);
      return;
    }
    window.clearTimeout(minuteur.current);
    setEnConfirmation(false);
    onConfirmer();
  };

  return (
    <button type="button" onClick={cliquer} disabled={disabled} className={className}>
      {enConfirmation ? libelleConfirmation : libelle}
    </button>
  );
}

// ---- champ de formulaire -----------------------------------------------------------
export function Champ({
  libelle,
  children,
  aide,
}: {
  libelle: string;
  children: ReactNode;
  aide?: string;
}) {
  return (
    <label className="block">
      <span className="block text-xs font-medium uppercase tracking-wide text-dim mb-1">{libelle}</span>
      {children}
      {aide && <span className="block mt-1 text-xs text-dim">{aide}</span>}
    </label>
  );
}
