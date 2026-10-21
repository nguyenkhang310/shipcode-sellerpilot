import { Ionicons } from '@expo/vector-icons';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Keyboard, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { OrderTracking, ORDER_ACTIONS } from './OrderTracking';
import { useReducedMotion } from '../../components/layout/useReducedMotion';
import { useFormScroll } from '../../components/layout/useFormScroll';
import { useModalViewport } from '../../components/layout/useModalViewport';
import { ApiError } from '../../api/client';
import { createMessageId } from '../../api/chatRequests';
import { getOrder, updateOrder } from '../../api/sellerPilot';
import { OrderChanges, OrderDetail } from '../../api/types';
import { ProductThumbnail } from '../../components/ui/ProductThumbnail';
import { useTheme } from '../../theme/ThemeProvider';
import { money } from './formatters';
import { ORDER_STATES, orderDate } from './orderPresentation';

const fields = [
  ['shipping_name', 'Người nhận', 150], ['shipping_phone', 'Số điện thoại', 30],
  ['shipping_address', 'Địa chỉ nhận hàng', 500], ['shipping_carrier', 'Đơn vị vận chuyển', 80],
  ['tracking_number', 'Mã vận đơn', 80], ['note', 'Ghi chú', 500],
] as const;
const actions = ORDER_ACTIONS;
const statusLabel = (status: string) => ORDER_STATES.find(state => state.key === status)?.label || status;
type Form = Record<typeof fields[number][0], string>;

export function OrderEditor({ id, initialView = 'edit', onClose, onUpdated }: { id: number | null; initialView?: 'edit' | 'tracking'; onClose: () => void; onUpdated: (order: OrderDetail) => void }) {
  const { ui, IOS, BRAND } = useTheme();
  const insets = useSafeAreaInsets();
  const reduceMotion = useReducedMotion();
  const [view, setView] = useState(initialView), [discard, setDiscard] = useState(false);
  const [syncing, setSyncing] = useState(false), [syncError, setSyncError] = useState('');
  const viewportHeight = useModalViewport();
  const formScroll = useFormScroll(viewportHeight), fieldGroupY = useRef(0);
  const [order, setOrder] = useState<OrderDetail | null>(null), [loading, setLoading] = useState(false);
  const [form, setForm] = useState<Form>({ shipping_name: '', shipping_phone: '', shipping_address: '', shipping_carrier: '', tracking_number: '', note: '' });
  const [status, setStatus] = useState(''), [review, setReview] = useState(false), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [conflict, setConflict] = useState(false), [reload, setReload] = useState(0);
  const saving = useRef(false), operation = useRef<{ fingerprint: string; id: string } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setOrder(null); setError(''); setSyncError(''); setDiscard(false); setView(initialView); setConflict(false); setReview(false); operation.current = null;
    if (id === null) { setLoading(false); return; }
    setLoading(true);
    getOrder(id, controller.signal).then(({ data }) => {
      if (controller.signal.aborted) return;
      setOrder(data); setStatus(data.status);
      setForm(Object.fromEntries(fields.map(([field]) => [field, data[field] || ''])) as Form);
    }).catch(e => { if (!controller.signal.aborted) setError(e instanceof ApiError ? e.message : 'Chưa tải được chi tiết đơn hàng.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [id, reload, initialView]);
  useEffect(() => { formScroll.ref.current?.scrollTo({ y: 0, animated: false }); }, [review, view]);
  const changes: OrderChanges = {};
  if (order) {
    for (const [field] of fields) if (order.editable_fields.includes(field) && form[field] !== (order[field] || '') && form[field].trim() !== (order[field] || '')) changes[field] = form[field].trim();
    if (status !== order.status) changes.status = status as OrderChanges['status'];
  }
  const changed = Object.keys(changes).length > 0;
  useEffect(() => {
    if (id === null || !order || changed || busy || review || conflict) return;
    let alive = true, controller: AbortController | null = null;
    const refresh = async () => {
      if (controller || AppState.currentState === 'background' || AppState.currentState === 'inactive') return;
      controller = new AbortController(); setSyncing(true);
      try {
        const { data } = await getOrder(id, controller.signal);
        if (!alive) return;
        setOrder(previous => previous?.version === data.version ? previous : data); setStatus(data.status);
        setForm(Object.fromEntries(fields.map(([field]) => [field, data[field] || ''])) as Form); setSyncError('');
      } catch (e) { if (alive && !controller.signal.aborted) setSyncError(e instanceof ApiError ? e.message : 'Chưa cập nhật được trạng thái mới.'); }
      finally { controller = null; if (alive) setSyncing(false); }
    };
    const timer = setInterval(() => void refresh(), 8000);
    const listener = AppState.addEventListener('change', state => { if (state === 'active') void refresh(); });
    return () => { alive = false; clearInterval(timer); listener.remove(); controller?.abort(); setSyncing(false); };
  }, [id, Boolean(order), changed, busy, review, conflict]);
  const close = () => { if (!saving.current) { if (changed) setDiscard(true); else onClose(); } };
  const inspect = () => {
    if (!order || !changed || conflict) return;
    for (const [field, label] of fields) {
      if (!(field in changes) || field === 'note' || field === 'shipping_carrier' || field === 'tracking_number') continue;
      if (!form[field].trim() || field === 'shipping_address' && form[field].trim().length < 5) { setError('Vui lòng kiểm tra ' + label.toLowerCase() + '.'); return; }
    }
    if ('shipping_phone' in changes && (!/^\+?[\d ()-]+$/.test(form.shipping_phone.trim()) || !/^\d{8,15}$/.test(form.shipping_phone.replace(/\D/g, '')))) {
      setError('Số điện thoại cần từ 8 đến 15 chữ số.'); return;
    }
    if (('shipping_carrier' in changes || 'tracking_number' in changes) && Boolean(form.shipping_carrier.trim()) !== Boolean(form.tracking_number.trim())) { setError('Nhập cả đơn vị vận chuyển và mã vận đơn, hoặc xóa cả hai.'); return; }
    if ('tracking_number' in changes && form.tracking_number.trim() && !/^[A-Za-z0-9][A-Za-z0-9._/-]{2,79}$/.test(form.tracking_number.trim())) { setError('Mã vận đơn cần 3–80 ký tự chữ/số hoặc dấu . _ / -.'); return; }
    formScroll.blur(); Keyboard.dismiss(); setError(''); setReview(true);
  };
  const save = async () => {
    if (!order || saving.current || !changed || conflict) return;
    const fingerprint = JSON.stringify([order.version, changes]);
    if (operation.current?.fingerprint !== fingerprint) operation.current = { fingerprint, id: createMessageId() };
    saving.current = true; setBusy(true); setError('');
    try {
      const result = await updateOrder(order.id, changes, order.version, operation.current.id);
      onUpdated(result.data); onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Chưa lưu được đơn hàng. Bạn có thể thử lại.');
      if (e instanceof ApiError && e.status === 409) setConflict(true);
    } finally { saving.current = false; setBusy(false); }
  };
  return <Modal visible={id !== null} transparent animationType={reduceMotion ? 'none' : 'slide'} onRequestClose={close}>
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1, maxHeight: viewportHeight, justifyContent: 'flex-end', backgroundColor: '#00000055' }}>
      <Pressable accessibilityLabel="Đóng chi tiết đơn" onPress={close} style={{ position: 'absolute', inset: 0 }} />
      <View accessibilityViewIsModal style={{ width: '100%', maxWidth: 560, maxHeight: '94%', alignSelf: 'center', backgroundColor: IOS.card, borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingBottom: Math.max(insets.bottom, 16), overflow: 'hidden' }}>
        <View style={[ui.between, { padding: 20, flexShrink: 0, borderBottomWidth: 1, borderColor: IOS.separator }]}>
          <View style={{ flex: 1 }}><Text accessibilityRole="header" style={ui.sheetTitle}>{review ? 'Xem lại thay đổi' : 'Đơn #' + id}</Text>{order ? <Text style={ui.caption}>{statusLabel(order.status)} · Đặt {orderDate(order.created_at)}</Text> : null}</View>
          <Pressable accessibilityRole="button" accessibilityLabel="Đóng chi tiết đơn hàng" disabled={busy} onPress={close} style={ui.circleButton}><Ionicons name="close" size={22} color={IOS.label} /></Pressable>
        </View>
        {order && !review ? <View style={{ flexDirection: 'row', paddingHorizontal: 20, paddingBottom: 8, gap: 8 }}>{([['tracking', 'Theo dõi'], ['edit', 'Thông tin & xử lý']] as const).map(([key, label]) => <Pressable key={key} accessibilityRole="tab" accessibilityLabel={label} accessibilityState={{ selected: view === key }} disabled={busy || changed} onPress={() => { formScroll.blur(); Keyboard.dismiss(); setView(key); setError(''); }} style={{ flex: 1, minHeight: 44, alignItems: 'center', justifyContent: 'center', borderBottomWidth: 2, borderColor: view === key ? BRAND.orange : IOS.separator }}><Text style={{ fontSize: 14, fontWeight: view === key ? '600' : '400', color: view === key ? BRAND.orangeInk : IOS.secondary }}>{label}</Text></Pressable>)}</View> : null}
        <ScrollView ref={formScroll.ref} keyboardShouldPersistTaps="handled" style={{ flexShrink: 1, minHeight: 0 }} contentContainerStyle={{ padding: 20, gap: 20 }}>
          {loading ? <ActivityIndicator style={{ margin: 30 }} color={BRAND.navy} /> : null}
          {order && !review && view === 'tracking' ? <OrderTracking order={order} refreshing={syncing} onRefresh={() => setReload(value => value + 1)} onAction={next => { if (!order.allowed_statuses.includes(next)) return; formScroll.blur(); setStatus(next); setView('edit'); setReview(true); setError(''); }} /> : null}
          {syncError && view === 'tracking' ? <Text accessibilityRole="alert" style={ui.error}>{syncError}</Text> : null}
          {order && !review && view === 'edit' ? <>
            <View style={{ gap: 14 }}>{order.items.map(item => <View key={item.id} style={ui.row}>
              <ProductThumbnail uri={item.image_url} size={48} radius={10} label={item.name || 'Sản phẩm'} />
              <View style={ui.grow}><Text style={ui.productName}>{item.name || 'Sản phẩm không còn trong danh mục'}</Text><Text style={ui.caption}>{item.variant_title || item.sku} · {item.quantity} × {money(item.price_vnd)}</Text></View>
            </View>)}<View style={ui.between}><Text style={[ui.productName, { flexShrink: 1 }]}>Tổng thanh toán</Text><Text numberOfLines={1} adjustsFontSizeToFit style={[ui.orderAmount, { flexShrink: 1 }]}>{money(order.total_vnd)}</Text></View></View>
            <View onLayout={event => { fieldGroupY.current = event.nativeEvent.layout.y; }} style={{ gap: 14 }}>{fields.map(([field, label, maxLength]) => <View key={field} onLayout={event => formScroll.position(field, event.nativeEvent.layout.y)} style={{ gap: 7 }}><Text style={ui.caption}>{label}</Text>
              {field === 'shipping_carrier' && order.editable_fields.includes(field) && order.shipping_carriers?.length ? <ScrollView horizontal showsHorizontalScrollIndicator={false} keyboardShouldPersistTaps="handled" contentContainerStyle={{ gap: 7, paddingVertical: 3 }} style={{ flexGrow: 0 }}>{order.shipping_carriers.map(carrier => <Pressable key={carrier} accessibilityRole="button" accessibilityLabel={'Chọn ' + carrier} accessibilityState={{ selected: form.shipping_carrier === carrier }} disabled={busy} onPress={() => { setForm(previous => ({ ...previous, shipping_carrier: carrier })); setError(''); }} style={{ minHeight: 44, paddingHorizontal: 13, justifyContent: 'center', borderRadius: 12, borderWidth: 1, borderColor: form.shipping_carrier === carrier ? BRAND.orange : IOS.separator, backgroundColor: form.shipping_carrier === carrier ? BRAND.orangeSoft : IOS.card }}><Text style={{ color: form.shipping_carrier === carrier ? BRAND.orangeInk : IOS.label, fontSize: 13 }}>{carrier}</Text></Pressable>)}</ScrollView> : null}
              {order.editable_fields.includes(field) ? <TextInput autoCorrect={false} onFocus={() => formScroll.focus(field, fieldGroupY.current)} onBlur={formScroll.blur} accessibilityLabel={label} editable={!busy} value={form[field]} onChangeText={value => { setForm(previous => ({ ...previous, [field]: value })); setError(''); }} maxLength={maxLength} keyboardType={field === 'shipping_phone' ? 'phone-pad' : 'default'} multiline={field === 'note' || field === 'shipping_address'} style={{ fontSize: 16, color: IOS.label, borderWidth: 1, borderColor: IOS.separator, borderRadius: 12, padding: 13, minHeight: field === 'note' || field === 'shipping_address' ? 80 : 48, textAlignVertical: 'top' }} /> : <Text selectable style={ui.productName}>{order[field] || '—'}</Text>}
            </View>)}</View>
            {order.allowed_statuses.length ? <View style={{ gap: 8 }}><Text style={ui.caption}>Xử lý đơn hàng</Text>{order.allowed_statuses.map(next => <Pressable key={next} accessibilityRole="radio" accessibilityLabel={actions[next]} accessibilityState={{ checked: status === next }} disabled={busy} onPress={() => { setStatus(status === next ? order.status : next); setError(''); }} style={[ui.between, { minHeight: 52, padding: 13, borderRadius: 12, borderWidth: 1, borderColor: status === next ? BRAND.navy : IOS.separator }]}><Text style={[ui.productName, { flex: 1 }, next === 'cancelled' && { color: '#C44135' }]}>{actions[next]}</Text><Ionicons name={status === next ? 'radio-button-on' : 'radio-button-off'} size={21} color={next === 'cancelled' ? '#C44135' : BRAND.navy} /></Pressable>)}</View> : null}
          </> : order && review ? <View style={{ gap: 20 }}>{Object.entries(changes).map(([field, value]) => <View key={field} style={{ gap: 6 }}><Text style={ui.caption}>{field === 'status' ? 'Trạng thái' : fields.find(([key]) => key === field)?.[1]}</Text><Text style={ui.caption}>{field === 'status' ? statusLabel(order.status) : order[field as keyof Form] || '—'}</Text><Text style={ui.productName}>→ {field === 'status' ? statusLabel(String(value)) : value || 'Xóa nội dung'}</Text></View>)}{changes.status === 'cancelled' ? <Text style={ui.caption}>Hàng trong đơn sẽ được hoàn về kho. Thao tác này không thực hiện hoàn tiền qua ngân hàng.</Text> : null}</View> : null}
          {error ? <Text accessibilityRole="alert" style={ui.error}>{error}</Text> : null}
          {(conflict || !order && !loading) ? <Pressable accessibilityRole="button" onPress={() => setReload(value => value + 1)} style={ui.secondaryButton}><Text style={ui.secondaryText}>Tải lại chi tiết</Text></Pressable> : null}
        </ScrollView>
        {order && (view === 'edit' || review || discard) ? <View style={{ paddingHorizontal: 20, paddingTop: 12, flexShrink: 0, gap: 10, borderTopWidth: 1, borderColor: IOS.separator }}>
          {discard ? <><Text style={ui.productName}>Bỏ thay đổi chưa lưu của đơn này?</Text><View style={ui.row}><Pressable accessibilityRole="button" onPress={() => setDiscard(false)} style={[ui.secondaryButton, { flex: 1 }]}><Text style={ui.secondaryText}>Tiếp tục sửa</Text></Pressable><Pressable accessibilityRole="button" onPress={onClose} style={[ui.secondaryButton, { flex: 1 }]}><Text style={[ui.secondaryText, { color: IOS.red }]}>Bỏ thay đổi</Text></Pressable></View></> : <>
          {review ? <Pressable accessibilityRole="button" disabled={busy} onPress={() => { setReview(false); setError(''); }} style={ui.secondaryButton}><Text style={ui.secondaryText}>Chỉnh lại</Text></Pressable> : null}
          <Pressable accessibilityRole="button" accessibilityState={{ disabled: !changed || busy || conflict }} disabled={!changed || busy || conflict} onPress={review ? () => void save() : inspect} style={[ui.primaryButton, { opacity: !changed || conflict ? .4 : 1 }, review && changes.status === 'cancelled' && { backgroundColor: '#C44135' }]}>{busy ? <ActivityIndicator color="#FFF" /> : <Text style={ui.primaryText}>{review ? changes.status === 'cancelled' ? 'Xác nhận hủy đơn' : 'Xác nhận lưu' : 'Xem thay đổi'}</Text>}</Pressable>
          </>}
        </View> : null}
      </View>
    </KeyboardAvoidingView>
  </Modal>;
}
