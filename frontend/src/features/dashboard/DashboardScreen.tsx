import { Ionicons } from '@expo/vector-icons';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ManagementData } from '../../api/types';
import { ProductThumbnail } from '../../components/ui/ProductThumbnail';
import { useTheme } from '../../theme/ThemeProvider';
import { OrderDistribution, SalesTrend } from './ManagementCharts';
import { count, money } from './formatters';

export { money, count } from './formatters';
export type ManagementRoute = { kind: 'products' | 'orders' | 'inventory' | 'tasks' | 'settings'; status?: string };
type Props = {
  data: ManagementData | null; loading: boolean; refreshing: boolean; error: string; days: number;
  onDays: (days: number) => void; onRefresh: () => void; onPullRefresh: () => void;
  onOpen: (route: ManagementRoute) => void; onAsk: (message: string) => void;
  onStore: (path: string) => void;
};

export function DashboardScreen({ data, loading, refreshing, error, days, onDays, onRefresh, onPullRefresh, onOpen, onAsk, onStore }: Props) {
  const { ui, IOS, BRAND, isDark } = useTheme();
  const insets = useSafeAreaInsets();
  const ready = data?.days === days;
  const ink = IOS.label, muted = isDark ? '#A8ADB7' : '#737B88';
  const line = isDark ? '#30343E' : '#E8EBEF', card = isDark ? '#1C1D22' : '#FFFFFF';
  const accent = isDark ? '#C2D6EE' : BRAND.navy;
  const block = { backgroundColor: card, borderColor: line };
  const shown = (value: number | undefined, currency = false) => ready && value !== undefined ? (currency ? money(value) : count(value)) : '—';
  const tasks = [
    { icon: 'receipt-outline', label: 'Chờ xác nhận', value: data?.tasks.pending_orders, action: () => onOpen({ kind: 'orders', status: 'pending' }) },
    { icon: 'cube-outline', label: 'Chờ lấy hàng', value: data?.tasks.packing_orders, action: () => onOpen({ kind: 'orders', status: 'paid' }) },
    { icon: 'layers-outline', label: 'Sắp hết hàng', value: data?.tasks.low_stock_products, action: () => onOpen({ kind: 'inventory' }) },
  ] as const;
  const stats = [
    { label: 'Đơn hợp lệ', value: shown(data?.order_count), icon: 'receipt-outline', testID: 'dashboard-order-count', action: () => onOpen({ kind: 'orders' }) },
    { label: 'Trung bình mỗi đơn', value: shown(data?.average_order_vnd, true), icon: 'wallet-outline', action: () => onOpen({ kind: 'orders' }) },
    { label: 'Giá trị đơn đã giao', value: shown(data?.delivered_value_vnd, true), icon: 'checkmark-circle-outline', action: () => onOpen({ kind: 'orders', status: 'delivered' }) },
    { label: 'Đơn đã hủy', value: shown(data?.order_status_counts?.cancelled), icon: 'return-down-back-outline', action: () => onOpen({ kind: 'orders', status: 'cancelled' }) },
  ] as const;
  const date = (value: string) => value.slice(8, 10) + '/' + value.slice(5, 7);
  const range = ready && data ? date(data.from_date) + (data.from_date === data.to_date ? '' : ' – ' + date(data.to_date)) : days === 1 ? 'Hôm nay' : days + ' ngày';

  return <ScrollView testID="management-scroll" showsVerticalScrollIndicator={false}
    contentContainerStyle={[ui.scroll, { paddingTop: 10, paddingBottom: 112 + insets.bottom }]}
    refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onPullRefresh} tintColor={accent} />}>
    <View style={[ui.between, { alignItems: 'flex-start', marginBottom: 18 }]}>
      <View style={ui.grow}><Text accessibilityRole="header" style={[s.title, { color: ink }]}>Quản lý</Text>
        <Text style={[s.meta, { color: muted, marginTop: 5 }]}>{new Date().toLocaleDateString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', weekday: 'long', day: 'numeric', month: 'long' })}</Text></View>
      <Pressable accessibilityRole="button" accessibilityLabel="Đồng bộ số liệu" accessibilityState={{ disabled: loading, busy: loading }} onPress={onRefresh} disabled={loading} style={[s.iconButton, block]}>
        <Ionicons name="refresh-outline" size={20} color={accent} />
      </Pressable>
    </View>
    <Pressable accessibilityRole="button" accessibilityLabel="Thông tin shop đang kết nối" onPress={() => onOpen({ kind: 'settings' })} style={[s.shop, block]}>
      <View style={[s.shopMark, { backgroundColor: isDark ? '#293341' : '#F1F4F8' }]}><Ionicons name="storefront-outline" size={20} color={accent} /></View>
      <View style={ui.grow}><Text numberOfLines={1} style={[s.shopName, { color: ink }]}>{data?.shop.name || 'Gian hàng của bạn'}</Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 3 }}><View style={[ui.dot, { width: 5, height: 5 }, (!data || Boolean(error)) && { backgroundColor: muted }]} /><Text style={[s.meta, { color: muted }]}>{error ? 'Chưa đồng bộ' : data ? 'Shopee · Đã kết nối' : 'Đang kết nối'}</Text></View></View>
      <Ionicons name="chevron-forward" size={15} color={muted} />
    </Pressable>
    {error && !data ? <View style={ui.errorCard}><Text style={ui.error}>{error}</Text><Pressable accessibilityRole="button" onPress={onRefresh} style={ui.secondaryButton}><Text style={ui.secondaryText}>Thử kết nối lại</Text></Pressable></View> : null}
    <View style={[s.section, { marginTop: 24 }]}><Text style={[s.heading, { color: ink }]}>Hiệu quả kinh doanh</Text><Text style={[s.meta, { color: muted }]}>{range}</Text></View>
    <View style={[s.period, { borderColor: line }]}>{([[1, 'Hôm nay'], [7, '7 ngày'], [30, '30 ngày']] as const).map(([value, label]) =>
      <Pressable key={value} accessibilityRole="button" accessibilityState={{ selected: days === value }} onPress={() => onDays(value)} style={[s.periodItem, days === value && { backgroundColor: card, borderColor: line }]}>
        <Text style={[s.periodText, { color: days === value ? ink : muted, fontWeight: days === value ? '600' : '400' }]}>{label}</Text>
      </Pressable>)}</View>
    {data ? <>
      <View testID="period-summary" accessibilityLabel={ready ? `Số liệu ${days} ngày` : `${loading ? 'Đang tải' : 'Chưa có'} số liệu ${days} ngày`} style={[s.revenue, block]}>
        <View style={[ui.between, { minHeight: 26 }]}><Text style={[s.meta, { color: muted }]}>Giá trị đơn hàng</Text>
          {ready && data.change_percent !== null ? <View style={[s.change, { backgroundColor: isDark ? '#22342F' : data.change_percent < 0 ? '#FAEFED' : '#EDF6F0' }]}>
            <Ionicons name={data.change_percent >= 0 ? 'trending-up-outline' : 'trending-down-outline'} size={14} color={data.change_percent >= 0 ? '#378064' : '#B15A50'} />
            <Text style={{ color: data.change_percent >= 0 ? (isDark ? '#9DDBB9' : '#287454') : '#B15A50', fontSize: 12, fontWeight: '600' }}>{data.change_percent > 0 ? '+' : ''}{data.change_percent}%</Text>
          </View> : null}
        </View>
        <Text numberOfLines={1} adjustsFontSizeToFit style={[s.amount, { color: ink }]}>{ready ? count(data.order_value_vnd) : '—'}<Text style={{ fontSize: 22, fontWeight: '400', color: muted }}> ₫</Text></Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: 38 }}>
          {loading && !refreshing ? <ActivityIndicator testID="period-loading" size="small" color={accent} /> : null}
          <Text accessibilityLiveRegion="polite" numberOfLines={2} style={[s.meta, { color: error ? IOS.red : muted, flex: 1 }]}>{error || (loading ? 'Đang lấy số liệu kỳ này…' : 'Đơn hợp lệ · Không gồm đơn hủy / hoàn')}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 14, marginTop: 16, paddingTop: 13, borderTopWidth: 1, borderColor: line }}>{stats.slice(0, 2).map(item => <Pressable key={item.label} accessibilityRole="button" onPress={item.action} style={{ flex: 1, minWidth: 0, minHeight: 52 }}>
          <Text style={[s.meta, { color: muted }]}>{item.label}</Text><Text testID={'testID' in item ? item.testID : undefined} numberOfLines={1} adjustsFontSizeToFit style={[s.metricNumber, { color: ink, fontSize: 20, marginTop: 4 }]}>{item.value}</Text>
        </Pressable>)}</View>
        <SalesTrend data={data} days={days} pending={!ready} />
        <Text numberOfLines={1} style={[s.meta, { color: muted, paddingTop: 4, minHeight: 23 }]}>{ready ? data.change_percent !== null ? 'So với cùng thời lượng kỳ trước' : 'Chưa có dữ liệu kỳ trước để so sánh' : ' '}</Text>
      </View>
      <View style={s.metrics}>{stats.slice(2).map(item => <Pressable key={item.label} accessibilityRole="button" onPress={item.action} style={[s.metric, block]}>
        <View style={[ui.between, { gap: 5 }]}><Text style={[s.meta, { color: muted, flex: 1 }]}>{item.label}</Text><Ionicons name={item.icon} size={16} color={muted} /></View>
        <Text testID={'testID' in item ? item.testID : undefined} numberOfLines={1} adjustsFontSizeToFit style={[s.metricNumber, { color: ink }]}>{item.value}</Text>
      </Pressable>)}</View>
      <View style={s.section}><Text style={[s.heading, { color: ink }]}>Việc cần làm</Text><Pressable accessibilityRole="button" onPress={() => onOpen({ kind: 'tasks' })} style={s.link}><Text style={[s.meta, { color: accent, fontWeight: '600' }]}>Xem tất cả</Text><Ionicons name="chevron-forward" size={12} color={accent} /></Pressable></View>
      <View style={[s.tasks, block]}>{tasks.map((task, index) => <Pressable key={task.label} accessibilityRole="button" onPress={task.action} style={[s.task, index > 0 && { borderLeftWidth: 1, borderColor: line }]}>
        <Ionicons name={task.icon} size={20} color={accent} />
        <Text style={[s.taskNumber, { color: (task.value || 0) > 0 && index === 0 ? (isDark ? '#F0B87C' : '#B77031') : ink }]}>{task.value === undefined ? '—' : count(task.value)}</Text>
        <Text style={[s.meta, { color: muted, textAlign: 'center' }]}>{task.label}</Text>
      </Pressable>)}</View>
      <Text style={[s.meta, { color: muted, marginTop: 7 }]}>Đang chờ xử lý trên toàn shop</Text>
      <OrderDistribution data={data} days={days} pending={!ready} />
      <View style={s.section}><Text style={[s.heading, { color: ink }]}>Sản phẩm nổi bật</Text><Pressable accessibilityRole="button" onPress={() => onOpen({ kind: 'products' })} style={s.link}><Text style={[s.meta, { color: accent, fontWeight: '600' }]}>Danh mục</Text><Ionicons name="chevron-forward" size={12} color={accent} /></Pressable></View>
      <View style={[s.products, block]}>
        <View style={[ui.between, { padding: 15, borderBottomWidth: data.top_products.length ? 1 : 0, borderColor: line }]}>
          <Text style={[s.meta, { color: muted }]}>{count(data.active_products)} đang bán</Text><Text style={[s.meta, { color: muted }]}><Text style={{ color: '#B88227' }}>★ </Text>{data.shop.rating > 0 ? data.shop.rating.toFixed(1) + ' / 5' : 'Chưa có đánh giá'}</Text>
        </View>
        {data.top_products.slice(0, 3).map((product, index) => <Pressable key={product.id} accessibilityRole="button" onPress={() => onStore('/product/' + product.id)} style={[s.product, index > 0 && { borderTopWidth: 1, borderColor: line }]}>
          <Text style={[s.rank, { color: muted }]}>{String(index + 1).padStart(2, '0')}</Text><ProductThumbnail uri={product.image_url} size={48} radius={9} label={'Ảnh ' + product.name} />
          <View style={ui.grow}><Text numberOfLines={2} style={[ui.productName, { fontSize: 14, lineHeight: 20 }]}>{product.name}</Text><Text style={[s.meta, { color: muted, marginTop: 4 }]}>{count(product.sold_count)} đã bán · Lũy kế</Text></View>
          <Ionicons name="chevron-forward" size={13} color={muted} />
        </Pressable>)}
      </View>
      <Pressable accessibilityRole="button" onPress={() => onAsk(`Phân tích số liệu ${days} ngày qua và lập kế hoạch kinh doanh 7 ngày tới. Chọn sản phẩm ưu tiên, lịch làm và cách đo kết quả.`)} style={[s.advisor, { borderColor: line }]}>
        <Ionicons name="analytics-outline" size={20} color={accent} /><Text style={[s.meta, { color: accent, fontWeight: '600', flex: 1 }]}>Phân tích & lập kế hoạch</Text><Ionicons name="arrow-forward" size={17} color={accent} />
      </Pressable>
      <Text style={[s.meta, { color: muted, textAlign: 'center', marginTop: 17 }]}>{error ? 'Chưa đồng bộ số liệu mới' : 'Cập nhật ' + new Date(data.updated_at).toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit' })}</Text>
    </> : <View style={[s.revenue, block, { minHeight: 260, justifyContent: 'center', alignItems: 'center', gap: 12 }]}>{loading ? <ActivityIndicator color={accent} /> : <Ionicons name="storefront-outline" size={30} color={muted} />}<Text style={[s.meta, { color: muted }]}>{loading ? 'Đang lấy số liệu từ shop…' : 'Kết nối shop để xem số liệu'}</Text></View>}
  </ScrollView>;
}

const s = StyleSheet.create({
  title: { fontSize: 29, lineHeight: 36, fontWeight: '700', letterSpacing: -.9 },
  meta: { fontSize: 13, lineHeight: 19 }, iconButton: { width: 42, height: 42, borderRadius: 13, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  shop: { flexDirection: 'row', alignItems: 'center', gap: 11, borderWidth: 1, borderRadius: 15, padding: 13 },
  shopMark: { width: 39, height: 39, borderRadius: 11, alignItems: 'center', justifyContent: 'center' }, shopName: { fontSize: 15, fontWeight: '600' },
  section: { marginTop: 21, marginBottom: 10, minHeight: 34, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  heading: { fontSize: 17, fontWeight: '600', letterSpacing: -.3 }, link: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 3 },
  period: { flexDirection: 'row', padding: 3, borderWidth: 1, borderRadius: 12, marginBottom: 12 }, periodItem: { flex: 1, minHeight: 40, borderWidth: 1, borderColor: 'transparent', borderRadius: 9, alignItems: 'center', justifyContent: 'center' }, periodText: { fontSize: 13 },
  revenue: { borderWidth: 1, borderRadius: 18, padding: 18 }, change: { flexDirection: 'row', gap: 4, alignItems: 'center', paddingHorizontal: 7, paddingVertical: 4, borderRadius: 6 },
  amount: { fontSize: 37, lineHeight: 48, fontWeight: '600', letterSpacing: -1.5, marginTop: 7, fontVariant: ['tabular-nums'] },
  metrics: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 10 }, metric: { width: '48%', flexGrow: 1, borderWidth: 1, borderRadius: 14, padding: 14, minWidth: 120 }, metricNumber: { fontSize: 23, lineHeight: 28, fontWeight: '600', letterSpacing: -.65, marginTop: 9, fontVariant: ['tabular-nums'] },
  tasks: { flexDirection: 'row', borderWidth: 1, borderRadius: 16, paddingVertical: 17 }, task: { flex: 1, alignItems: 'center', gap: 6, paddingHorizontal: 7 }, taskNumber: { fontSize: 25, fontWeight: '600', fontVariant: ['tabular-nums'] },
  products: { borderWidth: 1, borderRadius: 16, overflow: 'hidden' }, product: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 14, paddingHorizontal: 12 }, rank: { fontSize: 11, fontVariant: ['tabular-nums'] },
  advisor: { marginTop: 18, borderWidth: 1, borderRadius: 14, minHeight: 54, flexDirection: 'row', alignItems: 'center', gap: 11, paddingHorizontal: 15 },
});
