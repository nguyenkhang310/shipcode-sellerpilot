import { SymbolView } from 'expo-symbols';
import type { NativeSymbolProps } from './NativeSymbol';

export function NativeSymbol({ name, size, color }: NativeSymbolProps) {
  return <SymbolView name={name} size={size} tintColor={color} weight="regular" type="monochrome"
    resizeMode="scaleAspectFit" style={{ width: size, height: size }} accessible={false}
    accessibilityElementsHidden importantForAccessibility="no-hide-descendants" />;
}
