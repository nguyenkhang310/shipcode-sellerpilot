import { StyleSheet, View } from 'react-native';
import { dockAppearance } from './dockAppearance';

// Backdrop blur lives on DockMask.web, so the tint is applied only once.
export function DockMaterial({ dark, opaque }: { dark: boolean; opaque: boolean }) {
  const material = dockAppearance(dark);
  return <View testID="dock-material" style={[StyleSheet.absoluteFill, { backgroundColor: opaque ? material.solid : material.frost }]} />;
}
