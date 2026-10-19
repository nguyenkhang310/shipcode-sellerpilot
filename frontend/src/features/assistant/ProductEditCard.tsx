import { useState } from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { ProductEditProposal } from '../../api/types';
import { useTheme } from '../../theme/ThemeProvider';
import { money, count } from '../dashboard/formatters';

const labels = { name: 'Tiêu đề', description: 'Mô tả', price_vnd: 'Giá bán', stock: 'Tồn kho' };
const status = { pending: 'Xem trước thay đổi', executing: 'Đang đối chiếu với shop', approved: 'Đã cập nhật trên shop', rejected: 'Đã bỏ qua', conflict: 'Dữ liệu đã đổi · Cần tạo đề xuất mới' };

export function ProductEditCard({ proposal, busy, error, onDecide }: {
  proposal: ProductEditProposal; busy: boolean; error?: string;
  onDecide: (choice: 'confirm' | 'reject') => void;
}) {
  const { ui, IOS, BRAND } = useTheme();
  const [expanded, setExpanded] = useState(false);
  const format = (field: string, value: string | number | null) => value === null || value === '' ? 'Chưa có' :
    field === 'price_vnd' ? money(Number(value)) : field === 'stock' ? count(Number(value)) + ' sản phẩm' : String(value);
  const hasLongText = proposal.changes.some(change => String(change.before ?? '').length > 180 || String(change.after).length > 180);
  return <View style={ui.proposal}>
    <View style={ui.proposalBody}>
      <Text style={ui.proposalKicker}>{status[proposal.status]}</Text>
      <Text style={ui.listTitle}>{proposal.product_name}</Text>
      <Text style={ui.caption}>SKU {proposal.sku}</Text>
      {proposal.shared_content ? <Text style={[ui.caption, { marginTop: 7 }]}>Tiêu đề và mô tả dùng chung cho các phân loại.</Text> : null}
      {proposal.changes.map(change => <View key={change.field} style={{ paddingTop: 15, gap: 6 }}>
        <Text style={[ui.productName, { fontWeight: '600' }]}>{labels[change.field]}</Text>
        <Text numberOfLines={expanded ? undefined : 3} style={[ui.caption, { color: IOS.secondary }]}>Hiện tại: {format(change.field, change.before)}</Text>
        <View style={{ borderLeftWidth: 2, borderColor: BRAND.gold, paddingLeft: 10 }}>
          <Text selectable numberOfLines={expanded ? undefined : 5} style={[ui.productName, { lineHeight: 23 }]}>{format(change.field, change.after)}</Text>
        </View>
      </View>)}
      {hasLongText ? <Pressable accessibilityRole="button" accessibilityState={{ expanded }} onPress={() => setExpanded(value => !value)} style={{ minHeight: 44, justifyContent: 'center' }}><Text style={ui.textLink}>{expanded ? 'Thu gọn' : 'Xem toàn bộ nội dung'}</Text></Pressable> : null}
      {error ? <Text style={ui.error}>{error}</Text> : null}
    </View>
    {proposal.status === 'pending' || proposal.status === 'executing' ? <View style={ui.proposalActions}>
      {proposal.status === 'pending' ? <Pressable accessibilityRole="button" disabled={busy} onPress={() => onDecide('reject')} style={[ui.secondaryButton, { flex: 1 }]}><Text style={ui.secondaryText}>Bỏ qua</Text></Pressable> : null}
      <Pressable accessibilityRole="button" accessibilityLabel={'Xác nhận sửa sản phẩm SKU ' + proposal.sku} disabled={busy} onPress={() => onDecide('confirm')} style={[ui.primaryButton, { flex: 1.6 }, busy && { opacity: .55 }]}>
        {busy ? <ActivityIndicator color="#FFF" /> : <Ionicons name="checkmark" size={18} color="#FFF" />}<Text style={ui.primaryText}>{proposal.status === 'executing' ? 'Kiểm tra lại kết quả' : 'Xác nhận sửa'}</Text>
      </Pressable>
    </View> : null}
  </View>;
}
