import { Ionicons } from '@expo/vector-icons';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, FlatList, Keyboard, Pressable, RefreshControl, ScrollView, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ApiError } from '../../api/client';
import { ProductThumbnail } from '../../components/ui/ProductThumbnail';
import { getOrders } from '../../api/sellerPilot';
import { StoreOrder } from '../../api/types';
import { useTheme } from '../../theme/ThemeProvider';
import { count, money } from './formatters';
import { ORDER_STATES, orderDate } from './orderPresentation';

export function OrdersPanel({ initialStatus = 'all', embedded, active = true, onStore }: {
  initialStatus?: string; embedded: boolean; active?: boolean; onStore: (path: string) => void;
}) {
  const { ui, IOS, BRAND, isDark } = useTheme();
  const insets = useSafeAreaInsets();
  const [query, setQuery] = useState(''), [status, setStatus] = useState(initialStatus);
  const [items, setItems] = useState<StoreOrder[]>([]), [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(false), [loadingMore, setLoadingMore] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(''), [expanded, setExpanded] = useState<number | null>(null);
  const request = useRef<AbortController | null>(null), failedOffset = useRef(0);
  const list = useRef<FlatList<StoreOrder>>(null);
  const filters = useRef<ScrollView>(null);
  const chipPositions = useRef<Record<string, number>>({});
  const cacheKey = useRef(''), loadedAt = useRef(0);
  const pending = useRef(false);
  const key = status + ':' + query.trim();
  const load = useCallback(async (offset: number, pull = false) => {
    if (offset > 0 && pending.current) return;
    request.current?.abort();
    pending.current = true;
    const controller = new AbortController(); request.current = controller;
    failedOffset.current = offset; setError('');
    setLoading(offset === 0); setLoadingMore(offset > 0);
    setRefreshing(pull);
    try {
      const { data } = await getOrders(status, query.trim(), offset, controller.signal);
      if (controller.signal.aborted) return;
      setItems(previous => offset ? [...previous, ...data.items.filter(item => !previous.some(old => old.id === item.id))] : data.items);
      setTotal(data.total); cacheKey.current = key; loadedAt.current = Date.now();
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof ApiError ? e.message : 'Chưa tải được đơn hàng. Vui lòng thử lại.');
    } finally {
      if (!controller.signal.aborted) { pending.current = false; setLoading(false); setLoadingMore(false); setRefreshing(false); }
    }
  }, [status, query, key]);
  useEffect(() => { setStatus(initialStatus); }, [initialStatus]);
  useEffect(() => {
    if (!active) { request.current?.abort(); pending.current = false; setLoading(false); setLoadingMore(false); setRefreshing(false); return; }
    if (cacheKey.current !== key) {
      setItems([]); setTotal(null); setExpanded(null); setError(''); setLoading(true);
      list.current?.scrollToOffset({ offset: 0, animated: false });
    } else if (Date.now() - loadedAt.current < 60_000) return;
    const timer = setTimeout(() => void load(0), query ? 250 : 0);
    return () => { clearTimeout(timer); request.current?.abort(); };
  }, [active, key, load]);
  useEffect(() => () => request.current?.abort(), []);
  const chooseStatus = (next: string) => {
    if (next === status) return;
    Keyboard.dismiss(); setStatus(next);
    filters.current?.scrollTo({ x: Math.max(0, (chipPositions.current[next] || 0) - 22), animated: true });
  };
  const renderOrder = ({ item }: { item: StoreOrder }) => {
    const state = ORDER_STATES.find(entry => entry.key === item.status);
    const color = state ? isDark ? state.darkColor : state.color : IOS.secondary;
    const first = item.items?.[0], open = expanded === item.id;
    return <View style={ui.orderCard} testID={'order-card-' + item.id}>
      <Pressable accessibilityRole="button" accessibilityLabel={'Chi tiết đơn #' + item.id} accessibilityState={{ expanded: open }} onPress={() => { Keyboard.dismiss(); setExpanded(open ? null : item.id); }} style={({ pressed }) => [ui.orderSummary, pressed && { opacity: .7 }]}>
        <View style={ui.between}><Text style={ui.listTitle}>Đơn #{item.id}</Text><View style={[ui.orderStatus, { backgroundColor: color + '14' }]}><View style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: color }} /><Text style={{ fontSize: 12, fontWeight: '600', color }}>{state?.label || item.status}</Text></View></View>
        <View style={ui.row}>
          <ProductThumbnail uri={first?.image_url} size={48} radius={12} label={first?.name ? 'Ảnh ' + first.name : 'Ảnh sản phẩm trong đơn'} />
          <View style={ui.grow}><Text numberOfLines={1} style={ui.productName}>{item.customer_name || 'Khách hàng'}</Text><Text numberOfLines={1} style={ui.productMeta}>{first?.name || 'Đơn hàng tại shop'}</Text><Text style={[ui.productMeta, { marginTop: 3 }]}>{orderDate(item.created_at)}</Text></View>
        </View>
        <View style={ui.between}><Text style={ui.caption}>{count(item.quantity || 0)} sản phẩm</Text><View style={[ui.row, { gap: 8 }]}><Text style={ui.orderAmount}>{money(item.total_vnd)}</Text><Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={15} color={IOS.secondary} /></View></View>
      </Pressable>
      {open ? <View style={ui.orderDetail}>
        {(item.items || []).map(line => <View key={line.id} style={{ gap: 4, marginBottom: 14 }}><Text style={ui.productName}>{line.name || 'Sản phẩm không còn trong danh mục'}</Text>{line.variant_title ? <Text style={ui.caption}>{line.variant_title}</Text> : null}<View style={ui.between}><Text style={[ui.caption, ui.grow]} selectable>{line.sku || '—'}</Text><Text style={ui.caption}>{line.quantity} × {money(line.price_vnd)}</Text></View></View>)}
        {!item.items?.length ? <Text style={[ui.caption, { marginBottom: 12 }]}>Chưa có chi tiết sản phẩm.</Text> : null}
        {item.shipping_fee !== null ? <View style={ui.detailLine}><Text style={ui.caption}>Phí vận chuyển</Text><Text style={ui.productName}>{money(item.shipping_fee)}</Text></View> : null}
        {Boolean(item.discount_amount) ? <View style={ui.detailLine}><Text style={ui.caption}>Giảm giá</Text><Text style={ui.productName}>−{money(item.discount_amount!)}</Text></View> : null}
        {item.payment_method ? <View style={ui.detailLine}><Text style={ui.caption}>Thanh toán</Text><Text style={ui.productName}>{item.payment_method === 'COD' ? 'Khi nhận hàng' : item.payment_method}</Text></View> : null}
        {item.payment_status ? <View style={ui.detailLine}><Text style={ui.caption}>Trạng thái thanh toán</Text><Text style={ui.productName}>{{ paid: 'Đã thanh toán', unpaid: 'Chưa thanh toán', initiated: 'Đang xử lý', failed: 'Thất bại', cancelled: 'Đã hủy' }[item.payment_status] || item.payment_status}</Text></View> : null}
        <Pressable accessibilityRole="button" accessibilityLabel={'Xử lý đơn #' + item.id + ' trên Shopee'} onPress={() => onStore('/seller/orders/' + item.id)} style={[ui.secondaryButton, { marginTop: 10 }]}><Text style={ui.secondaryText}>Xử lý trên Shopee</Text><Ionicons name="open-outline" size={16} color={BRAND.navy} /></Pressable>
      </View> : null}
    </View>;
  };
  return <View style={{ flex: 1, minHeight: 0 }}>
    <View style={[ui.search, { marginBottom: 8, flexShrink: 0 }]}><Ionicons name="search" size={19} color={IOS.secondary} /><TextInput accessibilityLabel="Tìm đơn hàng" style={ui.searchInput} value={query} onChangeText={setQuery} placeholder="Mã đơn hoặc tên người mua" placeholderTextColor={IOS.secondary} autoCorrect={false} maxLength={200} returnKeyType="search" onSubmitEditing={Keyboard.dismiss} />{query ? <Pressable accessibilityRole="button" accessibilityLabel="Xóa tìm kiếm đơn hàng" onPress={() => setQuery('')} style={{ minWidth: 36, minHeight: 44, alignItems: 'center', justifyContent: 'center' }}><Ionicons name="close-circle" size={19} color={IOS.secondary} /></Pressable> : null}</View>
    <View testID="order-filters" style={{ flexShrink: 0, minHeight: 62, paddingBottom: 10 }}><ScrollView ref={filters} horizontal showsHorizontalScrollIndicator={false} keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingHorizontal: 22, paddingVertical: 4, gap: 8, alignItems: 'center' }} style={{ flexGrow: 0, flexShrink: 0 }}>
      {[{ key: 'all', label: 'Tất cả' }, ...ORDER_STATES].map(state => <Pressable key={state.key} accessibilityRole="button" accessibilityLabel={state.label} accessibilityState={{ selected: status === state.key }} onLayout={e => { chipPositions.current[state.key] = e.nativeEvent.layout.x; }} onPress={() => chooseStatus(state.key)} style={[ui.orderChip, state.key === status && { backgroundColor: isDark ? '#DAE5F5' : '#0B1F3F', borderColor: 'transparent' }]}><Text style={[ui.orderChipText, state.key === status && { color: isDark ? '#0B1F3F' : '#FFF' }]}>{state.label}</Text></Pressable>)}
    </ScrollView></View>
    <FlatList ref={list} testID="orders-list" data={items} keyExtractor={item => String(item.id)} renderItem={renderOrder} extraData={expanded} style={{ flex: 1 }} contentContainerStyle={[ui.sheetScroll, { paddingBottom: embedded ? 112 + insets.bottom : 24 }]} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag" initialNumToRender={8} maxToRenderPerBatch={6} windowSize={7}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(0, true)} tintColor={BRAND.navy} />}
      ListHeaderComponent={<Text style={[ui.caption, { marginBottom: 12 }]}>{total === null ? 'Đang tải đơn hàng…' : count(total) + ' đơn hàng'}</Text>}
      ListEmptyComponent={!loading && !error ? <View style={ui.center}><Ionicons name="receipt-outline" size={36} color={IOS.tertiary} /><Text style={ui.loadingText}>Không tìm thấy đơn hàng</Text></View> : null}
      ListFooterComponent={<>{error ? <View style={ui.errorCard}><Text style={ui.error}>{error}</Text><Pressable accessibilityRole="button" onPress={() => void load(failedOffset.current)} style={ui.secondaryButton}><Text style={ui.secondaryText}>Thử lại</Text></Pressable></View> : null}{loading && !items.length || loadingMore ? <ActivityIndicator color={BRAND.navy} style={{ margin: 24 }} /> : !error && total !== null && items.length < total ? <Pressable accessibilityRole="button" onPress={() => void load(items.length)} style={ui.secondaryButton}><Text style={ui.secondaryText}>Xem thêm đơn hàng</Text></Pressable> : null}</>}
    />
  </View>;
}
