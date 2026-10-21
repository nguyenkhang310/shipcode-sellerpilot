import { dockContentInset } from '../../components/layout/dockGeometry';
import { Ionicons } from '@expo/vector-icons';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, Switch, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { API_URL, ApiError } from '../../api/client';
import { ProductThumbnail } from '../../components/ui/ProductThumbnail';
import { getProducts } from '../../api/sellerPilot';
import { ManagementData, StoreProduct } from '../../api/types';
import { useTheme } from '../../theme/ThemeProvider';
import { ManagementRoute, money, count } from './DashboardScreen';
import { OrdersPanel } from './OrdersPanel';
import { ProductEditor } from './ProductEditor';
import { SecuritySettings } from '../auth/SecuritySettings';

const labels: Record<string, string> = { pending: 'Chờ xác nhận', paid: 'Chờ lấy hàng', shipped: 'Đang giao', delivered: 'Đã giao', cancelled: 'Đã hủy', returned: 'Đã hoàn hàng', active: 'Đang bán', draft: 'Bản nháp', archived: 'Đã ẩn' };
export function ManagementSheet({ route, onClose, onOpen, data, onAsk, onStore, darkMode, onDarkMode, onRefresh, embedded = false, active = true, connectionError = '', refreshing = false }: {
  route: ManagementRoute | null; onClose: () => void; onOpen: (route: ManagementRoute) => void;
  data: ManagementData | null; onAsk: (message: string) => void; onStore: (path: string) => void;
  darkMode: boolean; onDarkMode: (dark: boolean) => void; onRefresh: () => void;
  embedded?: boolean; active?: boolean; connectionError?: string; refreshing?: boolean;
}) {
  const { ui, IOS, BRAND, isDark } = useTheme();
  const insets = useSafeAreaInsets();
  const [query, setQuery] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [items, setItems] = useState<StoreProduct[]>([]);
  const [total, setTotal] = useState(0), [loading, setLoading] = useState(false), [error, setError] = useState('');
  const [retry, setRetry] = useState(0), [connectionOpen, setConnectionOpen] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const load = async (offset: number) => {
    if (!route || !['products', 'inventory'].includes(route.kind)) return;
    controller.current?.abort();
    const request = new AbortController(); controller.current = request;
    setLoading(true); setError('');
    try {
      const result = await getProducts(query, route.kind === 'inventory', offset, request.signal);
      if (request.signal.aborted) return;
      setItems(previous => offset ? [...previous, ...result.data.items.filter(item => !previous.some(old => old.id === item.id))] : result.data.items);
      setTotal(result.data.total);
    } catch (e) { if (!request.signal.aborted) setError(e instanceof ApiError ? e.message : 'Chưa kết nối được shop. Vui lòng thử lại.'); }
    finally { if (!request.signal.aborted) setLoading(false); }
  };
  useEffect(() => { setQuery(''); setItems([]); setTotal(0); setError(''); }, [route]);
  useEffect(() => { if (active && route && ['products', 'inventory'].includes(route.kind)) { setItems([]); setTotal(0); setError(''); setLoading(true); } }, [query, route?.kind, active]);
  useEffect(() => {
    if (!route || !active) { controller.current?.abort(); return; }
    const timer = setTimeout(() => { void load(0); }, query ? 250 : 0);
    return () => { clearTimeout(timer); controller.current?.abort(); };
  }, [route, query, retry, data?.updated_at, active]);
  const title = route ? { products: 'Sản phẩm', orders: 'Đơn hàng', inventory: 'Hàng sắp hết', tasks: 'Việc cần xử lý', settings: 'Shop' }[route.kind] : '';
  const isList = route && ['products', 'inventory'].includes(route.kind);
  const content = <View accessibilityViewIsModal={!embedded} style={embedded ? { flex: 1 } : [ui.sheet, { paddingBottom: Math.max(insets.bottom, 16) }]}>{!embedded ? <View style={ui.sheetHandle} /> : null}<View style={[ui.sheetHeader, { flexWrap: 'nowrap' }]}><Text accessibilityRole="header" style={[embedded ? ui.title : ui.sheetTitle, { flex: 1, minWidth: 0 }]}>{title}</Text>{!embedded ? <Pressable accessibilityRole="button" accessibilityLabel="Đóng" onPress={onClose} style={ui.circleButton}><Ionicons name="close" size={21} color={IOS.label} /></Pressable> : route?.kind === 'products' ? <Pressable accessibilityRole="button" accessibilityLabel="Đăng sản phẩm mới" onPress={() => onAsk('Đăng sản phẩm mới lên shop, giúp mình soạn tiêu đề và mô tả.')} style={[ui.circleButton, { borderRadius: 14, backgroundColor: isDark ? '#9EB9DC' : '#0B1F3F' }]}><Ionicons name="add" size={25} color={isDark ? '#0B1F3F' : '#FFF'} /></Pressable> : null}</View>
        {isList ? <View style={ui.search}><Ionicons name="search" size={19} color={IOS.secondary} /><TextInput accessibilityLabel={'Tìm sản phẩm'} style={ui.searchInput} value={query} onChangeText={setQuery} placeholder={'Tên sản phẩm hoặc SKU'} placeholderTextColor={IOS.secondary} autoCorrect={false} maxLength={200} returnKeyType="search" />{query ? <Pressable accessibilityRole="button" accessibilityLabel="Xóa tìm kiếm sản phẩm" onPress={() => setQuery('')} style={{ minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' }}><Ionicons name="close-circle" size={19} color={IOS.secondary} /></Pressable> : null}</View> : null}
        {route?.kind === 'orders' ? <OrdersPanel initialStatus={route.status} embedded={embedded} active={active} onStore={onStore} onChanged={onRefresh} /> : <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={[ui.sheetScroll, embedded && { paddingBottom: dockContentInset(insets.bottom) }]} showsVerticalScrollIndicator={false}>
          {error ? <View style={ui.errorCard}><Text style={ui.error}>{error}</Text><Pressable accessibilityRole="button" style={ui.secondaryButton} onPress={() => setRetry(value => value + 1)}><Text style={ui.secondaryText}>Thử lại</Text></Pressable></View> : null}
          {isList ? <><Text style={[ui.caption, { marginBottom: 14 }]}>{loading && !items.length ? 'Đang tải dữ liệu…' : total + ' sản phẩm'}</Text>{items.map(item => <View key={item.id} style={ui.listCard}>
            <View style={ui.row}><ProductThumbnail uri={item.image_url} size={68} radius={14} label={'Ảnh ' + item.name} /><View style={ui.grow}><Text numberOfLines={2} style={ui.productName}>{item.name}</Text><Text style={ui.productPrice}>{money(item.price_vnd)}</Text></View></View>
            <Text selectable style={[ui.productMeta, { fontSize: 12, letterSpacing: .25 }]}>SKU {item.sku}</Text><View style={[ui.between, { flexWrap: 'wrap', gap: 8 }]}><Text style={[ui.caption, { flexShrink: 1 }, item.stock <= 5 && { color: isDark ? '#EAC88E' : '#976323' }]}>{item.stock <= 5 ? 'Kho thấp · ' : 'Kho '}{count(item.stock)} · {count(item.sold_count)} đã bán</Text><View style={[ui.pill, item.status === 'active' && { backgroundColor: isDark ? '#1D362C' : '#ECF6EF' }]}><Text style={[ui.pillText, item.status === 'active' && { color: isDark ? '#99D3AD' : '#32784C' }]}>{labels[item.status] || item.status}</Text></View></View>
            <View style={[ui.row, { gap: 9 }]}><Pressable accessibilityRole="button" accessibilityLabel={'Soạn bản chỉnh sửa cho ' + item.name} onPress={() => { onClose(); onAsk('Tối ưu tiêu đề và mô tả SKU ' + item.sku + ' cho rõ ràng hơn. Giữ nguyên thông số, không thêm tính năng chưa có.'); }} style={[ui.secondaryButton, { flex: 1, paddingHorizontal: 8 }]}><Text style={[ui.secondaryText, { fontSize: 13 }]}>Gợi ý nội dung</Text></Pressable><Pressable accessibilityRole="button" accessibilityLabel={'Chỉnh sửa thủ công ' + item.name} onPress={() => setEditingId(item.id)} style={[ui.secondaryButton, { flex: 1, paddingHorizontal: 8, gap: 5, backgroundColor: BRAND.orangeSoft }]}><Ionicons name="create-outline" size={18} color={BRAND.orangeInk} /><Text style={[ui.secondaryText, { color: BRAND.orangeInk, fontSize: 13 }]}>Chỉnh sửa</Text></Pressable></View>
          </View>)}
            {loading ? <ActivityIndicator color={BRAND.navy} style={{ margin: 20 }} /> : !items.length && !error ? <Text style={[ui.loadingText, { paddingVertical: 40 }]}>Không tìm thấy kết quả</Text> : null}
            {!loading && items.length < total ? <Pressable accessibilityRole="button" onPress={() => void load(items.length)} style={ui.secondaryButton}><Text style={ui.secondaryText}>Xem thêm</Text></Pressable> : null}
          </> : null}
          {route?.kind === 'tasks' ? <>{([
            ['Đơn chờ xác nhận', data?.tasks.pending_orders, () => onOpen({ kind: 'orders', status: 'pending' })],
            ['Đơn chờ lấy hàng', data?.tasks.packing_orders, () => onOpen({ kind: 'orders', status: 'paid' })],
            ['Đơn đang giao', data?.tasks.shipping_orders, () => onOpen({ kind: 'orders', status: 'shipped' })],
            ['Sản phẩm sắp hết', data?.tasks.low_stock_products, () => onOpen({ kind: 'inventory' })],
            ['Đánh giá chưa phản hồi', data?.tasks.unanswered_reviews, () => onStore('/seller/reviews?unanswered=1')],
          ] as const).map(([label, value, action]) => <Pressable key={label} accessibilityRole="button" onPress={action} style={[ui.listCard, ui.between]}><Text style={[ui.productName, ui.grow]}>{label}</Text><Text style={ui.taskCount}>{value ?? '—'}</Text><Ionicons name="chevron-forward" size={17} color={IOS.tertiary} /></Pressable>)}</> : null}
          {route?.kind === 'settings' ? <>
            <SecuritySettings />
            <View style={ui.listCard}><Text style={ui.listTitle}>{data?.shop.name || 'Chưa kết nối shop'}</Text><View style={ui.row}><View style={[ui.dot, (!data || Boolean(connectionError)) && { backgroundColor: IOS.tertiary }]} /><Text style={ui.caption}>{connectionError ? 'Chưa đồng bộ được dữ liệu mới' : refreshing ? 'Đang đồng bộ…' : data ? 'Đã kết nối Shopee' : 'Chưa kết nối'}</Text></View><Text style={ui.caption}>{data?.shop.location || 'SellerPilot · by ShipCode'}</Text><Pressable accessibilityRole="button" onPress={() => onStore('/shop/' + (data?.shop.slug || 'utech-official'))} style={ui.secondaryButton}><Text style={ui.secondaryText}>Mở gian hàng</Text><Ionicons name="open-outline" size={16} color={BRAND.navy} /></Pressable></View>
            <View style={[ui.listCard, ui.between]}><View style={ui.row}><Ionicons name="moon-outline" size={21} color={BRAND.navy} /><Text style={ui.productName}>Giao diện tối</Text></View><Switch accessibilityLabel="Giao diện tối" value={darkMode} onValueChange={onDarkMode} trackColor={{ true: BRAND.orange, false: isDark ? '#454A54' : '#D2D8E1' }} /></View>
            <View style={ui.grouped}>{([
              ['storefront-outline', 'Kênh người bán', '/seller'],
              ['chatbubble-ellipses-outline', 'Tin nhắn khách hàng', '/seller/inbox'],
              ['star-outline', 'Đánh giá', '/seller/reviews'],
              ['ticket-outline', 'Mã giảm giá', '/seller/marketing'],
            ] as const).map(([icon, label, path], index) => <View key={path}>{index ? <View style={ui.separator} /> : null}<Pressable accessibilityRole="button" accessibilityLabel={label} onPress={() => onStore(path)} style={ui.task}><Ionicons name={icon} size={21} color={BRAND.navy} /><Text style={ui.taskTitle}>{label}</Text><Ionicons name="chevron-forward" size={16} color={IOS.secondary} /></Pressable></View>)}</View>
            {connectionError ? <View style={ui.errorCard}><Text style={ui.error}>{connectionError}</Text></View> : null}
            <Pressable accessibilityRole="button" accessibilityLabel="Đồng bộ dữ liệu" disabled={refreshing} onPress={onRefresh} style={[ui.secondaryButton, { marginTop: 18 }]}><Ionicons name="refresh-outline" size={18} color={BRAND.navy} />{refreshing ? <ActivityIndicator color={BRAND.navy} /> : null}<Text style={ui.secondaryText}>{refreshing ? 'Đang đồng bộ…' : 'Đồng bộ dữ liệu'}</Text></Pressable>
            {data ? <Text style={[ui.caption, { marginTop: 12 }]}>Cập nhật {new Date(data.updated_at).toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit' })}</Text> : null}
            <Pressable accessibilityRole="button" accessibilityState={{ expanded: connectionOpen }} onPress={() => setConnectionOpen(value => !value)} style={[ui.task, { paddingHorizontal: 0 }]}><Text style={[ui.caption, ui.grow]}>Thông tin kết nối</Text><Ionicons name={connectionOpen ? 'chevron-up' : 'chevron-down'} size={16} color={IOS.secondary} /></Pressable>{connectionOpen ? <Text selectable style={ui.caption}>{API_URL}</Text> : null}

          </> : null}
        </ScrollView>}
        <ProductEditor id={editingId} onClose={() => setEditingId(null)} onUpdated={() => { setRetry(value => value + 1); onRefresh(); }} />
      </View>;
  return embedded ? content : <Modal visible={Boolean(route)} transparent animationType="slide" onRequestClose={onClose}><KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={ui.modalOverlay}><Pressable accessibilityRole="button" accessibilityLabel="Đóng bảng quản lý" style={{ position: 'absolute', inset: 0 }} onPress={onClose} />{content}</KeyboardAvoidingView></Modal>;
}
