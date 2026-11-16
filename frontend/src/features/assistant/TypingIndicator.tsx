import { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, Platform, Text, View } from 'react-native';
import { BrandLogo } from '../../components/ui/BrandLogo';
import { useTheme } from '../../theme/ThemeProvider';

export function TypingIndicator({ active = true }: { active?: boolean }) {
  const { IOS, isDark } = useTheme();
  const dots = useRef([0, 1, 2].map(() => new Animated.Value(0))).current;
  const [reduceMotion, setReduceMotion] = useState(true);
  useEffect(() => {
    let mounted = true;
    void AccessibilityInfo.isReduceMotionEnabled().then(value => { if (mounted) setReduceMotion(value); }).catch(() => {});
    const listener = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduceMotion);
    return () => { mounted = false; listener.remove(); };
  }, []);
  useEffect(() => {
    if (reduceMotion || !active) { dots.forEach(dot => dot.setValue(0)); return; }
    const animations = dots.map((dot, index) => Animated.loop(Animated.sequence([
      // Animated.delay uses a JS-driven interaction handle internally. Keep
      // pauses non-interactive too, so virtualized order rows can render.
      Animated.timing(dot, { toValue: 0, duration: 0, delay: index * 140, useNativeDriver: Platform.OS !== 'web', isInteraction: false }),
      Animated.timing(dot, { toValue: 1, duration: 280, easing: Easing.inOut(Easing.quad), useNativeDriver: Platform.OS !== 'web', isInteraction: false }),
      Animated.timing(dot, { toValue: 0, duration: 280, easing: Easing.inOut(Easing.quad), useNativeDriver: Platform.OS !== 'web', isInteraction: false }),
      Animated.timing(dot, { toValue: 0, duration: 0, delay: 540 - index * 140, useNativeDriver: Platform.OS !== 'web', isInteraction: false }),
    ])));
    animations.forEach(animation => animation.start());
    return () => animations.forEach(animation => animation.stop());
  }, [dots, reduceMotion, active]);
  return <View testID="typing-indicator" accessibilityLabel="SellerPilot đang soạn câu trả lời" accessibilityLiveRegion="polite" style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 20, marginBottom: 8 }}>
    <BrandLogo size={26} />
    <View style={{ backgroundColor: isDark ? '#24252B' : '#FFFFFF', borderRadius: 18, borderBottomLeftRadius: 5, paddingHorizontal: 17, paddingVertical: 15, flexDirection: 'row', gap: 5 }}>
      {dots.map((dot, index) => <Animated.View key={index} testID={`typing-dot-${index}`} accessible={false} style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: IOS.secondary, opacity: dot.interpolate({ inputRange: [0, 1], outputRange: [.4, 1] }), transform: [{ translateY: dot.interpolate({ inputRange: [0, 1], outputRange: [0, -4] }) }] }} />)}
    </View>
    <Text style={{ fontSize: 12, color: IOS.secondary }}>SellerPilot</Text>
  </View>;
}
