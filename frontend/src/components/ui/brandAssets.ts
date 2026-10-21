import { Asset } from 'expo-asset';
import { Image } from 'react-native';

// The original artwork stays intact. UI marks are sized for 20–56px icons;
// the launch animation uses its own larger rendition.
export const SHIPCODE_MARK = require('../../../assets/shipcode-mark.png');
export const SHIPCODE_INTRO = require('../../../assets/shipcode-intro.png');
let warming: Promise<void> | undefined;

export function warmBrandAssets() {
  if (!warming) warming = Promise.allSettled([SHIPCODE_MARK, SHIPCODE_INTRO].map(async source => {
    const asset = await Asset.fromModule(source).downloadAsync();
    await Image.prefetch(asset.localUri || asset.uri);
  })).then(() => {});
  return warming;
}
