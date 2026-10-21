import { Ionicons } from '@expo/vector-icons';
import { useEffect, useRef } from 'react';
import { Animated, Easing, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useReducedMotion } from '../../components/layout/useReducedMotion';
import { OrderDetail } from '../../api/types';
import { useTheme } from '../../theme/ThemeProvider';
import { ORDER_STATES, orderDate } from './orderPresentation';

export const ORDER_ACTIONS: Record<string, string> = { paid: 'Xác nhận đơn', shipped: 'Bàn giao vận chuyển', delivered: 'Đã giao thành công', cancelled: 'Hủy đơn' };
const descriptions: Record<string, string> = {
  pending: 'Kiểm tra thông tin và xác nhận để chuẩn bị hàng.', paid: 'Đóng gói sản phẩm và chuẩn bị bàn giao.',
  shipped: 'Đã bàn giao. Theo dõi đơn và ghi nhận khi khách nhận hàng.', delivered: 'Đơn đã hoàn tất. Thông tin giao hàng được giữ để đối soát.',
  cancelled: 'Đơn đã hủy. Không thể tiếp tục chuyển trạng thái.', returned: 'Đơn đã hoàn hàng. Xem ghi nhận và thông tin đơn bên dưới.',
};

export function OrderTracking({ order, onAction, refreshing, onRefresh }: { order: OrderDetail; onAction: (status: string) => void; refreshing: boolean; onRefresh: () => void }) {
  const { IOS, BRAND, ui, isDark } = useTheme();
  const reduced = useReducedMotion(), appear = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    appear.setValue(reduced ? 1 : 0);
    const animation = Animated.timing(appear, { toValue: 1, duration: reduced ? 0 : 180, easing: Easing.out(Easing.cubic), useNativeDriver: Platform.OS !== 'web', isInteraction: false });
    animation.start(); return () => animation.stop();
  }, [order.status, reduced, appear]);
  const state = ORDER_STATES.find(item => item.key === order.status);
  const color = state ? isDark ? state.darkColor : state.color : IOS.secondary;
  const stages = ORDER_STATES.slice(0, 4), current = stages.findIndex(item => item.key === order.status);
  const events = order.events || [];
  const title = (event: OrderDetail['events'][number]) => event.from_status !== event.to_status
    ? ORDER_STATES.find(item => item.key === event.to_status)?.label || 'Cập nhật trạng thái'
    : event.changed_fields.some(field => field === 'tracking_number' || field === 'shipping_carrier') ? 'Cập nhật vận đơn'
      : event.changed_fields.every(field => field === 'note') ? 'Cập nhật ghi chú' : 'Cập nhật thông tin nhận hàng';
  return <Animated.View testID="order-tracking" style={{ gap: 22, opacity: appear, transform: [{ translateY: appear.interpolate({ inputRange: [0, 1], outputRange: [3, 0] }) }] }}>
    <View style={[s.hero, { backgroundColor: BRAND.orangeSoft, borderColor: isDark ? '#67462E' : '#F1CFB7' }]}>
      <View style={[s.statusMark, { backgroundColor: IOS.card }]}><Ionicons name={state?.icon || 'receipt-outline'} size={25} color={color} /></View>
      <View style={{ flex: 1 }}><Text style={[s.overline, { color: BRAND.orangeInk }]}>TIẾN TRÌNH ĐƠN HÀNG</Text><Text accessibilityLiveRegion="polite" style={[s.status, { color: IOS.label }]}>{state?.label || order.status}</Text><Text style={[ui.caption, { marginTop: 4 }]}>{descriptions[order.status] || 'Trạng thái từ gian hàng đang liên kết.'}</Text></View>
    </View>
    {current >= 0 ? <View accessibilityLabel={'Tiến trình hiện tại: ' + state?.label} style={s.progress}>{stages.map((stage, index) => <View key={stage.key} style={s.stage}>
      {index < stages.length - 1 ? <View style={[s.connector, { backgroundColor: index < current ? BRAND.orange : IOS.separator }]} /> : null}
      <View style={[s.circle, { backgroundColor: index <= current ? BRAND.orangeSoft : IOS.card, borderColor: index <= current ? BRAND.orange : IOS.separator }]}><Ionicons name={index < current ? 'checkmark' : stage.icon} size={17} color={index <= current ? BRAND.orangeInk : IOS.secondary} /></View>
      <Text style={[s.stageLabel, { color: index === current ? IOS.label : IOS.secondary, fontWeight: index === current ? '600' : '400' }]}>{['Đặt hàng', 'Chuẩn bị', 'Đang giao', 'Hoàn tất'][index]}</Text>
    </View>)}</View> : null}
    <View style={[s.shipping, { borderColor: IOS.separator }]}><Text style={ui.listTitle}>Thông tin vận chuyển</Text>
      {order.tracking_number ? <><Text style={ui.caption}>{order.shipping_carrier}</Text><Text selectable style={[ui.productName, { fontVariant: ['tabular-nums'], letterSpacing: .5 }]}>{order.tracking_number}</Text></> : <Text style={ui.caption}>Chưa có mã vận đơn. Có thể bổ sung đơn vị vận chuyển và mã khi chuẩn bị hàng.</Text>}
      <Text style={[ui.caption, { fontSize: 12 }]}>Trạng thái do shop cập nhật.</Text>
    </View>
    <View><View style={[ui.between, { marginBottom: 15 }]}><Text style={ui.listTitle}>Lịch sử cập nhật</Text><Pressable accessibilityRole="button" accessibilityLabel="Cập nhật theo dõi đơn" disabled={refreshing} onPress={onRefresh} style={s.refresh}><Ionicons name="refresh-outline" size={17} color={BRAND.orangeInk} /><Text style={{ color: BRAND.orangeInk, fontSize: 12 }}>{refreshing ? 'Đang tải…' : 'Làm mới'}</Text></Pressable></View>
      {order.unrecorded_status_change ? <Text style={[ui.caption, { marginBottom: 15 }]}>Chưa có thời gian ghi nhận cho trạng thái hiện tại.</Text> : null}
      {[...events.map(event => ({ key: String(event.id), title: title(event), date: event.created_at })), { key: 'created', title: 'Đơn được tạo', date: order.created_at }].map((event, index, all) => <View key={event.key} style={s.event}>
        <View style={s.rail}>{index < all.length - 1 ? <View style={[s.eventLine, { backgroundColor: IOS.separator }]} /> : null}<View style={[s.eventDot, { backgroundColor: index === 0 ? BRAND.orange : IOS.tertiary }]} /></View>
        <View style={{ flex: 1, paddingBottom: 20 }}><Text style={[ui.productName, { fontSize: 14 }]}>{event.title}</Text><Text style={[ui.caption, { fontSize: 12, marginTop: 3 }]}>{orderDate(event.date)}</Text></View>
      </View>)}
    </View>
    {order.allowed_statuses.length ? <View style={{ gap: 9 }}><Text style={ui.listTitle}>Thao tác tiếp theo</Text>{order.allowed_statuses.map(next => <Pressable key={next} accessibilityRole="button" accessibilityLabel={'Thực hiện ' + ORDER_ACTIONS[next]} onPress={() => onAction(next)} style={[next === 'cancelled' ? ui.secondaryButton : ui.primaryButton, next !== 'cancelled' && { backgroundColor: BRAND.orangeInk }]}><Ionicons name={next === 'cancelled' ? 'close-circle-outline' : 'arrow-forward'} size={18} color={next === 'cancelled' ? IOS.red : '#FFF'} /><Text style={next === 'cancelled' ? [ui.secondaryText, { color: IOS.red }] : ui.primaryText}>{ORDER_ACTIONS[next]}</Text></Pressable>)}</View> : null}
  </Animated.View>;
}

const s = StyleSheet.create({
  hero: { flexDirection: 'row', gap: 13, padding: 16, borderRadius: 20, borderWidth: StyleSheet.hairlineWidth }, statusMark: { width: 46, height: 46, borderRadius: 15, alignItems: 'center', justifyContent: 'center' },
  overline: { fontSize: 10, lineHeight: 16, letterSpacing: .9, fontWeight: '600' }, status: { fontSize: 21, lineHeight: 29, fontWeight: '600', letterSpacing: -.5 },
  progress: { flexDirection: 'row', marginHorizontal: -8 }, stage: { flex: 1, alignItems: 'center', gap: 8 }, connector: { position: 'absolute', top: 16, left: '50%', width: '100%', height: 2 }, circle: { width: 34, height: 34, borderRadius: 17, borderWidth: 1, alignItems: 'center', justifyContent: 'center' }, stageLabel: { fontSize: 11, lineHeight: 16, textAlign: 'center' },
  shipping: { borderWidth: StyleSheet.hairlineWidth, borderRadius: 16, padding: 15, gap: 8 }, refresh: { minHeight: 44, paddingHorizontal: 8, flexDirection: 'row', alignItems: 'center', gap: 5 },
  event: { flexDirection: 'row', gap: 12 }, rail: { width: 12, alignItems: 'center' }, eventDot: { width: 7, height: 7, borderRadius: 4, marginTop: 8 }, eventLine: { position: 'absolute', width: 1, top: 10, bottom: -10 },
});
