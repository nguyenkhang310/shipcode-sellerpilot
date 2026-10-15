import { Image, View } from 'react-native';

const LOGO = require('../../../assets/shipcode-logo-app.png');

export function BrandLogo({ size = 38 }: { size?: number }) {

  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size * 0.26,
        backgroundColor: '#fff',
        borderWidth: 1,
        borderColor: '#EDEDEF',
        overflow: 'hidden',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Image source={LOGO} style={{ width: size * 0.92, height: size * 0.92 }} resizeMode="contain" fadeDuration={0} />
    </View>
  );
}
