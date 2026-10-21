import { useEffect, useRef } from 'react';
import { Keyboard, ScrollView } from 'react-native';

/** Keep the focused field above a modal's pinned footer after keyboard resize. */
export function useFormScroll(viewportHeight?: number) {
  const ref = useRef<ScrollView>(null);
  const positions = useRef<Record<string, number>>({});
  const focused = useRef<{ key: string; offset: number } | null>(null);
  const frame = useRef<number | null>(null);
  const reveal = () => {
    if (!focused.current) return;
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      frame.current = null;
      const field = focused.current;
      if (field && positions.current[field.key] !== undefined) ref.current?.scrollTo({ y: Math.max(0, positions.current[field.key]! + field.offset - 8), animated: false });
    });
  };
  useEffect(reveal, [viewportHeight]);
  useEffect(() => {
    const listener = Keyboard.addListener('keyboardDidShow', reveal);
    return () => { listener.remove(); if (frame.current !== null) cancelAnimationFrame(frame.current); };
  }, []);
  return { ref, position: (key: string, y: number) => { positions.current[key] = y; },
    focus: (key: string, offset = 0) => { focused.current = { key, offset }; reveal(); },
    blur: () => { focused.current = null; } };
}
