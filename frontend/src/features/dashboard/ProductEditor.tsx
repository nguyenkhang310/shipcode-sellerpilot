import { Ionicons } from '@expo/vector-icons';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Keyboard, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ApiError } from '../../api/client';
import { createMessageId } from '../../api/chatRequests';
import { getProduct, updateProduct } from '../../api/sellerPilot';
import { ProductChanges, ProductDetail } from '../../api/types';
import { ProductThumbnail } from '../../components/ui/ProductThumbnail';
import { useFormScroll } from '../../components/layout/useFormScroll';
import { useModalViewport } from '../../components/layout/useModalViewport';
import { useTheme } from '../../theme/ThemeProvider';
import { money, count } from './formatters';

type Form = { name: string; description: string; price_vnd: string; stock: string };
const labels = { name: 'Tên sản phẩm', description: 'Mô tả sản phẩm', price_vnd: 'Giá bán (₫)', stock: 'Tồn kho' } as const;
const readNumber = (value: string) => /^(?:\d+|\d{1,3}(?:[.,]\d{3})+)$/.test(value.trim()) ? Number(value.replace(/[.,]/g, '').trim()) : NaN;

export function ProductEditor({ id, onClose, onUpdated }: { id: number | null; onClose: () => void; onUpdated: () => void }) {
  const { ui, IOS, BRAND } = useTheme();
  const insets = useSafeAreaInsets();
  const viewportHeight = useModalViewport();
  const formScroll = useFormScroll(viewportHeight);
  const [product, setProduct] = useState<ProductDetail | null>(null), [variantId, setVariantId] = useState<number | null>(null);
  const [form, setForm] = useState<Form>({ name: '', description: '', price_vnd: '', stock: '' });
  const [loading, setLoading] = useState(false), [busy, setBusy] = useState(false), [review, setReview] = useState(false);
  const [error, setError] = useState(''), [conflict, setConflict] = useState(false), [discard, setDiscard] = useState(false), [reload, setReload] = useState(0);
  const saving = useRef(false), operation = useRef<{ fingerprint: string; id: string } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setProduct(null); setError(''); setReview(false); setConflict(false); setDiscard(false); setVariantId(null); operation.current = null;
    if (id === null) { setLoading(false); return; }
    setLoading(true);
    getProduct(id, controller.signal).then(({ data }) => {
      if (controller.signal.aborted) return;
      setProduct(data); setForm({ name: data.name, description: data.description || '', price_vnd: String(data.price_vnd), stock: String(data.stock) });
    }).catch(e => { if (!controller.signal.aborted) setError(e instanceof ApiError ? e.message : 'Chưa tải được sản phẩm.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [id, reload]);
  useEffect(() => { formScroll.ref.current?.scrollTo({ y: 0, animated: false }); }, [review]);
  const target = product?.variants.find(variant => variant.id === variantId) || product;
  const commerceEditable = Boolean(product && (!product.variants.length || variantId !== null));
  const changes: ProductChanges = {};
  if (product && target) {
    if (form.name !== product.name && form.name.trim() !== product.name) changes.name = form.name.trim();
    if (product.editable_fields.includes('description') && form.description !== (product.description || '') && form.description.trim() !== (product.description || '')) changes.description = form.description.trim();
    if (commerceEditable) {
      if (readNumber(form.price_vnd) !== target.price_vnd) changes.price_vnd = readNumber(form.price_vnd);
      if (readNumber(form.stock) !== target.stock) changes.stock = readNumber(form.stock);
    }
  }
  const changed = Object.keys(changes).length > 0;
  const close = () => { if (!saving.current) { if (changed) setDiscard(true); else onClose(); } };
  const validate = () => {
    if ('name' in changes && (form.name.trim().length < 3 || form.name.trim().length > 200)) return 'Tên sản phẩm cần từ 3 đến 200 ký tự.';
    if ('description' in changes && form.description.trim().length > 10000) return 'Mô tả không vượt quá 10.000 ký tự.';
    if ('price_vnd' in changes && (!Number.isSafeInteger(readNumber(form.price_vnd)) || readNumber(form.price_vnd) < 1000 || readNumber(form.price_vnd) > 1_000_000_000)) return 'Giá bán cần là số nguyên từ 1.000 đến 1.000.000.000 ₫.';
    if ('stock' in changes && (!Number.isSafeInteger(readNumber(form.stock)) || readNumber(form.stock) < 0 || readNumber(form.stock) > 1_000_000)) return 'Tồn kho cần là số nguyên từ 0 đến 1.000.000.';
    return '';
  };
  const inspect = () => { const issue = validate(); setError(issue); if (!issue && changed && !conflict) { formScroll.blur(); Keyboard.dismiss(); setReview(true); } };
  const save = async () => {
    if (!product || saving.current || !changed || conflict) return;
    const issue = validate(); if (issue) { setError(issue); setReview(false); return; }
    const fingerprint = JSON.stringify([product.version, variantId, changes]);
    if (operation.current?.fingerprint !== fingerprint) operation.current = { fingerprint, id: createMessageId() };
    saving.current = true; setBusy(true); setError('');
    try {
      await updateProduct(product.id, changes, product.version, operation.current.id, variantId);
      onUpdated(); onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Chưa nhận được kết quả lưu. Thử lại để kiểm tra cùng yêu cầu.');
      if (e instanceof ApiError && e.status === 409) setConflict(true);
    } finally { saving.current = false; setBusy(false); }
  };
  const beforeValue = (field: keyof Form) => field === 'name' || field === 'description' ? product?.[field] : target?.[field];
  const showValue = (key: keyof Form, value: string | number | null | undefined) => key === 'price_vnd' ? money(Number(value)) : key === 'stock' ? count(Number(value)) : value || 'Trống';
  return <Modal visible={id !== null} transparent animationType="slide" onRequestClose={close}>
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1, maxHeight: viewportHeight, justifyContent: 'flex-end', backgroundColor: '#00000055' }}>
      <Pressable accessibilityRole="button" accessibilityLabel="Đóng nền sửa sản phẩm" onPress={close} style={{ position: 'absolute', inset: 0 }} />
      <View accessibilityViewIsModal style={{ width: '100%', maxWidth: 560, maxHeight: '94%', alignSelf: 'center', backgroundColor: IOS.card, borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingBottom: Math.max(insets.bottom, 16), overflow: 'hidden' }}>
        <View style={[ui.between, { padding: 18, flexShrink: 0, borderBottomWidth: 1, borderColor: IOS.separator }]}><View style={ui.grow}><Text accessibilityRole="header" style={ui.sheetTitle}>{review ? 'Xem lại sản phẩm' : 'Sửa sản phẩm'}</Text><Text style={ui.caption}>{product?.sku || 'Đang tải chi tiết'}</Text></View><Pressable accessibilityRole="button" accessibilityLabel="Đóng sửa sản phẩm" disabled={busy} onPress={close} style={ui.circleButton}><Ionicons name="close" size={22} color={IOS.label} /></Pressable></View>
        <ScrollView ref={formScroll.ref} testID="product-editor-scroll" keyboardShouldPersistTaps="handled" style={{ flexShrink: 1, minHeight: 0 }} contentContainerStyle={{ padding: 18, gap: 18 }}>
          {loading ? <ActivityIndicator style={{ margin: 30 }} color={BRAND.navy} /> : null}
          {product ? <>
            <View style={ui.row}><ProductThumbnail uri={product.image_url} size={52} radius={12} label={product.name} /><View style={ui.grow}><Text numberOfLines={2} style={ui.productName}>{product.name}</Text><Text style={ui.caption}>{product.variants.length ? product.variants.length + ' phân loại' : 'Sản phẩm không có phân loại'}</Text></View></View>
            {!review ? <>
              {product.variants.length ? <View style={{ gap: 8 }}><Text style={ui.caption}>Chọn phân loại để sửa giá / tồn</Text>
                {[{ id: null, sku: 'Nội dung chung', title: '', is_active: true }, ...product.variants].map(variant => <Pressable key={variant.id ?? 'parent'} accessibilityRole="radio" accessibilityLabel={'Sửa ' + variant.sku} accessibilityState={{ checked: variantId === variant.id }} disabled={busy} onPress={() => {
                  if ('price_vnd' in changes || 'stock' in changes) { setError('Giá / tồn của SKU hiện tại đang được sửa. Lưu hoặc khôi phục giá trị cũ trước khi đổi phân loại.'); return; }
                  const next = product.variants.find(item => item.id === variant.id) || product;
                  setVariantId(variant.id); setForm(previous => ({ ...previous, price_vnd: String(next.price_vnd), stock: String(next.stock) })); setError('');
                }} style={[ui.between, { borderWidth: 1, borderColor: variantId === variant.id ? BRAND.orange : IOS.separator, borderRadius: 12, padding: 12, minHeight: 48 }]}><View style={ui.grow}><Text style={ui.productName}>{variant.sku}</Text>{variant.title ? <Text style={ui.caption}>{variant.title}{!variant.is_active ? ' · Đã ẩn' : ''}</Text> : null}</View><Ionicons name={variantId === variant.id ? 'radio-button-on-outline' : 'radio-button-off-outline'} size={20} color={BRAND.orangeInk} /></Pressable>)}
                <Text style={ui.caption}>Tên và mô tả dùng chung cho tất cả phân loại. Mỗi lần lưu điều chỉnh giá / tồn của một SKU.</Text>
              </View> : null}
              {(Object.keys(labels) as (keyof Form)[]).map(field => {
                const editable = product.editable_fields.includes(field) && (!['price_vnd', 'stock'].includes(field) || commerceEditable);
                return <View key={field} onLayout={event => formScroll.position(field, event.nativeEvent.layout.y)} style={{ gap: 7 }}><Text style={ui.caption}>{labels[field]}</Text>{editable ? <TextInput onFocus={() => formScroll.focus(field)} onBlur={formScroll.blur} accessibilityLabel={labels[field]} value={form[field]} editable={!busy} onChangeText={value => { setForm(previous => ({ ...previous, [field]: value })); setError(''); }} multiline={field === 'description' || field === 'name'} keyboardType={field === 'price_vnd' || field === 'stock' ? 'number-pad' : 'default'} maxLength={field === 'name' ? 200 : field === 'description' ? 10000 : 16} style={{ fontSize: 16, lineHeight: 23, color: IOS.label, borderWidth: 1, borderColor: IOS.separator, borderRadius: 12, padding: 13, minHeight: field === 'description' ? 150 : 52, maxHeight: field === 'description' ? 260 : field === 'name' ? 104 : 52, textAlignVertical: 'top' }} /> : <Text style={ui.productName}>{field === 'price_vnd' || field === 'stock' ? 'Chọn phân loại bên trên' : 'Shop chưa hỗ trợ trường này'}</Text>}</View>;
              })}
            </> : <View style={{ gap: 18 }}>
              {variantId !== null ? <Text style={ui.caption}>Phân loại: {product.variants.find(item => item.id === variantId)?.sku}</Text> : null}
              {(Object.keys(changes) as (keyof Form)[]).map(field => <View key={field} onLayout={event => formScroll.position(field, event.nativeEvent.layout.y)} style={{ gap: 7 }}><Text style={ui.caption}>{labels[field]}</Text><Text selectable style={ui.caption}>{showValue(field, beforeValue(field))}</Text><Text selectable style={ui.productName}>→ {showValue(field, changes[field])}</Text></View>)}
              {product.variants.length && ('name' in changes || 'description' in changes) ? <Text style={ui.caption}>Tên / mô tả mới áp dụng cho toàn bộ phân loại của sản phẩm.</Text> : null}
            </View>}
          </> : null}
          {error ? <Text accessibilityRole="alert" style={ui.error}>{error}</Text> : null}
          {conflict || !product && !loading ? <Pressable accessibilityRole="button" disabled={busy} onPress={() => setReload(value => value + 1)} style={ui.secondaryButton}><Text style={ui.secondaryText}>Tải lại sản phẩm</Text></Pressable> : null}
        </ScrollView>
        {product ? <View style={{ paddingHorizontal: 18, paddingTop: 12, flexShrink: 0, gap: 10, borderTopWidth: 1, borderColor: IOS.separator }}>
          {discard ? <><Text style={ui.productName}>Bỏ những thay đổi chưa lưu?</Text><View style={ui.row}><Pressable accessibilityRole="button" onPress={() => setDiscard(false)} style={[ui.secondaryButton, { flex: 1 }]}><Text style={ui.secondaryText}>Tiếp tục sửa</Text></Pressable><Pressable accessibilityRole="button" onPress={onClose} style={[ui.secondaryButton, { flex: 1 }]}><Text style={[ui.secondaryText, { color: IOS.red }]}>Bỏ thay đổi</Text></Pressable></View></> : <>
            {review ? <Pressable accessibilityRole="button" disabled={busy} onPress={() => { setReview(false); setError(''); }} style={ui.secondaryButton}><Text style={ui.secondaryText}>Chỉnh lại sản phẩm</Text></Pressable> : null}
            <Pressable accessibilityRole="button" disabled={!changed || busy || conflict} onPress={review ? () => void save() : inspect} style={[ui.primaryButton, (!changed || conflict) && { opacity: .4 }]}>{busy ? <ActivityIndicator color="#FFF" /> : <Text style={ui.primaryText}>{review ? 'Xác nhận lưu sản phẩm' : 'Xem thay đổi sản phẩm'}</Text>}</Pressable>
          </>}
        </View> : null}
      </View>
    </KeyboardAvoidingView>
  </Modal>;
}
