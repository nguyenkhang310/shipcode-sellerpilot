import { useCallback, useRef, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { BrandLogo } from '../components/ui/BrandLogo';
import { AssistantChat, AssistantHandle } from '../features/assistant/AssistantChat';
import { useTheme } from '../theme/ThemeProvider';
import { BrowserConnection, BrowserPage, ExtensionBar } from './ExtensionBar';

const TABS = [
  {key: 'overview', title: 'Tổng quan', icon: 'grid-outline'},
  {key: 'products', title: 'Sản phẩm', icon: 'cube-outline'},
  {key: 'assistant', title: 'Trợ lý', icon: 'sparkles-outline'},
  {key: 'orders', title: 'Đơn hàng', icon: 'receipt-outline'},
  {key: 'shop', title: 'Shop', icon: 'storefront-outline'},
] as const;
type Tab = typeof TABS[number]['key'];

export function ExtensionShell() {
  const {ui, IOS, BRAND} = useTheme();
  const [tab, setTab] = useState<Tab>('assistant');
  const [connection, setConnection] = useState<BrowserConnection | null>(null);
  const [page, setPage] = useState<BrowserPage | null>(null);
  const [notice, setNotice] = useState('');
  const assistant = useRef<AssistantHandle>(null);
  const onConnection = useCallback((value: BrowserConnection) => setConnection(value), []);
  const validPage = page && connection?.tab_status === 'linked' && connection.target_matches !== false
    && (!connection.document_id || page.document_id === connection.document_id)
    && (!connection.page_context || page.page_context === connection.page_context)
    && page.target?.label === connection.target?.label ? page : null;
  const relevant = (validPage?.tables || []).filter(table => table[0]?.some(header => tab === 'orders'
    ? /^(mã đơn(?: hàng)?|order id)$/i.test(header)
    : /^(sản phẩm|tên sản phẩm|product|product name|sku|mã sku)$/i.test(header)));
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
        <Ionicons name={item.icon} size={17} color={tab === item.key ? BRAND.navy : IOS.secondary}/><Text numberOfLines={1} style={{fontSize: 11, fontWeight: tab === item.key ? '600' : '400', color: tab === item.key ? BRAND.navy : IOS.secondary}}>{item.title}</Text>
      </Pressable>)}
    </View>
    {notice ? <Pressable accessibilityRole="button" accessibilityLabel="Đóng thông báo" onPress={() => setNotice('')} style={{padding: 10, backgroundColor: IOS.card}}><Text style={ui.caption}>{notice}</Text></Pressable> : null}
    <View style={[{flex: 1, minHeight: 0}, tab !== 'assistant' && {display: 'none'}]}><AssistantChat ref={assistant} onToast={setNotice}/></View>
    {tab !== 'assistant' ? <ScrollView style={{flex: 1}} contentContainerStyle={{padding: 14, gap: 14}}>
      <View style={{gap: 4}}><Text style={{fontSize: 20, fontWeight: '600', color: IOS.label}}>{TABS.find(item => item.key === tab)?.title}</Text>
        <Text style={ui.caption}>{connection?.target?.label || 'Chưa chọn tài khoản'} · {validPage ? 'Trang đang xem' : 'Chưa đọc dữ liệu'}</Text></View>
      {tab === 'overview' ? <>
        {validPage?.metrics.length ? <View style={{flexDirection: 'row', flexWrap: 'wrap', gap: 8}}>{validPage.metrics.map(metric => <View key={metric.label} style={{width: '47%', flexGrow: 1, padding: 14, gap: 8, borderRadius: 10, backgroundColor: IOS.card, borderWidth: 1, borderColor: IOS.separator}}>
          <Text style={ui.caption}>{metric.label}</Text><Text style={{fontSize: 22, fontWeight: '600', color: IOS.label}}>{metric.value}</Text>
        </View>)}</View> : <Text style={ui.caption}>Mở trang Phân tích bán hàng trên Shopee rồi bấm Cập nhật. Chỉ hiện số liệu đọc được chắc chắn.</Text>}
        {validPage ? <Text style={ui.caption}>Cập nhật {new Date(validPage.snapshot.captured_at).toLocaleTimeString('vi-VN')} · Kỳ báo cáo theo trang Shopee, chưa xác minh tự động.</Text> : null}
        <Pressable accessibilityRole="button" onPress={() => {setTab('assistant'); assistant.current?.ask('Phân tích số liệu quan sát được trên trang hiện tại, chỉ rõ phần còn thiếu và đề xuất 3 việc ưu tiên.');}} style={ui.secondaryButton}><Text style={ui.secondaryText}>Phân tích với SellerPilot</Text></Pressable>
      </> : tab === 'shop' ? <View style={{backgroundColor: IOS.card, padding: 14, gap: 12, borderRadius: 10}}>
        <Text style={ui.listTitle}>{connection?.target?.label || 'Chưa liên kết tài khoản'}</Text>
        <Text style={ui.caption}>Liên kết trình duyệt · Chưa cấp quyền Open API</Text>
        <Text style={ui.caption}>Dữ liệu đọc: số liệu và cột sản phẩm/đơn hàng được nhận diện trên trang hiện tại. Không gửi nguyên văn trang, tên người mua, số điện thoại hay địa chỉ.</Text>
        <Text style={ui.caption}>Có thể chat, phân tích ảnh, soạn nội dung và điền form tên/mô tả/giá/tồn. Ảnh, ngành hàng, biến thể và lưu/đăng được kiểm tra trực tiếp trên Shopee.</Text>
        <Text style={ui.caption}>Kết nối độc lập bằng Shop ID và đồng bộ toàn shop cần ứng dụng Shopee Open Platform được cấp quyền.</Text>
      </View> : <>
        {relevant.length ? relevant.map((table, index) => <View key={index} style={{backgroundColor: IOS.card, borderWidth: 1, borderColor: IOS.separator, borderRadius: 10, overflow: 'hidden'}}>
          <Text style={[ui.caption, {padding: 12}]}>{Math.max(0, table.length - 1)} dòng trên trang</Text>
          <ScrollView horizontal><View>{table.map((row, rowIndex) => <View key={rowIndex} style={{flexDirection: 'row', paddingVertical: 10, borderTopWidth: 1, borderColor: IOS.separator, backgroundColor: rowIndex === 0 ? IOS.fill : IOS.card}}>{row.map((cell, cellIndex) => <Text key={cellIndex} numberOfLines={3} style={{width: cellIndex === 0 ? 180 : 125, paddingHorizontal: 12, fontSize: 12, lineHeight: 18, fontWeight: rowIndex === 0 ? '600' : '400', color: IOS.label}}>{cell || '—'}</Text>)}</View>)}</View></ScrollView>
        </View>) : <Text style={ui.caption}>Mở danh sách {tab === 'orders' ? 'đơn hàng' : 'sản phẩm'} trên Shopee rồi bấm Cập nhật. Chỉ hiển thị các cột được nhận diện; chưa đọc toàn bộ shop hoặc các trang tiếp theo.</Text>}
      </>}
    </ScrollView> : null}
  </View>;
}
