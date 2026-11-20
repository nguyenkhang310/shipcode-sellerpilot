import { SystemIcon } from '../../components/ui/SystemIcon';
import { Pressable, Text } from 'react-native';
import { useTheme } from '../../theme/ThemeProvider';
import type { LiveLanguage } from './live/locale';

export function OrderChatAction({ action, onOpen, language }: { action: unknown; onOpen: (id: number) => void; language?: LiveLanguage }) {
  const { ui, BRAND } = useTheme();
  if (!action || typeof action !== 'object' || !('id' in action)
      || typeof action.id !== 'number' || !Number.isSafeInteger(action.id) || action.id <= 0) return null;
  const id = action.id;
  return <Pressable accessibilityRole="button" accessibilityLabel={(language === 'en' ? 'Open order #' : 'Mở chi tiết đơn #') + id}
    onPress={() => onOpen(id)} style={[ui.secondaryButton, { marginTop: 10, borderColor: BRAND.orange }]}>
    <SystemIcon name="receipt-outline" size={18} color={BRAND.orangeInk} />
    <Text style={[ui.secondaryText, { color: BRAND.orangeInk }]}>{language === 'en' ? 'Track and manage order #' : 'Theo dõi & xử lý đơn #'}{id}</Text>
  </Pressable>;
}
