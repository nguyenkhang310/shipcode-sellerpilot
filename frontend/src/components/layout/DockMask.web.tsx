import { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

// CSS clips the actual backdrop material; no page-colored disk covering content.
export function DockMask({ path, children }: { width: number; path: string; children: ReactNode }) {
  // The filter belongs on the clipped element itself. A filtered parent or a
  // backdrop-filter only on its child isolates the backdrop and leaves text
  // behind the glass sharp in Chromium.
  return <View style={[StyleSheet.absoluteFill, { clipPath: `path("${path}")`, backdropFilter: 'saturate(155%) blur(18px)', WebkitBackdropFilter: 'saturate(155%) blur(18px)' } as object]}>{children}</View>;
}
