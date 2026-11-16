import type { ReactNode } from 'react';
import type { SymbolViewProps } from 'expo-symbols';

export type NativeSymbolProps = {
  name: SymbolViewProps['name']; size: number; color: string; fallback: ReactNode;
};

// Metro picks the iOS implementation on iPhone. Web/Android never import the
// native symbol package or its Material Symbols font and lookup table.
export function NativeSymbol({ fallback }: NativeSymbolProps) { return <>{fallback}</>; }
