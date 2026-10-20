import { useEffect, useState } from 'react';
import { ActivityIndicator, Modal, Pressable, ScrollView, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { extensionCall } from './extension';
import { useTheme } from '../theme/ThemeProvider';

export type BrowserConnection = {id: string; mode: string; platform?: 'shopee' | 'tiktok'; target?: {label: string} | null;
  target_selection_pending?: boolean; target_matches?: boolean; document_id?: string; page_context?: string;
  tab_status: 'unlinked' | 'linked' | 'closed' | 'wrong_tab' | 'local'};
export type BrowserPage = {document_id: string; page_context: string; snapshot: {url: string; captured_at: string};
  metrics: {label: string; value: string}[]; tables: string[][][]; fields: {label: string; type: string}[]; target: {label: string};
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
  const { ui, IOS, desktop } = useTheme();
  const [connection, setConnection] = useState<BrowserConnection | null>(null);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  const [menu, setMenu] = useState(false), [scopes, setScopes] = useState<Scope[]>([]);
  const [sync, setSync] = useState<SyncStatus | null>(null);
  const platform = connection?.platform === 'tiktok' ? 'TikTok Shop' : 'Shopee';
  const linked = connection?.tab_status === 'linked';
  const matched = linked && connection?.target && connection.target_matches !== false;
  const syncError = Object.values(sync?.resources || {}).find(value => value?.error || value?.reason);
  const issue = syncError?.error || syncError?.reason;
  const syncIssue = issue ? SYNC_REASONS[issue] || issue : 'Chưa đọc đủ dữ liệu. Bấm Cập nhật để thử lại.';
  useEffect(() => {
    let alive = true, running = false, hasInitialScanned = false;
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
          if (!hasInitialScanned) {
            hasInitialScanned = true;
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
    const result = await extensionCall<{status: string}>('sync_now');
    if (['started', 'already_running'].includes(result.status)) {
      setSync({synced: false, syncing: true, status: 'running', resource: 'products', pages_read: 0, records_read: 0});
    }
  });
  const local = () => void execute(async () => {await extensionCall('bind_tab', {mode: 'local'}); location.reload();});
  const status = !connection ? 'Đang kiểm tra…' : connection.mode === 'local' ? 'Shop local'
    : !linked ? 'Chưa liên kết tài khoản' : connection.target_matches === false ? 'Kiểm tra lại tài khoản ' + platform : connection.target?.label || 'Chọn tài khoản ' + platform;
  return <View style={{paddingHorizontal: 14, paddingVertical: 8, borderBottomWidth: 1, borderColor: IOS.separator, backgroundColor: IOS.card, gap: 5}}>
    <View style={{flexDirection: 'row', alignItems: 'center', gap: 6}}>
      <Ionicons name="storefront-outline" size={16} color={IOS.secondary} />
      <Pressable accessibilityRole="button" accessibilityLabel="Cài đặt kết nối" onPress={() => {
        setMenu(true); void extensionCall<Scope[]>('list_scopes').then(setScopes).catch(() => {});
      }} style={{flex: 1, minWidth: 0, minHeight: 30, flexDirection: 'row', alignItems: 'center', gap: 5}}>
        <Text numberOfLines={1} style={[ui.caption, {fontWeight: '600', color: IOS.label, flexShrink: 1}]}>{status}</Text>
        <Ionicons name="chevron-down" size={12} color={IOS.secondary} />
      </Pressable>
      {busy || sync?.syncing ? <View style={{flexDirection: 'row', alignItems: 'center', gap: 8}}><ActivityIndicator size="small"/>{sync?.syncing ? <Pressable accessibilityRole="button" accessibilityLabel="Dừng đồng bộ" onPress={() => void execute(async () => {await extensionCall('sync_cancel');})} style={{padding: 5}}><Ionicons name="stop-circle-outline" size={19} color={IOS.secondary}/></Pressable> : null}</View> : <Pressable accessibilityRole="button" disabled={!connection} onPress={matched ? scan : choose} style={{paddingHorizontal: 8, minHeight: 30, justifyContent: 'center'}}>
        <Text style={[ui.caption, {color: IOS.blue, fontWeight: '500'}]}>{matched ? 'Cập nhật' : 'Liên kết'}</Text>
      </Pressable>}
    </View>
    {sync?.syncing ? <Text accessibilityLiveRegion="polite" style={ui.caption}>Đang đọc {sync.resource === 'products' ? 'sản phẩm' : sync.resource === 'orders' ? 'đơn hàng' : 'tổng quan'} · {sync.pages_read || 0} trang · {sync.records_read || 0} dòng</Text> : sync && ['failed', 'partial', 'interrupted'].includes(sync.status) ? <Text numberOfLines={3} style={ui.caption}>{syncIssue}</Text> : null}
    {message ? <Text accessibilityLiveRegion="polite" style={[ui.caption, {fontSize: 12, lineHeight: 17}]}>{message}</Text> : null}
    {!desktop && connection?.mode === 'shopee' ? <Text style={ui.caption}>Dữ liệu trang hiện tại · Chưa kết nối Open API</Text> : null}
    <Modal visible={menu} transparent animationType="fade" onRequestClose={() => setMenu(false)}>
      <View style={{flex: 1, backgroundColor: '#0005', justifyContent: 'center', padding: 16}}>
        <ScrollView style={{maxHeight: '90%', flexGrow: 0, width: '100%', maxWidth: 420, alignSelf: 'center', backgroundColor: IOS.card, borderRadius: 14}} contentContainerStyle={{padding: 16, gap: 10}}>
          <View style={ui.between}><Text style={ui.listTitle}>{'Kết nối ' + platform}</Text><Pressable accessibilityRole="button" accessibilityLabel="Đóng kết nối" onPress={() => setMenu(false)} style={ui.circleButton}><Ionicons name="close" size={20} color={IOS.label}/></Pressable></View>
          {connection?.target ? <Text style={ui.caption}>Tài khoản đã chọn: {connection.target.label}</Text> : null}
          <Pressable accessibilityRole="button" disabled={busy} onPress={choose} style={ui.primaryButton}><Text style={ui.primaryText}>Chọn tài khoản trên trang</Text></Pressable>
          <Text style={ui.caption}>Dùng phiên người bán bạn đã đăng nhập. Tên được chọn để kiểm tra mục tiêu, chưa phải Shop ID do API xác thực. Không đọc mật khẩu hoặc cookie.</Text>
          <Pressable accessibilityRole="button" disabled={busy} onPress={() => void execute(async () => {await extensionCall('backend_health'); setMessage('Endpoint ghép nối AI hoạt động.'); setMenu(false);})} style={ui.secondaryButton}><Text style={ui.secondaryText}>Kiểm tra backend AI</Text></Pressable>
          <Text style={ui.listTitle}>Gán ô trên form sản phẩm</Text>
          <View style={{flexDirection: 'row', flexWrap: 'wrap', gap: 6}}>{([['name', 'Tên sản phẩm'], ['description', 'Mô tả'], ['price_vnd', 'Giá bán'], ['stock', 'Tồn kho']] as const).map(([field, label]) =>
            <Pressable key={field} accessibilityRole="button" disabled={busy} onPress={() => void execute(async () => {
              await extensionCall('bind_field', {field}); setMenu(false); setMessage('Trong 30 giây, bấm ô ' + label.toLowerCase() + ' trên ' + platform + '.');
            })} style={ui.secondaryButton}><Text style={ui.secondaryText}>{label}</Text></Pressable>)}</View>
          <Text style={ui.caption}>Kiểm tra ảnh, ngành hàng và biến thể trên trang người bán. Điền form chưa phải lưu/đăng.</Text>
          {scopes.length ? <Text style={ui.listTitle}>Phiên đã lưu</Text> : null}
          {scopes.map(scope => <Pressable key={scope.id} accessibilityRole="button" disabled={busy} onPress={() => void execute(async () => {
            await extensionCall('restore_scope', {scope_id: scope.id}); location.reload();
          })} style={ui.secondaryButton}><Text style={ui.secondaryText}>{scope.mode === 'local' ? 'Shop local' : scope.target?.label || 'Phiên Shopee cũ'} · {scope.turns} cuộc trò chuyện</Text></Pressable>)}
          <Pressable accessibilityRole="button" disabled={busy} onPress={local} style={ui.secondaryButton}><Text style={ui.secondaryText}>Chuyển sang shop local</Text></Pressable>
        </ScrollView>
      </View>
    </Modal>
  </View>;
}
