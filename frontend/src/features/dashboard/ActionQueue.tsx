import { Ionicons } from '@expo/vector-icons';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { ManagementData } from '../../api/types';
import { useTheme } from '../../theme/ThemeProvider';
import type { ManagementRoute } from './DashboardScreen';
import { count } from './formatters';

export function ActionQueue({ data, stale, onOpen }: { data: ManagementData; stale: boolean; onOpen: (route: ManagementRoute) => void }) {
  const { IOS, BRAND } = useTheme();
  const items = [
    { label: 'Chờ xác nhận', title: 'đơn chờ xác nhận', value: data.tasks.pending_orders, route: { kind: 'orders', status: 'pending' } },
    { label: 'Chờ lấy hàng', title: 'đơn chờ lấy hàng', value: data.tasks.packing_orders, route: { kind: 'orders', status: 'paid' } },
    { label: 'Sắp hết hàng', title: 'sản phẩm sắp hết', value: data.tasks.low_stock_products, route: { kind: 'inventory' } },
  ] as const;
  const priority = items.find(item => item.value > 0);
  const accent = BRAND.orangeInk;
  const title = stale ? 'Cần cập nhật số liệu' : priority ? `${count(priority.value)} ${priority.title}` : 'Không có mục chờ xử lý';
  return <View testID="action-queue" style={[s.card, { backgroundColor: IOS.card, borderColor: IOS.separator }]}>
    <Pressable accessibilityRole="button" accessibilityLabel={title} onPress={() => onOpen(stale || !priority ? { kind: 'tasks' } : priority.route)} style={({ pressed }) => [s.priority, { backgroundColor: BRAND.orangeSoft, opacity: pressed ? .85 : 1 }]}>
      <View style={[s.mark, { backgroundColor: BRAND.orange }]} />
      <View style={{ flex: 1, minWidth: 0 }}><Text style={[s.eyebrow, { color: accent }]}>ƯU TIÊN HÔM NAY</Text><Text numberOfLines={2} style={[s.title, { color: IOS.label }]}>{title}</Text></View>
      <Ionicons name="arrow-forward" size={19} color={accent} />
    </Pressable>
    <View style={s.lanes}>{items.map((item, index) => <Pressable key={item.label} accessibilityRole="button" accessibilityLabel={item.label + ': ' + (stale ? 'chờ cập nhật' : count(item.value))} onPress={() => onOpen(item.route)} style={[s.lane, index > 0 && { borderLeftWidth: StyleSheet.hairlineWidth, borderColor: IOS.separator }]}>
      <Text numberOfLines={1} adjustsFontSizeToFit style={[s.number, { color: BRAND.navy }]}>{stale ? '—' : count(item.value)}</Text><Text numberOfLines={2} style={[s.label, { color: IOS.secondary }]}>{item.label}</Text>
    </Pressable>)}</View>
  </View>;
}

const s = StyleSheet.create({
  card: { borderWidth: StyleSheet.hairlineWidth, borderRadius: 24, overflow: 'hidden' },
  priority: { minHeight: 104, flexDirection: 'row', alignItems: 'center', padding: 16, gap: 12 },
  mark: { width: 3, height: 38, borderRadius: 2 },
  eyebrow: { fontSize: 11, lineHeight: 17, fontWeight: '600', letterSpacing: 1 },
  title: { fontSize: 16, lineHeight: 23, fontWeight: '600', marginTop: 3, minHeight: 46 },
  lanes: { flexDirection: 'row', paddingVertical: 15 }, lane: { flex: 1, paddingHorizontal: 8, alignItems: 'center', gap: 5, minHeight: 68 },
  number: { fontSize: 24, lineHeight: 29, fontWeight: '600', fontVariant: ['tabular-nums'], letterSpacing: -.6 },
  label: { fontSize: 13, lineHeight: 18, textAlign: 'center', minHeight: 36 },
});
