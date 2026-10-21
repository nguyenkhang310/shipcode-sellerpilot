import { BlurView } from 'expo-blur';
import { GlassView, isGlassEffectAPIAvailable, isLiquidGlassAvailable } from 'expo-glass-effect';
import { Platform, StyleSheet, View } from 'react-native';
import { dockAppearance } from './dockAppearance';

export function DockMaterial({ dark, opaque }: { dark: boolean; opaque: boolean }) {
  const material = dockAppearance(dark);
  if (opaque) return <View testID="dock-material" style={[StyleSheet.absoluteFill, { backgroundColor: material.solid }]} />;
  const glass = Platform.OS === 'ios' && isGlassEffectAPIAvailable() && isLiquidGlassAvailable();
  return <View pointerEvents="none" style={StyleSheet.absoluteFill}>
    {glass
      ? <GlassView key={dark ? 'dark-glass' : 'light-glass'} glassEffectStyle="regular" colorScheme={dark ? 'dark' : 'light'} tintColor={material.nativeTint} style={StyleSheet.absoluteFill} />
      : <BlurView key={dark ? 'dark-blur' : 'light-blur'} intensity={65} tint={dark ? 'systemMaterialDark' : 'systemMaterialLight'} style={StyleSheet.absoluteFill} />}
    {/* A shared opacity floor keeps chart labels from showing through when
        UIKit changes its glass contrast or the effect is inside a mask. */}
    <View testID="dock-material" style={[StyleSheet.absoluteFill, { backgroundColor: material.frost }]} />
  </View>;
}
