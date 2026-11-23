import * as ImagePicker from 'expo-image-picker';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';

export type PendingImage = { uri: string; fileName: string; mimeType: string; base64?: string };

async function jpeg(uri: string, dimensions?: { width: number; height: number }, maxSize = 1800) {
  const context = ImageManipulator.manipulate(uri);
  if (dimensions && Math.max(dimensions.width, dimensions.height) > maxSize) {
    context.resize(dimensions.width >= dimensions.height ? { width: maxSize } : { height: maxSize });
  }
  const rendered = await context.renderAsync();
  const image = await rendered.saveAsync({ compress: .8, format: SaveFormat.JPEG, base64: true });
  if (!image.base64) throw new Error('image_base64_unavailable');
  return { uri: image.uri, base64: image.base64 };
}

export async function pickProductImages(limit: number, maxSize?: number): Promise<PendingImage[]> {
  // The system photo picker grants access to selected files. Open it directly,
  // including on the web where the dialog must follow the initiating gesture.
  const selected = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ['images'],
    allowsEditing: false,
    allowsMultipleSelection: limit > 1,
    selectionLimit: limit,
    orderedSelection: limit > 1,
    quality: .85,
  });
  if (selected.canceled) return [];
  const images = [];
  for (const [index, asset] of selected.assets.slice(0, limit).entries()) {
    images.push({
      ...await jpeg(asset.uri, asset, maxSize),
      fileName: `sellerpilot-${Date.now()}-${index + 1}.jpg`,
      mimeType: 'image/jpeg',
    });
  }
  return images;
}

export const encodeProductImage = async (image: PendingImage): Promise<PendingImage> =>
  image.base64 ? image : { ...image, ...await jpeg(image.uri) };
