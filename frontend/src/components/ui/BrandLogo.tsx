import { Image, View } from 'react-native';

const LOGO = require('../../../assets/shipcode-logo-transparent.png');

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
      <Image source={LOGO} style={{ width: size, height: size }} resizeMode="contain" fadeDuration={0} />
    </View>
  );
}
