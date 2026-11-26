// Titre de document par page (onglet navigateur).
import { useEffect } from 'react';

export function useTitrePage(titre: string): void {
  useEffect(() => {
    document.title = `${titre} — GAtraking`;
    return () => {
      document.title = 'GAtraking — Console d\'exploitation';
    };
  }, [titre]);
}
