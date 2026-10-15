import { Platform } from 'react-native';
import type { MainTab } from '../components/layout/BottomNav';

export function initialTab(): MainTab {
  if (Platform.OS !== 'web') return 'home';
  const search = globalThis.location?.search || '';
  const value = new URLSearchParams(search).get('tab');
  return value === 'assistant' || value === 'chat' ? 'assistant' : 'home';
}
