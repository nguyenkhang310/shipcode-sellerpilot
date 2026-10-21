import { useState } from 'react';
import { StyleSheet, Text, useWindowDimensions, View } from 'react-native';

/** Avoid native auto-fit measurement during the login/scene transition. */
export function OrderValue({ value, colour, muted }: { value: string; colour: string; muted: string }) {
  const viewport = useWindowDimensions();
  const [measuredWidth, setMeasuredWidth] = useState(0);
  const width = measuredWidth || Math.max(160, Math.min(viewport.width, 600) - 40);
  const scale = Math.min(Math.max(viewport.fontScale, 1), 1.4);
  // Budget generously for system tabular digits, separators and the inline ₫.
  // Size is determined by the container, never by a transient zero text frame.
  const units = [...value].reduce((sum, char) => sum + (/\d/.test(char) ? 0.7 : 0.4), 0) + 1;
  const fontSize = Math.min(46, Math.max(20 / scale, (width - 8) / (units * scale)));
  return <View style={s.row} onLayout={event => {
    const next = event.nativeEvent.layout.width;
    if (next > 0) setMeasuredWidth(previous => Math.abs(previous - next) >= 1 ? next : previous);
  }}>
    <Text testID="dashboard-order-value" accessible accessibilityLabel={value + ' đồng'}
      numberOfLines={1} maxFontSizeMultiplier={1.4}
      style={[s.amount, { color: colour, fontSize }]}>
      {value}<Text style={{ fontSize: Math.max(12, fontSize / 2), color: muted }}>{'\u00A0₫'}</Text>
    </Text>
  </View>;
}

const s = StyleSheet.create({
  row: { width: '100%', minHeight: 64, marginTop: 6, justifyContent: 'center' },
  amount: { width: '100%', minWidth: 0, lineHeight: 64, fontWeight: '600', letterSpacing: -0.6, fontVariant: ['tabular-nums'] },
});

/** Small ledger values also need explicit sizing: web does not support RN auto-fit. */
export function MetricValue({ value, colour, testID, size = 22 }: {
  value: string; colour: string; testID?: string; size?: number;
}) {
  const { fontScale } = useWindowDimensions();
  const [width, setWidth] = useState(0);
  const scale = Math.min(Math.max(fontScale, 1), 1.4);
  const units = [...value].reduce((sum, char) => sum + (/\d/.test(char) ? 0.67 : 0.4), 0);
  const fontSize = width > 0 ? Math.min(size, Math.max(14 / scale, (width - 4) / (Math.max(units, 1) * scale))) : 14;
  const wrap = width > 0 && units * fontSize * scale > width;
  return <View style={{ flex: 1, minWidth: 0, minHeight: 48, justifyContent: 'center' }} onLayout={event => {
    const next = event.nativeEvent.layout.width;
    if (next > 0) setWidth(previous => Math.abs(previous - next) >= 1 ? next : previous);
  }}>
    <Text testID={testID} accessible accessibilityLabel={value} maxFontSizeMultiplier={1.4}
      style={{ color: colour, fontSize, lineHeight: 24, fontWeight: '600', fontVariant: ['tabular-nums'] }}>
      {wrap ? value.replaceAll('.', '.\u200B') : value}
    </Text>
  </View>;
}
