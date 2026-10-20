import MaskedView from '@react-native-masked-view/masked-view';
import { ReactNode } from 'react';
import { StyleSheet } from 'react-native';
import Svg, { Path } from 'react-native-svg';
import { DOCK_HEIGHT } from './dockGeometry';

export function DockMask({ width, path, children }: { width: number; path: string; children: ReactNode }) {
  return <MaskedView style={StyleSheet.absoluteFill} maskElement={<Svg width={width} height={DOCK_HEIGHT}><Path d={path} fill="black" /></Svg>}>{children}</MaskedView>;
}
