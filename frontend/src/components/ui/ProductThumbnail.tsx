import { Ionicons } from '@expo/vector-icons';
import { useEffect, useState } from 'react';
import { Image, View } from 'react-native';
import { productImageUrl } from '../../api/client';
import { useTheme } from '../../theme/ThemeProvider';

export function ProductThumbnail({ uri, size = 52, radius = 12, label = 'Ảnh sản phẩm' }: {
  uri: string | null | undefined;
  size?: number;
  radius?: number;
  label?: string;
}) {
  const { ui, IOS } = useTheme();
  const [failed, setFailed] = useState(false);
  const source = productImageUrl(uri || null);
  useEffect(() => setFailed(false), [source]);

  return <View accessibilityLabel={label} style={[ui.productImage, {
    width: size,
    height: size,
    borderRadius: radius,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
  }]}>
    {source && !failed
      ? <Image source={{ uri: source }} onError={() => setFailed(true)} style={{ width: '100%', height: '100%' }} resizeMode="cover" />
      : <Ionicons name="image-outline" size={Math.round(size * .4)} color={IOS.secondary} />}
  </View>;
}
