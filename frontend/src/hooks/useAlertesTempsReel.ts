// Connexion WebSocket /ws/alerts?token=JWT avec reconnexion automatique.
// NB : côté serveur le message est {"type": <type d'alerte>, **payload} — le champ
// « type » est écrasé par le type d'alerte (spread du payload). Une nouvelle alerte
// est donc détectée par la présence conjointe de uuid + message + severity.
import { useEffect, useRef } from 'react';
import { urlWebSocketAlertes } from '../api/client';
import type { MessageWsAlerte } from '../api/types';
import { obtenirJeton } from '../api/client';

export function useAlertesTempsReel(
  surNouvelleAlerte: (alerte: MessageWsAlerte) => void,
  actif = true,
): void {
  const rappelRef = useRef(surNouvelleAlerte);
  rappelRef.current = surNouvelleAlerte;

  useEffect(() => {
    if (!actif || !obtenirJeton()) return;
    let ws: WebSocket | null = null;
    let ferme = false;
    let minuteur: number | undefined;

    const connecter = () => {
      try {
        ws = new WebSocket(urlWebSocketAlertes());
      } catch {
        programmerReconnexion();
        return;
      }
      ws.onmessage = (ev: MessageEvent) => {
        try {
          const donnees = JSON.parse(ev.data) as MessageWsAlerte;
          if (donnees && typeof donnees.uuid === 'string' && typeof donnees.message === 'string' && donnees.severity) {
            rappelRef.current(donnees);
          }
        } catch {
          /* message non JSON : ignoré */
        }
      };
      ws.onclose = () => {
        if (!ferme) programmerReconnexion();
      };
      ws.onerror = () => {
        ws?.close();
      };
    };

    const programmerReconnexion = () => {
      if (ferme) return;
      window.clearTimeout(minuteur);
      minuteur = window.setTimeout(connecter, 4000);
    };

    connecter();
    return () => {
      ferme = true;
      window.clearTimeout(minuteur);
      ws?.close();
    };
  }, [actif]);
}

export function estAlerteWs(donnees: unknown): donnees is MessageWsAlerte {
  const d = donnees as MessageWsAlerte | null;
  return (
    d !== null &&
    typeof d === 'object' &&
    typeof d.uuid === 'string' &&
    typeof d.message === 'string' &&
    typeof d.severity === 'string'
  );
}
