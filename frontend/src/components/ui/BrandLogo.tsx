import { Image, View } from 'react-native';
import { SHIPCODE_MARK } from './brandAssets';

export function BrandLogo({ size = 38 }: { size?: number }) {

  return (
    <View
      style={{
        width: size,
        height: size,
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Image accessibilityLabel="ShipCode" source={SHIPCODE_MARK} defaultSource={SHIPCODE_MARK} style={{ width: size, height: size }} resizeMode="contain" fadeDuration={0} />
    </View>
  );
}
