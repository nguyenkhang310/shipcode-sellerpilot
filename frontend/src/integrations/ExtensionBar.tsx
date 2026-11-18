import { useEffect, useState } from 'react';
import { ActivityIndicator, Modal, Pressable, ScrollView, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { extensionCall } from './extension';
import { useTheme } from '../theme/ThemeProvider';

export type BrowserConnection = {id: string; mode: string; platform?: 'shopee' | 'tiktok'; target?: {label: string} | null;
  target_selection_pending?: boolean; target_matches?: boolean; target_check?: 'checking' | 'unverified' | 'matched' | 'mismatch'; document_id?: string; page_context?: string;
  tab_status: 'unlinked' | 'linked' | 'closed' | 'wrong_tab' | 'local'};
export type BrowserPage = {document_id: string; page_context: string; snapshot: {url: string; captured_at: string};
  metrics: {label: string; value: string}[]; tables: string[][][]; fields: {label: string; type: string}[]; target: {label: string};
  list_kind?: 'products' | 'orders' | 'dashboard' | null;
  inventory?: {key: string; name: string; sku: string | null; stock: string | number | null; identity_verified: boolean}[];
  coverage?: {pages_read: number; pagination_complete: boolean; reason?: string | null};
  inventory_summary?: {records_count: number; total_units: number; low_stock_count: number; out_of_stock_count: number; quantities_unknown: number}};
export type SyncStatus = {synced: boolean; syncing: boolean; status: string; resource?: string; pages_read?: number; records_read?: number;
  resources?: Record<string, {error?: string; reason?: string | null} | null>};
type Scope = {id: string; mode: string; platform?: 'shopee' | 'tiktok'; target?: {label: string}; created_at?: string; turns: number};
const SYNC_REASONS: Record<string, string> = {
  pagination_unverified: 'Chưa xác nhận được phân trang. Dữ liệu mới là một phần danh sách.',
  active_filters: 'Danh sách đang lọc. Chưa xác nhận dữ liệu ngoài bộ lọc này.',
  repeated_page: 'Trang dữ liệu bị lặp. Đã dừng để tránh tính trùng.',
  page_limit: 'Đã đạt giới hạn số trang cho một lượt đọc.',
  row_limit: 'Bảng có nhiều dòng hơn giới hạn đọc. Chưa lấy đủ dữ liệu.',
  record_limit: 'Đã đạt giới hạn số dòng cho một lượt đọc.',
};

export function ExtensionBar({onPage, onConnection}: {onPage?: (page: BrowserPage) => void; onConnection?: (value: BrowserConnection) => void}) {
  const { ui, IOS, BRAND } = useTheme();
  const [connection, setConnection] = useState<BrowserConnection | null>(null);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  const [menu, setMenu] = useState(false), [scopes, setScopes] = useState<Scope[]>([]);
  const [details, setDetails] = useState(false);
  const [sync, setSync] = useState<SyncStatus | null>(null);
  const platform = connection?.platform === 'tiktok' ? 'TikTok Shop' : 'Shopee';
  const linked = connection?.tab_status === 'linked';
  const verifying = linked && ['checking', 'unverified'].includes(connection?.target_check || '');
  const matched = linked && connection?.target && connection.target_matches !== false;
  const syncError = Object.values(sync?.resources || {}).find(value => value?.error || value?.reason);
  const issue = syncError?.error || syncError?.reason;
  const syncIssue = issue ? SYNC_REASONS[issue] || issue : 'Chưa cập nhật đủ dữ liệu.';
  useEffect(() => {
    let alive = true, running = false, lastScannedContext = '';
    async function refresh() {
      if (running) return;
      running = true;
      try {
        let value = await extensionCall<BrowserConnection>('connection_status');
        if (!alive) return;
        if (value.mode === 'shopee' && (!value.target || value.tab_status !== 'linked')) {
          const auto = await extensionCall<BrowserConnection | null>('auto_connect').catch(() => null);
          if (auto) {
            value = await extensionCall<BrowserConnection>('connection_status').catch(() => value);
          }
        }
        const scope = new URLSearchParams(location.search).get('scope');
        if (value.target && scope && value.id !== scope) {location.reload(); return;}
        setConnection(value); onConnection?.(value);
        if (value.target && value.tab_status === 'linked' && value.target_matches !== false) {
          if (value.page_context && value.page_context !== lastScannedContext) {
            lastScannedContext = value.page_context;
            extensionCall<BrowserPage>('scan').then(p => {
              if (alive && p) onPage?.(p);
            }).catch(() => {});
          }
          const status = await extensionCall<SyncStatus>('sync_status').catch(() => null);
          if (alive && status) setSync(status);
        }
        if (!value.target_selection_pending) setMessage(current => current.startsWith('Bấm tên tài khoản/') ? '' : current);
      } catch (error) {if (alive) setMessage(error instanceof Error ? error.message : 'Chưa đọc được kết nối.');}
      finally {running = false;}
    }
    void refresh();
    const timer = setInterval(() => void refresh(), 2500);
    return () => {alive = false; clearInterval(timer);};
  }, [onConnection]);
  async function execute(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setMessage('');
    try {await action();} catch (error) {setMessage(error instanceof Error ? error.message : 'Chưa thực hiện được.');}
    finally {setBusy(false);}
  }
  const choose = () => void execute(async () => {
    if (!linked || connection?.mode !== 'shopee') await extensionCall('bind_tab', {mode: 'shopee'});
    await extensionCall('select_target'); setMenu(false);
    setConnection(await extensionCall<BrowserConnection>('connection_status'));
    setMessage('Bấm tên tài khoản/shop trên thanh đầu trang ' + platform + '.');
  });
  const scan = () => void execute(async () => {
    extensionCall<BrowserPage>('scan').then(p => {
      if (p) onPage?.(p);
    }).catch(() => {});
    const result = await extensionCall<{status: string}>('sync_now');
    if (['started', 'already_running'].includes(result.status)) {
      setSync({synced: false, syncing: true, status: 'running', resource: 'products', pages_read: 0, records_read: 0});
    }
  });
  const local = () => void execute(async () => {await extensionCall('bind_tab', {mode: 'local'}); location.reload();});
  const status = !connection ? 'Đang kiểm tra…' : connection.mode === 'local' ? 'Shop local'
    : !linked ? 'Chưa liên kết tài khoản' : verifying ? connection.target?.label || 'Đang xác minh shop'
      : connection.target_matches === false ? 'Kiểm tra lại tài khoản ' + platform : connection.target?.label || 'Chọn tài khoản ' + platform;
  return <View style={{paddingHorizontal: 14, paddingTop: 2, paddingBottom: 8, backgroundColor: IOS.card, gap: 4}}>
    <View style={{flexDirection: 'row', alignItems: 'center', gap: 6}}>
      <View accessibilityLabel={matched ? 'Đã liên kết shop' : 'Chưa xác minh shop'} style={{width: 6, height: 6, borderRadius: 3, backgroundColor: matched ? IOS.green : IOS.orange, marginRight: 2}}/>
      <Pressable accessibilityRole="button" accessibilityLabel="Cài đặt kết nối" onPress={() => {
        setMenu(true); void extensionCall<Scope[]>('list_scopes').then(setScopes).catch(() => {});
      }} style={{flex: 1, minWidth: 0, minHeight: 36, flexDirection: 'row', alignItems: 'center', gap: 5}}>
        <Text numberOfLines={1} style={{fontSize: 13, lineHeight: 20, fontWeight: '500', color: IOS.label, flexShrink: 1}}>{status}</Text>
        <Ionicons name="chevron-down" size={12} color={IOS.secondary} />
      </Pressable>
      {busy || sync?.syncing ? <View style={{flexDirection: 'row', alignItems: 'center', gap: 8}}><ActivityIndicator size="small" color={BRAND.orangeInk}/>{sync?.syncing ? <Pressable accessibilityRole="button" accessibilityLabel="Dừng đồng bộ" onPress={() => void execute(async () => {await extensionCall('sync_cancel');})} style={{padding: 8}}><Ionicons name="stop-circle-outline" size={19} color={IOS.secondary}/></Pressable> : null}</View> : <Pressable accessibilityRole="button" disabled={!connection} onPress={verifying ? () => void execute(async () => {setConnection(await extensionCall<BrowserConnection>('connection_status'));}) : matched ? scan : choose} style={{paddingHorizontal: 10, minHeight: 34, borderRadius: 10, backgroundColor: BRAND.orangeSoft, justifyContent: 'center'}}>
        <Text style={[ui.caption, {color: BRAND.orangeInk, fontWeight: '600'}]}>{matched ? 'Cập nhật' : verifying ? 'Kiểm tra' : 'Liên kết'}</Text>
      </Pressable>}
    </View>
    {sync?.syncing ? <Text accessibilityLiveRegion="polite" style={ui.caption}>Đang đọc {sync.resource === 'products' ? 'sản phẩm' : sync.resource === 'orders' ? 'đơn hàng' : 'tổng quan'} · {sync.records_read || 0} dòng</Text> : sync && ['failed', 'partial', 'interrupted'].includes(sync.status) ? <Text numberOfLines={2} style={ui.caption}>{syncIssue}</Text> : null}
    {verifying ? <Text accessibilityLiveRegion="polite" style={ui.caption}>Đang xác minh shop…</Text> : null}
    {message ? <Text accessibilityLiveRegion="polite" style={[ui.caption, {fontSize: 12, lineHeight: 17}]}>{message}</Text> : null}
    <Modal visible={menu} transparent animationType="fade" onRequestClose={() => setMenu(false)}>
      <View style={{flex: 1, backgroundColor: '#0005', justifyContent: 'center', padding: 16}}>
        <ScrollView showsVerticalScrollIndicator={false} style={{maxHeight: '90%', flexGrow: 0, width: '100%', maxWidth: 420, alignSelf: 'center', backgroundColor: IOS.card, borderRadius: 22}} contentContainerStyle={{padding: 18, gap: 12}}>
          <View style={ui.between}><View style={{flex: 1, gap: 3}}><Text style={{fontSize: 20, fontWeight: '600', letterSpacing: -.4, color: IOS.label}}>Kết nối shop</Text><Text numberOfLines={1} style={ui.caption}>{connection?.target?.label || platform}</Text></View><Pressable accessibilityRole="button" accessibilityLabel="Đóng kết nối" onPress={() => setMenu(false)} style={ui.circleButton}><Ionicons name="close" size={20} color={IOS.label}/></Pressable></View>
          <Pressable accessibilityRole="button" disabled={busy} onPress={choose} style={ui.primaryButton}><Text style={ui.primaryText}>Chọn tài khoản trên trang</Text></Pressable>
          <Pressable accessibilityRole="button" disabled={busy} onPress={() => void execute(async () => {await extensionCall('backend_health'); setMessage('Kết nối AI sẵn sàng.'); setMenu(false);})} style={ui.secondaryButton}><Text style={ui.secondaryText}>Kiểm tra kết nối AI</Text></Pressable>
          <Text style={[ui.listTitle, {marginTop: 6}]}>Gán ô sản phẩm</Text>
          <View style={{flexDirection: 'row', flexWrap: 'wrap', gap: 6}}>{([['name', 'Tên sản phẩm'], ['description', 'Mô tả'], ['price_vnd', 'Giá bán'], ['stock', 'Tồn kho']] as const).map(([field, label]) =>
            <Pressable key={field} accessibilityRole="button" disabled={busy} onPress={() => void execute(async () => {
              await extensionCall('bind_field', {field}); setMenu(false); setMessage('Trong 30 giây, bấm ô ' + label.toLowerCase() + ' trên ' + platform + '.');
            })} style={[ui.secondaryButton, {width: '48%', flexGrow: 1, minWidth: 0}]}><Text style={ui.secondaryText}>{label}</Text></Pressable>)}</View>
          <Text style={ui.caption}>Điền form chưa phải đăng bán.</Text>
          {scopes.length ? <Text style={ui.listTitle}>Phiên đã lưu</Text> : null}
          {scopes.map(scope => <Pressable key={scope.id} accessibilityRole="button" disabled={busy} onPress={() => void execute(async () => {
            await extensionCall('restore_scope', {scope_id: scope.id}); location.reload();
          })} style={ui.secondaryButton}><Text style={ui.secondaryText}>{scope.mode === 'local' ? 'Shop local' : scope.target?.label || 'Phiên Shopee cũ'} · {scope.turns} cuộc trò chuyện</Text></Pressable>)}
          <Pressable accessibilityRole="button" accessibilityLabel="Thông tin kết nối" accessibilityState={{expanded: details}} onPress={() => setDetails(value => !value)} style={[ui.between, {minHeight: 40}]}><Text style={ui.caption}>Thông tin kết nối</Text><Ionicons name={details ? 'chevron-up' : 'chevron-down'} color={IOS.secondary} size={15}/></Pressable>
          {details ? <Text style={ui.caption}>{platform} · Kết nối qua trình duyệt, chưa cấp quyền Open API. Không thu thập mật khẩu hoặc cookie. Tên shop là nhãn xác minh trên trang.</Text> : null}
          <Pressable accessibilityRole="button" disabled={busy} onPress={local} style={ui.secondaryButton}><Text style={ui.secondaryText}>Dùng shop nội bộ</Text></Pressable>
        </ScrollView>
      </View>
    </Modal>
  </View>;
}
