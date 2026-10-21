import { Ionicons } from '@expo/vector-icons';
import { Pressable, Text } from 'react-native';
import { useTheme } from '../../theme/ThemeProvider';

export function OrderChatAction({ action, onOpen }: { action: unknown; onOpen: (id: number) => void }) {
  const { ui, BRAND } = useTheme();
  if (!action || typeof action !== 'object' || !('id' in action)
      || typeof action.id !== 'number' || !Number.isSafeInteger(action.id) || action.id <= 0) return null;
  const id = action.id;
  return <Pressable accessibilityRole="button" accessibilityLabel={'Mở chi tiết đơn #' + id}
    onPress={() => onOpen(id)} style={[ui.secondaryButton, { marginTop: 10, borderColor: BRAND.orange }]}>
    <Ionicons name="receipt-outline" size={18} color={BRAND.orangeInk} />
    <Text style={[ui.secondaryText, { color: BRAND.orangeInk }]}>Theo dõi & xử lý đơn #{id}</Text>
  </Pressable>;
}
