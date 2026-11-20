import { Ionicons } from '@expo/vector-icons';
import type { SymbolViewProps } from 'expo-symbols';
import { NativeSymbol } from './NativeSymbol';

// SF Symbols are rendered by iOS itself. Other platforms keep bundled glyphs,
// without downloading a font or exporting Apple's symbols as image assets.
const SYMBOLS = {
  'menu-outline': 'line.3.horizontal',
  'create-outline': 'square.and.pencil',
  'notifications-outline': 'bell',
  add: 'plus', close: 'xmark', stop: 'stop.fill', checkmark: 'checkmark',
  'arrow-up': 'arrow.up', 'arrow-up-outline': 'arrow.up',
  'arrow-down': 'arrow.down', 'arrow-forward': 'arrow.right',
  'copy-outline': 'doc.on.doc', 'share-outline': 'square.and.arrow.up',
  refresh: 'arrow.clockwise', 'images-outline': 'photo.on.rectangle',
  'cloud-upload-outline': 'square.and.arrow.up',
  'receipt-outline': 'doc.text', 'chevron-down': 'chevron.down', 'chevron-up': 'chevron.up',
  pin: 'pin.fill', 'pin-outline': 'pin.slash', 'trash-outline': 'trash',
  'ellipsis-horizontal': 'ellipsis',
  'pulse-outline': 'waveform', 'mic-outline': 'mic', 'mic-off-outline': 'mic.slash',
} as const satisfies Record<string, SymbolViewProps['name']>;

export function SystemIcon({ name, size = 22, color }: { name: keyof typeof SYMBOLS; size?: number; color: string }) {
  return <NativeSymbol name={SYMBOLS[name]} size={size} color={color}
    fallback={<Ionicons name={name} size={size} color={color} accessible={false} aria-hidden />} />;
}
