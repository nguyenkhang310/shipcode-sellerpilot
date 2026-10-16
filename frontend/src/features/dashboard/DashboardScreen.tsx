import { Ionicons } from '@expo/vector-icons';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ManagementData } from '../../api/types';
import { BrandLogo } from '../../components/ui/BrandLogo';
import { ProductThumbnail } from '../../components/ui/ProductThumbnail';
import { useTheme } from '../../theme/ThemeProvider';
import { OrderDistribution, SalesTrend } from './ManagementCharts';
import { count, money } from './formatters';

export { money, count } from './formatters';
export type ManagementRoute = {
  kind: 'products' | 'orders' | 'inventory' | 'tasks' | 'settings';
  status?: string;
};

type Props = {
  data: ManagementData | null;
  loading: boolean;
  error: string;
  days: number;
  onDays: (days: number) => void;
  onRefresh: () => void;
  onOpen: (route: ManagementRoute) => void;
  onAsk: (message: string) => void;
  onStore: (path: string) => void;
};

export function DashboardScreen({ data, loading, error, days, onDays, onRefresh, onOpen, onAsk, onStore }: Props) {
  const { ui, IOS, BRAND, isDark } = useTheme();
  const insets = useSafeAreaInsets();
  const periodReady = data?.days === days;
  const tasks = [
    { icon: 'time-outline', label: 'Chờ xác nhận', value: data?.tasks.pending_orders,
      action: () => onOpen({ kind: 'orders', status: 'pending' }) },
    { icon: 'cube-outline', label: 'Hàng sắp hết', value: data?.tasks.low_stock_products,
      action: () => onOpen({ kind: 'inventory' }) },
    { icon: 'chatbubble-ellipses-outline', label: 'Đánh giá chưa trả lời', value: data?.tasks.unanswered_reviews,
      action: () => onStore('/seller/reviews?unanswered=1') },
  ] as const;

  return (
    <ScrollView testID="management-scroll" showsVerticalScrollIndicator={false}
      contentContainerStyle={[ui.scroll, { paddingBottom: 112 + insets.bottom }]}
      refreshControl={<RefreshControl refreshing={loading && Boolean(data)} onRefresh={onRefresh} tintColor={BRAND.navy} />}>
      <View style={ui.pageHeading}>
        <Text accessibilityRole="header" style={ui.title}>Quản lý</Text>
        <Text style={ui.pageDate}>{new Date().toLocaleDateString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', weekday: 'long', day: 'numeric', month: 'long' })}</Text>
      </View>
      <Pressable accessibilityRole="button" accessibilityLabel="Thông tin shop đang kết nối"
        onPress={() => onOpen({ kind: 'settings' })} style={ui.shopCard}>
        <View style={ui.shopIcon}><Ionicons name="storefront-outline" size={21} color={BRAND.navy} /></View>
        <View style={ui.grow}>
          <Text numberOfLines={1} style={ui.shopName}>{data?.shop.name || 'Gian hàng của bạn'}</Text>
          <View style={[ui.row, { gap: 5, marginTop: 4 }]}>
            <View style={[ui.dot, (!data || Boolean(error)) && { backgroundColor: IOS.tertiary }]} />
            <Text style={ui.connected}>{error ? 'Chưa đồng bộ' : data ? 'UTE MALL · Đã kết nối' : 'Đang kết nối'}</Text>
          </View>
        </View>
        <Ionicons name="chevron-forward" size={15} color={IOS.tertiary} />
      </Pressable>
      {error ? (
        <View style={ui.errorCard}>
          <Text style={ui.error}>{error}</Text>
          <Pressable accessibilityRole="button" onPress={onRefresh} style={ui.secondaryButton}>
            <Text style={ui.secondaryText}>Thử kết nối lại</Text>
          </Pressable>
        </View>
      ) : null}
      <View style={[ui.segment, { marginTop: 22 }]}>
        {([[1, 'Hôm nay'], [7, '7 ngày'], [30, '30 ngày']] as const).map(([value, label]) => (
          <Pressable key={value} accessibilityRole="button" accessibilityState={{ selected: days === value }}
            onPress={() => onDays(value)} style={[ui.segmentItem, days === value && ui.segmentSelected]}>
            <Text style={[ui.segmentText, days === value && ui.segmentTextSelected]}>{label}</Text>
          </Pressable>
        ))}
      </View>
      {data ? (
        <>
          <View testID="period-summary" accessibilityLabel={periodReady ? `Số liệu ${days} ngày` : `${loading ? 'Đang tải' : 'Chưa có'} số liệu ${days} ngày`} style={ui.revenueCard}>
            <View style={[ui.between, { minHeight: 28 }]}>
              <Text style={ui.revenueLabel}>Giá trị đơn hàng</Text>
              {loading ? <ActivityIndicator size="small" color={BRAND.navy} /> : null}
              {periodReady && !loading && data.change_percent !== null ? (
                <View accessibilityLabel={'Biến động ' + data.change_percent + '% so với cùng thời lượng kỳ trước'} style={ui.delta}>
                  <Ionicons name={data.change_percent >= 0 ? 'trending-up' : 'trending-down'} size={14}
                    color={data.change_percent >= 0 ? '#368368' : '#BA6159'} />
                  <Text style={[ui.deltaText, data.change_percent < 0 && { color: isDark ? '#E3A99A' : '#A96B5D' }]}>
                    {data.change_percent > 0 ? '+' : ''}{data.change_percent}%
                  </Text>
                </View>
              ) : null}
            </View>
            <Text adjustsFontSizeToFit numberOfLines={1} style={ui.revenueValue}>
              {periodReady ? count(data.order_value_vnd) : '—'}<Text style={ui.revenueUnit}> ₫</Text>
            </Text>
            {periodReady ? <SalesTrend key={data.days} data={data} /> : <View style={{ height: 215, flexShrink: 0, alignItems: 'center', justifyContent: 'center' }}><Text style={ui.loadingText}>{loading ? 'Đang lấy số liệu từ shop…' : 'Chưa lấy được số liệu kỳ này'}</Text></View>}
            <View style={ui.revenueFoot}>
              <View style={ui.grow}><Text style={ui.revenueLabel}>Đơn hợp lệ</Text><Text testID="dashboard-order-count" style={ui.revenueFootValue}>{periodReady ? count(data.order_count) : '—'}</Text></View>
              <View style={ui.grow}><Text style={ui.revenueLabel}>Trung bình mỗi đơn</Text><Text adjustsFontSizeToFit numberOfLines={1} style={ui.revenueFootValue}>{periodReady ? money(data.average_order_vnd) : '—'}</Text></View>
            </View>
          </View>
          <View style={ui.sectionHead}>
            <Text style={ui.sectionTitle}>Cần xử lý</Text>
            <Pressable accessibilityRole="button" onPress={() => onOpen({ kind: 'tasks' })} style={ui.linkHit}><Text style={ui.textLink}>Tất cả</Text></Pressable>
          </View>
          <View style={ui.grouped}>
            {tasks.map((task, index) => (
              <View key={task.label}>
                {index ? <View style={ui.separator} /> : null}
                <Pressable accessibilityRole="button" onPress={task.action} style={ui.task}>
                  <View style={ui.taskIcon}><Ionicons name={task.icon} size={19} color={BRAND.navy} /></View>
                  <Text style={ui.taskTitle}>{task.label}</Text>
                  <Text style={ui.taskCount}>{task.value === undefined ? '—' : count(task.value)}</Text>
                  <Ionicons name="chevron-forward" size={13} color={IOS.tertiary} />
                </Pressable>
              </View>
            ))}
          </View>
          <Pressable accessibilityRole="button" accessibilityLabel="Nhờ SellerPilot phân tích shop"
            onPress={() => onAsk('Phân tích tình hình shop và tư vấn việc nên ưu tiên hôm nay')} style={ui.aiCard}>
            <BrandLogo size={32} />
            <View style={ui.grow}><Text style={ui.aiTitle}>Hỏi SellerPilot</Text></View>
            <Ionicons name="arrow-forward" size={19} color={BRAND.navy} />
          </Pressable>
          {periodReady ? <OrderDistribution data={data} /> : <View style={[ui.distributionCard, { minHeight: 190, alignItems: 'center', justifyContent: 'center' }]}><Text style={ui.loadingText}>{loading ? 'Đang cập nhật trạng thái đơn…' : 'Chưa lấy được trạng thái đơn'}</Text></View>}
          <View style={ui.metricGrid}>
            <Pressable accessibilityRole="button" accessibilityLabel="Xem sản phẩm đang bán" onPress={() => onOpen({ kind: 'products' })} style={ui.metric}>
              <Text style={ui.metricLabel}>Đang bán</Text><Text style={ui.metricValue}>{count(data.active_products)}</Text><Text style={ui.caption}>sản phẩm</Text>
            </Pressable>
            <Pressable accessibilityRole="button" accessibilityLabel="Xem đánh giá Shop" onPress={() => onStore('/seller/reviews')} style={ui.metric}>
              <Text style={ui.metricLabel}>Đánh giá shop</Text><Text style={ui.metricValue}>{data.shop.rating > 0 ? data.shop.rating.toFixed(1) : '—'}<Text style={ui.caption}> / 5</Text></Text>
              <Text style={ui.caption}>{data.shop.rating > 0 ? 'Từ người mua' : 'Chưa có đánh giá'}</Text>
            </Pressable>
          </View>
          {periodReady && data.top_products.length ? (
            <>
              <View style={ui.sectionHead}>
                <Text style={ui.sectionTitle}>Sản phẩm nổi bật</Text>
                <Pressable accessibilityRole="button" onPress={() => onOpen({ kind: 'products' })} style={ui.linkHit}><Text style={ui.textLink}>Tất cả</Text></Pressable>
              </View>
              <View style={ui.grouped}>
                {data.top_products.slice(0, 3).map((product, index) => (
                  <View key={product.id}>
                    {index ? <View style={ui.separator} /> : null}
                    <Pressable accessibilityRole="button" accessibilityLabel={'Hỏi về ' + product.name}
                      onPress={() => onAsk('SKU ' + product.sku + ' còn bao nhiêu hàng?')} style={ui.productRow}>
                      <ProductThumbnail uri={product.image_url} label={'Ảnh ' + product.name} />
                      <View style={ui.grow}><Text numberOfLines={2} style={ui.productName}>{product.name}</Text><Text style={ui.productMeta}>{count(product.sold_count)} đã bán · Kho {count(product.stock)}</Text></View>
                      <Ionicons name="chevron-forward" size={14} color={IOS.tertiary} />
                    </Pressable>
                  </View>
                ))}
              </View>
            </>
          ) : null}
        </>
      ) : (
        <View style={[ui.grouped, ui.center, { minHeight: 250 }]}>
          {loading ? <ActivityIndicator color={BRAND.navy} /> : null}
          <Text style={ui.loadingText}>{loading ? 'Đang lấy số liệu từ shop…' : 'Kết nối shop để xem số liệu'}</Text>
        </View>
      )}
    </ScrollView>
  );
}
