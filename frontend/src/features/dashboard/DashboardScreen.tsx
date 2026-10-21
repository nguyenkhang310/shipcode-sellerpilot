import { dockContentInset } from '../../components/layout/dockGeometry';
import { Ionicons } from '@expo/vector-icons';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ManagementData } from '../../api/types';
import { ProductThumbnail } from '../../components/ui/ProductThumbnail';
import { useTheme } from '../../theme/ThemeProvider';
import { OrderDistribution } from './ManagementCharts';
import { count } from './formatters';
import { ActionQueue } from './ActionQueue';
import { PerformanceOverview } from './PerformanceOverview';
import { PeriodPicker } from './PeriodPicker';
import { matchesPeriod } from './dates';

export { money, count } from './formatters';
export type ManagementRoute = { kind: 'products' | 'orders' | 'inventory' | 'tasks' | 'settings'; status?: string };
type Props = {
  data: ManagementData | null; loading: boolean; refreshing: boolean; error: string; days: number;
  selectedDate: string | null; onDate: (date: string) => void; reduceMotion: boolean;
  onDays: (days: number) => void; onRefresh: () => void; onPullRefresh: () => void;
  onOpen: (route: ManagementRoute) => void; onAsk: (message: string) => void;
  onStore: (path: string) => void;
};

export function DashboardScreen({ data, loading, refreshing, error, days, selectedDate, onDate, reduceMotion, onDays, onRefresh, onPullRefresh, onOpen, onAsk, onStore }: Props) {
  const { ui, IOS, BRAND, isDark } = useTheme();
  const insets = useSafeAreaInsets();
  const ready = matchesPeriod(data, days, selectedDate);
  const ink = IOS.label, muted = isDark ? '#A8ADB7' : '#737B88';
  const line = isDark ? '#30343E' : '#E8EBEF', card = isDark ? '#1C1D22' : '#FFFFFF';
  const accent = isDark ? '#C2D6EE' : BRAND.navy;
  const block = { backgroundColor: card, borderColor: line };
  const date = (value: string) => value.slice(8, 10) + '/' + value.slice(5, 7);
  const range = selectedDate ? date(selectedDate) : ready && data ? date(data.from_date) + (data.from_date === data.to_date ? '' : ' – ' + date(data.to_date)) : days === 1 ? 'Hôm nay' : days + ' ngày';
  const analysisMessage = selectedDate && ready && data
    ? `Phân tích số liệu tôi đang xem ngày ${selectedDate}: giá trị đơn hợp lệ ${data.order_value_vnd} đồng, ${data.order_count} đơn, giá trị đơn đã giao ${data.delivered_value_vnd} đồng, ${data.cancelled_count} đơn hủy/hoàn. Đây là số liệu của ngày đã chọn, không thay bằng số hôm nay. Đề xuất kế hoạch 7 ngày tới và cách đo kết quả; không coi giá trị đơn là lợi nhuận.`
    : `Phân tích số liệu ${days} ngày qua và lập kế hoạch kinh doanh 7 ngày tới. Chọn sản phẩm ưu tiên, lịch làm và cách đo kết quả.`;

  return <ScrollView testID="management-scroll" showsVerticalScrollIndicator={false}
    contentContainerStyle={[ui.scroll, { paddingTop: 10, paddingBottom: dockContentInset(insets.bottom) }]}
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
    <View style={[s.section, { marginTop: 24 }]}><Text style={[s.heading, { color: ink }]}>Hiệu quả kinh doanh</Text><Text style={[s.meta, { color: muted, flexShrink: 0 }]}>{range}</Text></View>
    <PeriodPicker days={days} date={selectedDate} onDays={onDays} onDate={onDate} reduceMotion={reduceMotion} />
    {data ? <>
      <PerformanceOverview data={data} days={days} selectedDate={selectedDate} loading={loading} refreshing={refreshing} error={error} onOpen={onOpen} />
      <View style={s.section}><Text style={[s.heading, { color: ink }]}>Việc cần làm</Text><Pressable accessibilityRole="button" onPress={() => onOpen({ kind: 'tasks' })} style={s.link}><Text style={[s.meta, { color: accent, fontWeight: '600' }]}>Xem tất cả</Text><Ionicons name="chevron-forward" size={12} color={accent} /></Pressable></View>
      <ActionQueue data={data} stale={Boolean(error)} onOpen={onOpen} />
      <Text style={[s.meta, { color: muted, marginTop: 7 }]}>Đang chờ xử lý trên toàn shop</Text>
      <OrderDistribution data={data} days={days} selectedDate={selectedDate} pending={!ready} />
      <View style={s.section}><Text style={[s.heading, { color: ink }]}>Sản phẩm nổi bật</Text><Pressable accessibilityRole="button" onPress={() => onOpen({ kind: 'products' })} style={s.link}><Text style={[s.meta, { color: accent, fontWeight: '600' }]}>Danh mục</Text><Ionicons name="chevron-forward" size={12} color={accent} /></Pressable></View>
      <View style={[s.products, block]}>
        <View style={[ui.between, { padding: 15, borderBottomWidth: data.top_products.length ? 1 : 0, borderColor: line }]}>
          <Text style={[s.meta, { color: muted }]}>{count(data.active_products)} đang bán</Text><Text style={[s.meta, { color: muted }]}><Text style={{ color: '#B88227' }}>★ </Text>{data.shop.rating > 0 ? data.shop.rating.toFixed(1) + ' / 5' : 'Chưa có đánh giá'}</Text>
        </View>
        {data.top_products.slice(0, 3).map((product, index) => <Pressable key={product.id} accessibilityRole="button" onPress={() => onStore('/product/' + product.id)} style={[s.product, index > 0 && { borderTopWidth: 1, borderColor: line }]}>
          <Text style={[s.rank, { color: muted }]}>{String(index + 1).padStart(2, '0')}</Text><ProductThumbnail uri={product.image_url} size={48} radius={9} label={'Ảnh ' + product.name} />
          <View style={ui.grow}><Text numberOfLines={2} style={[ui.productName, { fontSize: 15, lineHeight: 22 }]}>{product.name}</Text><Text style={[s.meta, { color: muted, marginTop: 4 }]}>{count(product.sold_count)} đã bán · Lũy kế</Text></View>
          <Ionicons name="chevron-forward" size={13} color={muted} />
        </Pressable>)}
      </View>
      <Pressable accessibilityRole="button" disabled={!ready || loading || Boolean(error)} onPress={() => onAsk(analysisMessage)} style={[s.advisor, { borderColor: isDark ? '#B767374D' : '#EDB48D', backgroundColor: BRAND.orangeSoft, opacity: !ready || loading || error ? .5 : 1 }]}>
        <Ionicons name="analytics-outline" size={20} color={BRAND.orangeInk} /><Text style={[s.meta, { color: BRAND.orangeInk, fontWeight: '600', flex: 1 }]}>Phân tích & lập kế hoạch</Text><Ionicons name="arrow-forward" size={17} color={BRAND.orangeInk} />
      </Pressable>
      <Text style={[s.meta, { color: muted, textAlign: 'center', marginTop: 17 }]}>{error ? 'Chưa đồng bộ số liệu mới' : 'Cập nhật ' + new Date(data.updated_at).toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit' })}</Text>
    </> : <View style={[s.revenue, block, { minHeight: 260, justifyContent: 'center', alignItems: 'center', gap: 12 }]}>{loading ? <ActivityIndicator color={accent} /> : <Ionicons name="storefront-outline" size={30} color={muted} />}<Text style={[s.meta, { color: muted }]}>{loading ? 'Đang lấy số liệu từ shop…' : 'Kết nối shop để xem số liệu'}</Text></View>}
  </ScrollView>;
}

const s = StyleSheet.create({
  title: { fontSize: 29, lineHeight: 36, fontWeight: '700', letterSpacing: -.9 },
  meta: { fontSize: 14, lineHeight: 21 }, iconButton: { width: 44, height: 44, borderRadius: 13, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  shop: { flexDirection: 'row', alignItems: 'center', gap: 11, borderWidth: StyleSheet.hairlineWidth, borderRadius: 19, padding: 13 },
  shopMark: { width: 39, height: 39, borderRadius: 11, alignItems: 'center', justifyContent: 'center' }, shopName: { fontSize: 15, fontWeight: '600' },
  section: { marginTop: 21, marginBottom: 10, minHeight: 34, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  heading: { fontSize: 18, fontWeight: '600', letterSpacing: -.3, flexShrink: 1 }, link: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 3 },
  revenue: { borderWidth: StyleSheet.hairlineWidth, borderRadius: 22, padding: 19 },
  products: { borderWidth: 1, borderRadius: 16, overflow: 'hidden' }, product: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 14, paddingHorizontal: 12 }, rank: { fontSize: 11, fontVariant: ['tabular-nums'] },
  advisor: { marginTop: 18, borderWidth: 1, borderRadius: 14, minHeight: 54, flexDirection: 'row', alignItems: 'center', gap: 11, paddingHorizontal: 15 },
});
