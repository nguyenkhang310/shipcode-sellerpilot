import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
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
    let alive = true;
    if (!connection?.target || connection.target_matches === false) {setCachedPages({}); return;}
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

  useEffect(() => {
    let alive = true;
    if (connection?.target && connection.target_matches !== false) {
      if (tab === 'products' || tab === 'overview' || tab === 'orders') {
        const key = tab === 'overview' ? 'dashboard' : tab;
        extensionCall<BrowserPage | null>('get_cached_page', { page_key: key }).then(cached => {
          if (alive && cached) {
            setCachedPages(prev => ({ ...prev, [key]: cached }));
          }
        }).catch(() => {});
        extensionCall<BrowserPage>('scan').then(p => {
          if (alive && p) setPage(p);
        }).catch(() => {});
      }
    }
    return () => { alive = false; };
  }, [tab, connection?.id, connection?.target?.label, connection?.target_matches]);

  const validPage = page && connection?.tab_status === 'linked' && connection.target_matches !== false
    && (!connection.document_id || page.document_id === connection.document_id)
    && (!connection.page_context || page.page_context === connection.page_context)
    && page.target?.label === connection.target?.label ? page : null;

  const trustedConnection = connection?.tab_status === 'linked' && connection.target_matches !== false;
  const currentMetrics = trustedConnection ? (cachedPages.dashboard?.metrics || validPage?.metrics || []) : [];
  const stockPage = trustedConnection ? (cachedPages.products || (validPage?.list_kind === 'products' ? validPage : null)) : null;
  const stock = stockPage?.inventory_summary;

  const currentTables = (() => {
    if (!trustedConnection) return [];
    const filterTable = (tables: string[][][], isOrder: boolean) =>
      tables.filter(table => table[0]?.some(header => isOrder
        ? /^(?:mã đơn(?: hàng)?|order id)(?:\s*\(.*?\))?$/i.test(header.trim())
        : /^(?:sản phẩm|tên sản phẩm|thông tin sản phẩm|product|product name|sku|mã sku)(?:\s*\(.*?\))?$/i.test(header.trim()))
        && (isOrder || !table[0]?.some(header => /^(?:mã đơn(?: hàng)?|order id)(?:\s*\(.*?\))?$/i.test(header.trim()))));

    if (tab === 'orders') {
      const live = filterTable(validPage?.tables || [], true);
      if (live.length) return live;
      const cached = filterTable(cachedPages.orders?.tables || [], true);
      return cached.length ? cached : (cachedPages.orders?.tables || []);
    }
    if (tab === 'products') {
      const live = filterTable(validPage?.tables || [], false);
      if (live.length) return live;
      if (validPage?.inventory?.length) {
        return [[
          ['Tên sản phẩm', 'SKU', 'Kho hàng'],
          ...validPage.inventory.map(item => [item.name, item.sku || '—', String(item.stock ?? '—')])
        ]];
      }
      const cached = filterTable(cachedPages.products?.tables || [], false);
      if (cached.length) return cached;
      if (cachedPages.products?.inventory?.length) {
        return [[
          ['Tên sản phẩm', 'SKU', 'Kho hàng'],
          ...cachedPages.products.inventory.map(item => [item.name, item.sku || '—', String(item.stock ?? '—')])
        ]];
      }
      return cachedPages.products?.tables || [];
    }
    return [];
  })();

  const relevant = currentTables;
  const card = {backgroundColor: IOS.card, borderWidth: StyleSheet.hairlineWidth, borderColor: IOS.separator, borderRadius: 18};
  const resource = validPage && (relevant.some(table => validPage.tables?.includes(table)) || tab === 'products' && validPage.inventory?.length)
    ? validPage : tab === 'orders' ? cachedPages.orders : cachedPages.products;
  const updatedAt = cachedPages.dashboard?.snapshot.captured_at || validPage?.snapshot.captured_at;
  const platform = connection?.platform === 'tiktok' ? 'TikTok Shop' : 'Shopee';
  const button = (label: string, action: () => void, icon: 'menu-outline' | 'create-outline') =>
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={action} style={ui.circleButton}><Ionicons name={icon} size={19} color={IOS.label}/></Pressable>;
  return <View testID="extension-shell" style={{flex: 1, minHeight: 0, width: '100%', backgroundColor: IOS.bg}}>
    <View style={{height: 58, paddingHorizontal: 14, flexDirection: 'row', alignItems: 'center', gap: 9, backgroundColor: IOS.card}}>
      <BrandLogo size={34}/><Text style={{fontSize: 18, letterSpacing: -.5, fontWeight: '600', color: IOS.label, flex: 1}}>SellerPilot</Text>
      {button('Lịch sử trò chuyện', () => {setTab('assistant'); assistant.current?.openHistory();}, 'menu-outline')}
      {button('Cuộc trò chuyện mới', () => {setTab('assistant'); assistant.current?.newConversation();}, 'create-outline')}
    </View>
    <ExtensionBar onPage={setPage} onConnection={onConnection}/>
    <View accessibilityRole="tablist" style={{flexDirection: 'row', gap: 2, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: IOS.separator, backgroundColor: IOS.card, paddingHorizontal: 8, paddingBottom: 8}}>
      {TABS.map(item => <Pressable key={item.key} accessibilityRole="tab" accessibilityLabel={item.title} accessibilityState={{selected: item.key === tab}} onPress={() => setTab(item.key)} style={({pressed}) => ({flex: 1, minWidth: 0, minHeight: 50, justifyContent: 'center', paddingVertical: 7, gap: 4, borderRadius: 13, alignItems: 'center', backgroundColor: tab === item.key ? BRAND.orangeSoft : 'transparent', opacity: pressed ? .65 : 1})}>
        <InterfaceIcon name={item.icon} size={18} color={tab === item.key ? BRAND.orangeInk : IOS.secondary}/><Text numberOfLines={1} style={{fontSize: 11, lineHeight: 16, fontWeight: tab === item.key ? '600' : '500', color: tab === item.key ? BRAND.orangeInk : IOS.secondary}}>{item.title}</Text>
      </Pressable>)}
    </View>
    {notice ? <Pressable accessibilityRole="button" accessibilityLabel="Đóng thông báo" onPress={() => setNotice('')} style={{padding: 10, backgroundColor: IOS.card}}><Text style={ui.caption}>{notice}</Text></Pressable> : null}
    <View style={[{flex: 1, minHeight: 0}, tab !== 'assistant' && {display: 'none'}]}><AssistantChat ref={assistant} onToast={setNotice}/></View>
    {tab !== 'assistant' ? <ScrollView showsVerticalScrollIndicator={false} style={{flex: 1}} contentContainerStyle={{padding: 16, paddingBottom: 24, gap: 16}}>
      <Text accessibilityRole="header" style={{fontSize: 24, lineHeight: 30, letterSpacing: -.7, fontWeight: '600', color: IOS.label}}>{TABS.find(item => item.key === tab)?.title}</Text>
      {stock && ['overview', 'products'].includes(tab) ? <View style={[card, {padding: 16, gap: 14}]}>
        <View style={ui.between}><Text style={ui.listTitle}>Tồn kho</Text><Text style={[ui.caption, {color: IOS.secondary}]}>{stockPage?.coverage?.pagination_complete ? 'Đủ danh sách' : 'Một phần'}</Text></View>
        <View style={{flexDirection: 'row', gap: 12}}>{[[stock.records_count, 'Dòng hàng'], [stock.total_units, 'Tổng tồn đã biết'], [stock.low_stock_count, 'Sắp hết · ≤5']] .map(([value, label]) => <View key={String(label)} style={{flex: 1, gap: 5}}><Text style={{fontSize: 20, fontWeight: '600', color: IOS.label}}>{Number(value).toLocaleString('vi-VN')}</Text><Text style={ui.caption}>{label}</Text></View>)}</View>
        {stock.quantities_unknown ? <Text style={ui.caption}>{stock.quantities_unknown} dòng chưa xác định số tồn</Text> : null}
        <Pressable accessibilityRole="button" onPress={() => {setTab('assistant'); assistant.current?.ask('Sản phẩm nào gần hết hàng? Liệt kê SKU, số tồn và đề xuất nhập hàng.');}} style={[ui.between, {minHeight: 36, borderTopWidth: StyleSheet.hairlineWidth, borderColor: IOS.separator, paddingTop: 10}]}><Text style={{fontSize: 13, fontWeight: '500', color: BRAND.orangeInk}}>Xem hàng sắp hết</Text><Ionicons name="arrow-forward" size={17} color={BRAND.orangeInk}/></Pressable>
      </View> : null}
      {tab === 'overview' ? <>
        {currentMetrics.length ? <View style={{flexDirection: 'row', flexWrap: 'wrap', gap: 10}}>{currentMetrics.map(metric => <View key={metric.label} style={[card, {width: '46%', flexGrow: 1, padding: 16, gap: 10}]}>
          <Text style={ui.caption}>{metric.label}</Text><Text adjustsFontSizeToFit numberOfLines={1} minimumFontScale={.7} style={{fontSize: 23, lineHeight: 30, letterSpacing: -.6, fontVariant: ['tabular-nums'], fontWeight: '600', color: IOS.label}}>{metric.value}</Text>
        </View>)}</View> : <Text style={ui.caption}>Chưa có số liệu. Bấm Cập nhật để đọc trang.</Text>}
        {trustedConnection && updatedAt ? <Text style={ui.caption}>{new Date(updatedAt).toLocaleTimeString('vi-VN', {hour: '2-digit', minute: '2-digit'})} · Kỳ chưa xác minh</Text> : null}
        <Pressable accessibilityRole="button" onPress={() => {setTab('assistant'); assistant.current?.ask('Phân tích dữ liệu shop đã đồng bộ, kiểm tra hàng sắp hết và đề xuất 3 việc ưu tiên.');}} style={[ui.primaryButton, {backgroundColor: BRAND.navy}]}><Text style={[ui.primaryText, {color: IOS.card}]}>Phân tích shop</Text></Pressable>
      </> : tab === 'shop' ? <View style={[card, {overflow: 'hidden'}]}>
        <View style={{flexDirection: 'row', alignItems: 'center', gap: 12, padding: 16}}>
          <View style={{width: 42, height: 42, borderRadius: 13, backgroundColor: BRAND.orangeSoft, alignItems: 'center', justifyContent: 'center'}}><InterfaceIcon name="shop" color={BRAND.orangeInk} size={23}/></View>
          <View style={{flex: 1, gap: 4}}><Text style={ui.listTitle}>{connection?.target?.label || 'Chưa liên kết'}</Text><Text style={ui.caption}>{platform} · Trình duyệt</Text></View>
          <View accessibilityLabel={trustedConnection ? 'Đã liên kết' : 'Chưa xác minh'} style={{width: 7, height: 7, borderRadius: 4, backgroundColor: trustedConnection ? IOS.green : IOS.orange}}/>
        </View>
        {[
          ['Kết nối', trustedConnection ? 'Đã liên kết' : 'Chưa xác minh'],
          ['Cập nhật', trustedConnection && updatedAt ? new Date(updatedAt).toLocaleTimeString('vi-VN', {hour: '2-digit', minute: '2-digit'}) : '—'],
          ['Nguồn dữ liệu', 'Trang người bán'],
        ].map(([label, value]) => <View key={label} style={{paddingHorizontal: 16, minHeight: 46, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, borderTopWidth: StyleSheet.hairlineWidth, borderColor: IOS.separator}}><Text style={{fontSize: 13, color: IOS.secondary}}>{label}</Text><Text style={{fontSize: 13, fontWeight: '500', color: IOS.label}}>{value}</Text></View>)}
      </View> : <>
        {relevant.length > 4 ? <Text style={ui.caption}>Hiển thị 4 / {relevant.length} danh sách</Text> : null}
        {relevant.length ? relevant.slice(0, 4).map((table, index) => <View key={index} style={[card, {overflow: 'hidden'}]}>
          <View style={[ui.between, {padding: 14}]}><Text style={ui.caption}>{Math.min(50, Math.max(0, table.length - 1))}{table.length > 51 ? ` / ${table.length - 1}` : ''} dòng đã đọc</Text><Text style={ui.caption}>{resource?.coverage?.pagination_complete ? 'Đủ danh sách' : 'Một phần'}</Text></View>
          {table.slice(1, 51).map((row, rowIndex) => <View key={rowIndex} style={{padding: 14, gap: 8, borderTopWidth: StyleSheet.hairlineWidth, borderColor: IOS.separator}}>
            <Text selectable style={{fontSize: 14, lineHeight: 21, fontWeight: '600', color: IOS.label}}>{row[0] || '—'}</Text>
            <View style={{flexDirection: 'row', flexWrap: 'wrap', columnGap: 18, rowGap: 8}}>{row.slice(1).map((cell, cellIndex) => <View key={cellIndex} style={{minWidth: 76, maxWidth: '100%', gap: 3}}><Text style={ui.caption}>{table[0]?.[cellIndex + 1]}</Text><Text selectable style={{fontSize: 13, lineHeight: 19, color: IOS.label}}>{cell || '—'}</Text></View>)}</View>
          </View>)}
        </View>) : <Text style={ui.caption}>Chưa có dữ liệu {tab === 'orders' ? 'đơn hàng' : 'sản phẩm'}. Bấm Cập nhật để đọc trang.</Text>}
      </>}
    </ScrollView> : null}
  </View>;
}
