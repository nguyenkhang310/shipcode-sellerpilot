import { useEffect, useState } from 'react';
import { Platform } from 'react-native';

/** Modals render outside the app root, so they need their own web keyboard bound. */
export function useModalViewport() {
  const [height, setHeight] = useState<number | undefined>();
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const viewport = window.visualViewport;
    const sync = () => setHeight(viewport ? Math.min(window.innerHeight, viewport.height) : window.innerHeight);
    sync(); viewport?.addEventListener('resize', sync); window.addEventListener('resize', sync);
    return () => { viewport?.removeEventListener('resize', sync); window.removeEventListener('resize', sync); };
  }, []);
  return height;
}
