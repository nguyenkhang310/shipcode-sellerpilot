import { ProtectedImage } from '../../components/ui/ProtectedImage';
import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, Text, View } from 'react-native';
import { ProductDraft } from '../../api/types';
import { productDraftImageUrl } from '../../api/sellerPilot';
import { useTheme } from '../../theme/ThemeProvider';
import { count, money } from '../dashboard/formatters';

const labels = { collecting: 'Bản nháp', ready: 'Sẵn sàng kiểm tra', filled: 'Đã điền form · Chưa đăng',
  published: 'Đã đăng · UTech Official', cancelled: 'Đã hủy bản nháp', conflict: 'Cần kiểm tra lại' };

export function ProductDraftCard({ draft, busy, saving, error, browser, onDecide }: {
  draft: ProductDraft; busy: boolean; saving: boolean; error?: string; browser: boolean;
  onDecide: (choice: 'publish' | 'cancel') => void;
}) {
  const { ui, IOS, BRAND } = useTheme();
  const [selected, setSelected] = useState(''), [expanded, setExpanded] = useState(false);
  const images = draft.status === 'cancelled' ? [] : draft.preview_urls?.length ? draft.preview_urls : draft.preview_url ? [draft.preview_url] : [];
  const preview = images.includes(selected) ? selected : images[0];
  const longDescription = Boolean(draft.description && (draft.description.length > 160 || draft.description.split('\n').length > 3));
  return <View testID="product-draft-card" style={ui.proposal}>
    {preview ? <ProtectedImage testID="draft-main-image" accessibilityLabel="Ảnh sản phẩm đang xem" source={{ uri: productDraftImageUrl(preview) }} style={ui.draftImage} resizeMode="contain" /> : null}
    {images.length > 1 ? <ScrollView testID="draft-image-gallery" horizontal style={ui.draftGalleryScroller} showsHorizontalScrollIndicator={false} contentContainerStyle={ui.draftGallery}>{images.map((uri, index) => <Pressable key={uri} accessibilityRole="button" accessibilityLabel={`Xem ảnh sản phẩm ${index + 1}`} accessibilityState={{ selected: uri === preview }} onPress={() => setSelected(uri)}><ProtectedImage source={{ uri: productDraftImageUrl(uri) }} style={[ui.draftThumbnail, { borderWidth: uri === preview ? 2 : 1, borderColor: uri === preview ? BRAND.navy : IOS.separator }]} resizeMode="cover" /></Pressable>)}</ScrollView> : null}
    <View style={ui.proposalBody}>
      <Text style={ui.proposalKicker}>{labels[draft.status]}</Text>
      <Text style={draft.name ? ui.listTitle : ui.caption}>{draft.name || 'Sản phẩm mới'}</Text>
      {draft.sku ? <Text selectable style={ui.caption}>SKU {draft.sku}</Text> : null}
      {draft.price_vnd !== null ? <Text style={ui.newPrice}>{money(draft.price_vnd)}</Text> : null}
      {draft.category_name ? <Text style={ui.caption}>{draft.category_name}</Text> : null}
      {draft.stock !== null ? <Text style={ui.caption}>Tồn kho {count(draft.stock)}</Text> : null}
      {draft.description ? <Text testID="draft-description" selectable numberOfLines={expanded ? undefined : 4} style={ui.productName}>{draft.description}</Text> : null}
      {longDescription ? <Pressable accessibilityRole="button" accessibilityState={{ expanded }} onPress={() => setExpanded(value => !value)} style={ui.linkHit}><Text style={ui.textLink}>{expanded ? 'Thu gọn mô tả' : 'Xem toàn bộ mô tả'}</Text></Pressable> : null}
      {error ? <Text accessibilityRole="alert" style={ui.error}>{error}</Text> : null}
    </View>
    {['collecting', 'ready'].includes(draft.status) ? <View style={ui.proposalActions}>
      <Pressable accessibilityRole="button" accessibilityLabel="Hủy bản nháp sản phẩm" disabled={busy} onPress={() => onDecide('cancel')} style={[ui.secondaryButton, { flex: 1, paddingHorizontal: 8 }]}><Text style={ui.secondaryText}>Hủy</Text></Pressable>
      {draft.status === 'ready' ? <Pressable accessibilityRole="button" accessibilityLabel={browser ? 'Điền bản nháp vào form người bán' : 'Đăng sản phẩm lên UTech Official'} disabled={busy} onPress={() => onDecide('publish')} style={[ui.primaryButton, { flex: 1.7, paddingHorizontal: 8 }, busy && { opacity: .55 }]}>{saving ? <ActivityIndicator color="#FFF" size="small" /> : <Ionicons name="cloud-upload-outline" size={18} color="#FFF" />}<Text style={ui.primaryText}>{browser ? 'Điền vào form' : 'Đăng sản phẩm'}</Text></Pressable> : null}
    </View> : null}
  </View>;
}
