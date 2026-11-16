import NativeMaskedView from '@react-native-masked-view/masked-view';
import { ComponentType, ReactElement, ReactNode } from 'react';
import { StyleSheet, ViewProps } from 'react-native';
import Svg, { Path } from 'react-native-svg';
import { DOCK_HEIGHT } from './dockGeometry';

// 0.3.2 still declares the removed NativeMethods type. Keep the package's
// documented props checked at this boundary under React Native's strict API.
const MaskedView = NativeMaskedView as unknown as ComponentType<ViewProps & {
  maskElement: ReactElement; androidRenderingMode?: 'software' | 'hardware';
}>;

export function DockMask({ width, path, children }: { width: number; path: string; children: ReactNode }) {
  return <MaskedView style={StyleSheet.absoluteFill} maskElement={<Svg width={width} height={DOCK_HEIGHT}><Path d={path} fill="black" /></Svg>}>{children}</MaskedView>;
}
