import { useEffect, useState } from 'react';
import { Image, ImageProps, ImageURISource, Platform } from 'react-native';
import { API_URL, privateMediaHeaders } from '../../api/client';

/** Private draft photos use authenticated fetch; public/local images stay native. */
export function ProtectedImage(props: ImageProps) {
  const original = props.source as ImageURISource | undefined;
  const uri = original?.uri;
  const privatePhoto = Boolean(uri?.startsWith(API_URL + '/product-drafts/'));
  const [loaded, setLoaded] = useState<{ uri: string; source: string } | null>(null);
  useEffect(() => {
    if (Platform.OS !== 'web' || !privatePhoto || !uri) return;
    const controller = new AbortController(); let objectUrl: string | undefined;
    void fetch(uri, { headers: privateMediaHeaders(uri), signal: controller.signal, cache: 'no-store' })
      .then(response => { if (!response.ok) throw new Error('private_image_unavailable'); return response.blob(); })
      .then(blob => { if (!controller.signal.aborted) { objectUrl = URL.createObjectURL(blob); setLoaded({ uri, source: objectUrl }); } })
      .catch(() => {});
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [uri, privatePhoto]);
  if (!privatePhoto || !uri) return <Image {...props} />;
  const source = Platform.OS === 'web' ? (loaded?.uri === uri ? { uri: loaded.source } : undefined)
    : { ...original, headers: { ...original?.headers, ...privateMediaHeaders(uri) } };
  return <Image {...props} source={source} />;
}
