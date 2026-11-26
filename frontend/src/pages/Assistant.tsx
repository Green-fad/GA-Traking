// Assistant : chat avec POST /api/intelligence/assistant — bulles, suggestions
// de questions, note de conformité (aucune sanction automatique).
import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Bot, Send, ShieldCheck, User as UserIcon } from 'lucide-react';
import { api, ApiError } from '../api/client';
import { Card, Erreur, PageHeader, Spin } from '../components/ui';
import { useAuth } from '../state/AuthContext';
import { useTitrePage } from '../hooks/useTitrePage';

interface Message {
  auteur: 'utilisateur' | 'assistant';
  texte: string;
  source?: string;
}

const SUGGESTIONS = [
  "Combien d'alertes sont ouvertes ?",
  'Résume l\u2019activité des dernières 24 heures',
  'Quelles caméras sont hors ligne ?',
  'Combien de dossiers attendent une vérification ?',
  'Quel est l\u2019état du stockage des médias ?',
];

export default function Assistant() {
  useTitrePage('Assistant');
  const { utilisateur } = useAuth();
  const [messages, setMessages] = useState<Message[]>([
    {
      auteur: 'assistant',
      texte:
        "Bonjour. Je suis l'assistant d'exploitation GAtraking : je réponds à vos questions à partir des données réelles de la plateforme (alertes, caméras, dossiers, stockage).",
      source: 'base_locale',
    },
  ]);
  const [saisie, setSaisie] = useState('');
  const [enCours, setEnCours] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const finRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, enCours]);

  const envoyer = useCallback(
    async (texte: string) => {
      const question = texte.trim();
      if (!question || enCours) return;
      setErreur(null);
      setMessages((m) => [...m, { auteur: 'utilisateur', texte: question }]);
      setSaisie('');
      setEnCours(true);
      try {
        const reponse = await api.assistant(question.slice(0, 2000));
        setMessages((m) => [...m, { auteur: 'assistant', texte: reponse.reponse, source: reponse.source }]);
      } catch (exc) {
        setErreur(
          exc instanceof ApiError ? exc.message : "L'assistant est momentanément indisponible (service non démarré)",
        );
      } finally {
        setEnCours(false);
      }
    },
    [enCours],
  );

  const soumettre = (e: FormEvent) => {
    e.preventDefault();
    void envoyer(saisie);
  };

  return (
    <>
      <PageHeader
        titre="Assistant d'exploitation"
        description="Interrogez la plateforme en langage naturel — l'assistant répond à partir des données locales de GAtraking."
      />

      <div className="mb-4 rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-4 py-3 text-sm text-indigo-200">
        <span className="inline-flex items-center gap-1.5 font-semibold">
          <ShieldCheck size={15} /> Conformité —
        </span>{' '}
        l'assistant est un outil d'aide à l'exploitation : il ne prononce{' '}
        <span className="font-semibold">aucune sanction automatique</span> et ses réponses s'appuient exclusivement sur
        les données réelles de la plateforme (aucune invention de chiffres).
      </div>

      <Card corpsClassName="p-0">
        <div className="h-[420px] overflow-y-auto p-4 space-y-3">
          {messages.map((m, i) => (
            <div key={i} className={`flex items-start gap-2.5 ${m.auteur === 'utilisateur' ? 'justify-end' : ''}`}>
              {m.auteur === 'assistant' && (
                <div className="w-8 h-8 rounded-lg bg-acc/15 border border-acc/40 flex items-center justify-center shrink-0">
                  <Bot size={16} className="text-acc" />
                </div>
              )}
              <div
                className={`max-w-[80%] md:max-w-[70%] rounded-xl px-3.5 py-2.5 text-sm ${
                  m.auteur === 'utilisateur'
                    ? 'bg-indigo-500/20 border border-indigo-500/40 text-ink rounded-tr-sm'
                    : 'bg-panel-soft border border-edge text-ink rounded-tl-sm'
                }`}
              >
                <p className="whitespace-pre-wrap break-words leading-relaxed">{m.texte}</p>
                {m.source && <p className="mt-1 text-[10px] text-dim">source : {m.source}</p>}
              </div>
              {m.auteur === 'utilisateur' && (
                <div className="w-8 h-8 rounded-lg bg-indigo-500/20 border border-indigo-500/40 flex items-center justify-center shrink-0">
                  <UserIcon size={16} className="text-indigo-400" />
                </div>
              )}
            </div>
          ))}
          {enCours && (
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-acc/15 border border-acc/40 flex items-center justify-center shrink-0">
                <Spin taille={14} />
              </div>
              <span className="text-sm text-dim">L'assistant analyse les données…</span>
            </div>
          )}
          <div ref={finRef} />
        </div>

        <div className="border-t border-edge p-3">
          <div className="flex flex-wrap gap-1.5 mb-2.5">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => void envoyer(s)}
                disabled={enCours}
                className="text-xs rounded-full border border-edge bg-panel-soft text-dim px-2.5 py-1 hover:text-acc hover:border-acc/40 transition disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>
          {erreur && <div className="mb-2.5"><Erreur message={erreur} /></div>}
          <form onSubmit={soumettre} className="flex items-center gap-2">
            <input
              className="champ"
              value={saisie}
              onChange={(e) => setSaisie(e.target.value)}
              placeholder={`Posez votre question, ${utilisateur?.username ?? ''}…`}
              maxLength={2000}
            />
            <button type="submit" className="btn-primaire shrink-0" disabled={enCours || saisie.trim().length === 0}>
              <Send size={15} /> Envoyer
            </button>
          </form>
        </div>
      </Card>
    </>
  );
}
