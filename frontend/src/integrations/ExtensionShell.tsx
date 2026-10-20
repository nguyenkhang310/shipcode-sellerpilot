import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { InterfaceIcon } from '../components/ui/InterfaceIcon';
import { BrandLogo } from '../components/ui/BrandLogo';
import { AssistantChat, AssistantHandle } from '../features/assistant/AssistantChat';
import { useTheme } from '../theme/ThemeProvider';
import { BrowserConnection, BrowserPage, ExtensionBar } from './ExtensionBar';
import { extensionCall } from './extension';

const TABS = [
  {key: 'overview', title: 'Tổng quan', icon: 'overview'},
  {key: 'products', title: 'Sản phẩm', icon: 'products'},
  {key: 'assistant', title: 'Trợ lý', icon: 'assistant'},
  {key: 'orders', title: 'Đơn hàng', icon: 'orders'},
  {key: 'shop', title: 'Shop', icon: 'shop'},
] as const;
type Tab = typeof TABS[number]['key'];

export function ExtensionShell() {
  const {ui, IOS, BRAND} = useTheme();
  const [tab, setTab] = useState<Tab>('assistant');
  const [connection, setConnection] = useState<BrowserConnection | null>(null);
  const [page, setPage] = useState<BrowserPage | null>(null);
  const [cachedPages, setCachedPages] = useState<{
    dashboard?: BrowserPage | null;
    products?: BrowserPage | null;
    orders?: BrowserPage | null;
  }>({});
  const [notice, setNotice] = useState('');
  const assistant = useRef<AssistantHandle>(null);
  const onConnection = useCallback((value: BrowserConnection) => setConnection(value), []);

  useEffect(() => {
    if (!connection?.target || connection.target_matches === false) {setCachedPages({}); return;}
    let alive = true;
    async function loadCache() {
      try {
        const [dash, prod, ord] = await Promise.all([
          extensionCall<BrowserPage | null>('get_cached_page', { page_key: 'dashboard' }).catch(() => null),
          extensionCall<BrowserPage | null>('get_cached_page', { page_key: 'products' }).catch(() => null),
          extensionCall<BrowserPage | null>('get_cached_page', { page_key: 'orders' }).catch(() => null),
        ]);
        if (alive) {
          setCachedPages({ dashboard: dash, products: prod, orders: ord });
        }
      } catch {}
    }
    void loadCache();
    const timer = setInterval(loadCache, 3000);
    return () => { alive = false; clearInterval(timer); };
  }, [connection?.id, connection?.target?.label, connection?.target_matches]);

  const validPage = page && connection?.tab_status === 'linked' && connection.target_matches !== false
    && (!connection.document_id || page.document_id === connection.document_id)
    && (!connection.page_context || page.page_context === connection.page_context)
    && page.target?.label === connection.target?.label ? page : null;

  const trustedConnection = connection?.tab_status === 'linked' && connection.target_matches !== false;
  const currentMetrics = trustedConnection ? (cachedPages.dashboard?.metrics || validPage?.metrics || []) : [];
  const stockPage = trustedConnection ? cachedPages.products : null;
  const stock = stockPage?.inventory_summary;

  const currentTables = (() => {
    if (!trustedConnection) return [];
    const filterTable = (tables: string[][][], isOrder: boolean) =>
      tables.filter(table => table[0]?.some(header => isOrder
        ? /^(mã đơn(?: hàng)?|order id)$/i.test(header)
        : /^(sản phẩm|tên sản phẩm|product|product name|sku|mã sku)$/i.test(header))
        && (isOrder || !table[0]?.some(header => /^(mã đơn(?: hàng)?|order id)$/i.test(header))));

    if (tab === 'orders') {
      const live = filterTable(validPage?.tables || [], true);
      if (live.length) return live;
      const cached = filterTable(cachedPages.orders?.tables || [], true);
      return cached.length ? cached : (cachedPages.orders?.tables || []);
    }
    if (tab === 'products') {
      const live = filterTable(validPage?.tables || [], false);
      if (live.length) return live;
      const cached = filterTable(cachedPages.products?.tables || [], false);
      return cached.length ? cached : (cachedPages.products?.tables || []);
    }
    return [];
  })();

  const relevant = currentTables;
  const button = (label: string, action: () => void, icon: 'menu-outline' | 'create-outline') =>
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={action} style={ui.circleButton}><Ionicons name={icon} size={19} color={IOS.label}/></Pressable>;
  return <View testID="extension-shell" style={{flex: 1, minHeight: 0, width: '100%', backgroundColor: IOS.bg}}>
    <View style={{height: 52, paddingHorizontal: 14, flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: IOS.card, borderBottomWidth: 1, borderColor: IOS.separator}}>
      <BrandLogo size={28}/><Text style={{fontSize: 15, fontWeight: '600', color: IOS.label, flex: 1}}>SellerPilot</Text>
      {button('Lịch sử trò chuyện', () => {setTab('assistant'); assistant.current?.openHistory();}, 'menu-outline')}
      {button('Cuộc trò chuyện mới', () => {setTab('assistant'); assistant.current?.newConversation();}, 'create-outline')}
    </View>
    <ExtensionBar onPage={setPage} onConnection={onConnection}/>
    <View accessibilityRole="tablist" style={{flexDirection: 'row', borderBottomWidth: 1, borderColor: IOS.separator, backgroundColor: IOS.card, paddingHorizontal: 6}}>
      {TABS.map(item => <Pressable key={item.key} accessibilityRole="tab" accessibilityLabel={item.title} accessibilityState={{selected: item.key === tab}} onPress={() => setTab(item.key)} style={{flex: 1, minWidth: 0, paddingVertical: 10, gap: 4, alignItems: 'center', borderBottomWidth: 2, borderColor: tab === item.key ? BRAND.navy : 'transparent'}}>
        <InterfaceIcon name={item.icon} size={17} color={tab === item.key ? BRAND.navy : IOS.secondary}/><Text numberOfLines={1} style={{fontSize: 11, fontWeight: tab === item.key ? '600' : '400', color: tab === item.key ? BRAND.navy : IOS.secondary}}>{item.title}</Text>
      </Pressable>)}
    </View>
    {notice ? <Pressable accessibilityRole="button" accessibilityLabel="Đóng thông báo" onPress={() => setNotice('')} style={{padding: 10, backgroundColor: IOS.card}}><Text style={ui.caption}>{notice}</Text></Pressable> : null}
    <View style={[{flex: 1, minHeight: 0}, tab !== 'assistant' && {display: 'none'}]}><AssistantChat ref={assistant} onToast={setNotice}/></View>
    {tab !== 'assistant' ? <ScrollView style={{flex: 1}} contentContainerStyle={{padding: 14, gap: 14}}>
      <View style={{gap: 4}}><Text style={{fontSize: 20, fontWeight: '600', color: IOS.label}}>{TABS.find(item => item.key === tab)?.title}</Text>
        <Text style={ui.caption}>{connection?.target?.label || 'Chưa chọn tài khoản'} · {validPage ? 'Trang đang xem' : (tab === 'overview' && currentMetrics.length) || (tab !== 'overview' && tab !== 'shop' && relevant.length) ? 'Dữ liệu đã thu thập từ Shopee' : 'Chưa đọc dữ liệu'}</Text></View>
      {stock && ['overview', 'products'].includes(tab) ? <View style={{padding: 14, gap: 10, borderRadius: 10, backgroundColor: IOS.card, borderWidth: 1, borderColor: IOS.separator}}>
        <View style={ui.between}><Text style={ui.listTitle}>Tồn kho</Text><Text style={ui.caption}>{stockPage?.coverage?.pages_read || 1} trang · {stockPage?.coverage?.pagination_complete ? 'Đã đọc hết danh sách' : 'Chưa đọc đủ'}</Text></View>
        <View style={{flexDirection: 'row', gap: 12}}>{[[stock.records_count, 'Dòng hàng'], [stock.total_units, 'Tổng tồn đã biết'], [stock.low_stock_count, 'Sắp hết · ≤5']] .map(([value, label]) => <View key={String(label)} style={{flex: 1, gap: 5}}><Text style={{fontSize: 20, fontWeight: '600', color: IOS.label}}>{Number(value).toLocaleString('vi-VN')}</Text><Text style={ui.caption}>{label}</Text></View>)}</View>
        {stock.quantities_unknown ? <Text style={ui.caption}>{stock.quantities_unknown} dòng chưa xác định số tồn</Text> : null}
        <Pressable accessibilityRole="button" onPress={() => {setTab('assistant'); assistant.current?.ask('Sản phẩm nào gần hết hàng? Liệt kê SKU, số tồn và đề xuất nhập hàng.');}} style={ui.secondaryButton}><Text style={ui.secondaryText}>Xem hàng sắp hết với SellerPilot</Text></Pressable>
      </View> : null}
      {tab === 'overview' ? <>
        {currentMetrics.length ? <View style={{flexDirection: 'row', flexWrap: 'wrap', gap: 8}}>{currentMetrics.map(metric => <View key={metric.label} style={{width: '47%', flexGrow: 1, padding: 14, gap: 8, borderRadius: 10, backgroundColor: IOS.card, borderWidth: 1, borderColor: IOS.separator}}>
          <Text style={ui.caption}>{metric.label}</Text><Text style={{fontSize: 22, fontWeight: '600', color: IOS.label}}>{metric.value}</Text>
        </View>)}</View> : <Text style={ui.caption}>Chưa có số liệu tổng quan. Bấm Cập nhật để tự thu thập từ Shopee.</Text>}
        {trustedConnection && (validPage || cachedPages.dashboard) ? <Text style={ui.caption}>Cập nhật {new Date(cachedPages.dashboard?.snapshot.captured_at || validPage!.snapshot.captured_at).toLocaleTimeString('vi-VN')} · Kỳ báo cáo chưa xác minh tự động.</Text> : null}
        <Pressable accessibilityRole="button" onPress={() => {setTab('assistant'); assistant.current?.ask('Phân tích dữ liệu shop đã đồng bộ, kiểm tra hàng sắp hết và đề xuất 3 việc ưu tiên.');}} style={ui.secondaryButton}><Text style={ui.secondaryText}>Phân tích với SellerPilot</Text></Pressable>
      </> : tab === 'shop' ? <View style={{backgroundColor: IOS.card, padding: 14, gap: 12, borderRadius: 10}}>
        <Text style={ui.listTitle}>{connection?.target?.label || 'Chưa liên kết tài khoản'}</Text>
        <Text style={ui.caption}>Liên kết trình duyệt · Chưa cấp quyền Open API</Text>
        <Text style={ui.caption}>Tự đọc số liệu và danh sách sản phẩm/đơn hàng qua các trang nhận diện được trong tab nền. Không gửi nguyên văn trang, tên người mua, số điện thoại hay địa chỉ.</Text>
        <Text style={ui.caption}>Có thể chat, phân tích ảnh, soạn nội dung và điền form tên/mô tả/giá/tồn. Ảnh, ngành hàng, biến thể và lưu/đăng được kiểm tra trực tiếp trên Shopee.</Text>
        <Text style={ui.caption}>Kết nối độc lập bằng Shop ID và đồng bộ toàn shop cần ứng dụng Shopee Open Platform được cấp quyền.</Text>
      </View> : <>
        {relevant.length ? <Text style={ui.caption}>Xem trước tối đa 4 bảng, 50 dòng mỗi bảng. AI dùng toàn bộ dữ liệu đã đọc để tính tồn.</Text> : null}
        {relevant.length ? relevant.slice(0, 4).map((table, index) => <View key={index} style={{backgroundColor: IOS.card, borderWidth: 1, borderColor: IOS.separator, borderRadius: 10, overflow: 'hidden'}}>
          <Text style={[ui.caption, {padding: 12}]}>{Math.max(0, table.length - 1)} dòng đã đọc</Text>
          <ScrollView horizontal><View>{table.slice(0, 51).map((row, rowIndex) => <View key={rowIndex} style={{flexDirection: 'row', paddingVertical: 10, borderTopWidth: 1, borderColor: IOS.separator, backgroundColor: rowIndex === 0 ? IOS.fill : IOS.card}}>{row.map((cell, cellIndex) => <Text key={cellIndex} numberOfLines={3} style={{width: cellIndex === 0 ? 180 : 125, paddingHorizontal: 12, fontSize: 12, lineHeight: 18, fontWeight: rowIndex === 0 ? '600' : '400', color: IOS.label}}>{cell || '—'}</Text>)}</View>)}</View></ScrollView>
        </View>) : <Text style={ui.caption}>Chưa có dữ liệu {tab === 'orders' ? 'đơn hàng' : 'sản phẩm'}. Bấm Cập nhật để tự đọc danh sách.</Text>}
      </>}
    </ScrollView> : null}
  </View>;
}
