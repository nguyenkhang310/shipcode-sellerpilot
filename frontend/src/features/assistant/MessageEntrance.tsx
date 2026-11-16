import { ReactNode, useEffect, useRef } from 'react';
import { Animated, Easing, LayoutChangeEvent, Platform, StyleProp, ViewStyle } from 'react-native';

/** Opacity/translation only: message heights and the scroll anchor stay stable. */
export function MessageEntrance({ children, style, animate, reduceMotion, onLayout }: {
  children: ReactNode; style?: StyleProp<ViewStyle>; animate: boolean; reduceMotion: boolean;
  onLayout?: (event: LayoutChangeEvent) => void;
}) {
  const progress = useRef(new Animated.Value(animate && !reduceMotion ? 0 : 1)).current;
  useEffect(() => {
    if (!animate || reduceMotion) { progress.setValue(1); return; }
    const transition = Animated.timing(progress, { toValue: 1, duration: 190,
      easing: Easing.out(Easing.cubic), useNativeDriver: Platform.OS !== 'web', isInteraction: false });
    transition.start(); return () => transition.stop();
  }, [animate, reduceMotion, progress]);
  return <Animated.View onLayout={onLayout} style={[style, { opacity: progress,
    transform: [{ translateY: progress.interpolate({ inputRange: [0, 1], outputRange: [7, 0] }) }] }]}>{children}</Animated.View>;
}
