import { BlurView } from 'expo-blur';
import { GlassView, isGlassEffectAPIAvailable, isLiquidGlassAvailable } from 'expo-glass-effect';
import { Platform, StyleSheet, View } from 'react-native';
import { dockAppearance } from './dockAppearance';

export function DockMaterial({ dark, opaque }: { dark: boolean; opaque: boolean }) {
  const material = dockAppearance(dark);
  if (opaque) return <View style={[StyleSheet.absoluteFill, { backgroundColor: material.solid }]} />;
  if (Platform.OS === 'ios' && isGlassEffectAPIAvailable() && isLiquidGlassAvailable()) {
    // Recreate only the native effect when the app theme changes. Keep the
    // navigation and its gesture/selection state mounted. No opaque overlay:
    // UIKit owns the tint, contrast, refraction and material appearance.
    return <GlassView key={dark ? 'dark-glass' : 'light-glass'} glassEffectStyle="regular" colorScheme={dark ? 'dark' : 'light'} tintColor={material.nativeTint} style={StyleSheet.absoluteFill} />;
  }
  return <BlurView key={dark ? 'dark-blur' : 'light-blur'} intensity={65} tint={dark ? 'systemUltraThinMaterialDark' : 'systemUltraThinMaterialLight'} style={StyleSheet.absoluteFill} />;
}
