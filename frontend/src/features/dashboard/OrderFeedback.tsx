import { Ionicons } from '@expo/vector-icons';
import { useEffect, useRef } from 'react';
import { Animated, Easing, Platform, Text } from 'react-native';
import { useTheme } from '../../theme/ThemeProvider';
import { useReducedMotion } from '../../components/layout/useReducedMotion';

export function OrderFeedback({ message, bottom }: { message: string; bottom: number }) {
  const { IOS, BRAND } = useTheme();
  const reduced = useReducedMotion(), value = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    value.setValue(0);
    const animation = Animated.timing(value, { toValue: 1, duration: reduced ? 0 : 190, easing: Easing.out(Easing.cubic), useNativeDriver: Platform.OS !== 'web', isInteraction: false });
    animation.start(); return () => animation.stop();
  }, [message, reduced, value]);
  if (!message) return null;
  return <Animated.View testID="order-feedback" pointerEvents="none" accessibilityLiveRegion="polite" style={{ position: 'absolute', left: 22, right: 22, bottom, flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: IOS.card, borderColor: BRAND.orange, borderWidth: 1, borderRadius: 16, padding: 15, opacity: value, transform: [{ translateY: value.interpolate({ inputRange: [0, 1], outputRange: [8, 0] }) }] }}><Ionicons name="checkmark-circle" size={23} color={BRAND.orangeInk} /><Text style={{ flex: 1, fontSize: 14, lineHeight: 20, color: IOS.label, fontWeight: '500' }}>{message}</Text></Animated.View>;
}
