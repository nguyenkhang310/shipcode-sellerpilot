import { useEffect, useRef, useState } from 'react';
import { Animated, Easing, Platform, StyleSheet } from 'react-native';
import Svg, { Line, Path } from 'react-native-svg';
import { useReducedMotion } from '../../components/layout/useReducedMotion';
import { SHIPCODE_TRACES } from './shipcodeTraces';
import { SHIPCODE_INTRO } from '../../components/ui/brandAssets';
const DrawPath = Animated.createAnimatedComponent(Path);

/** One launch: trace the actual logo, reveal its colour, then open the form. */
export function BrandIntro({ ready, onComplete }: { ready: boolean; onComplete: () => void }) {
  const reduced = useReducedMotion();
  const drawing = useRef(new Animated.Value(0)).current;
  const reveal = useRef(new Animated.Value(0)).current;
  const exit = useRef(new Animated.Value(0)).current;
  const [drawn, setDrawn] = useState(false);
  const [imageReady, setImageReady] = useState(false);
  const [imageFailed, setImageFailed] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const complete = useRef(onComplete);
  complete.current = onComplete;
  useEffect(() => {
    if (reduced) { drawing.setValue(1); setDrawn(true); return; }
    // Only simplified contour paths use JS-driven SVG updates. Colour
    // reveal and zoom run separately on the native compositor, with no React
    // state updates or per-region fill animations on each frame.
    const animation = Animated.timing(drawing, { toValue: 1, duration: 1250,
      easing: Easing.inOut(Easing.quad), useNativeDriver: false, isInteraction: false });
    animation.start(({ finished }) => { if (finished) setDrawn(true); });
    return () => animation.stop();
  }, [drawing, reduced]);
  useEffect(() => {
    if (!drawn || !imageReady) return;
    const animation = Animated.sequence([
      Animated.delay(reduced ? 0 : 160),
      Animated.timing(reveal, { toValue: 1, duration: reduced ? 0 : 320,
        easing: Easing.out(Easing.cubic), useNativeDriver: Platform.OS !== 'web', isInteraction: false }),
    ]);
    animation.start(({ finished }) => { if (finished) setRevealed(true); });
    return () => animation.stop();
  }, [drawn, imageReady, reduced, reveal]);
  useEffect(() => {
    if (!ready || !revealed) return;
    if (reduced) { complete.current(); return; }
    const animation = Animated.sequence([Animated.delay(500), Animated.timing(exit, { toValue: 1, duration: 480,
      easing: Easing.inOut(Easing.cubic), useNativeDriver: Platform.OS !== 'web', isInteraction: false })]);
    animation.start(({ finished }) => { if (finished) complete.current(); });
    return () => animation.stop();
  }, [ready, revealed, reduced, exit]);

  return <Animated.View testID="auth-brand-intro" pointerEvents="auto" accessibilityElementsHidden
    importantForAccessibility="no-hide-descendants" aria-hidden style={[StyleSheet.absoluteFill, styles.cover,
      { opacity: exit.interpolate({ inputRange: [0, 0.22, 1], outputRange: [1, 1, 0] }) }]}>
    <Animated.View style={{ width: 224, height: 224, transform: [
      { scale: exit.interpolate({ inputRange: [0, 0.25, 1], outputRange: [1, 1.08, 5.5] }) },
    ] }}>
      <Animated.View testID="logo-construction" style={[StyleSheet.absoluteFill, {
        opacity: reveal.interpolate({ inputRange: [0, 1], outputRange: [0.2, 0] }),
      }]}>
        <Svg width="100%" height="100%" viewBox="0 0 320 320">
          <Line x1="0" y1="160" x2="320" y2="160" stroke="#AAB4C7" strokeWidth={0.7} strokeDasharray="3 5" />
          <Line x1="160" y1="20" x2="160" y2="300" stroke="#AAB4C7" strokeWidth={0.7} strokeDasharray="3 5" />
        </Svg>
      </Animated.View>
      <Animated.View style={[StyleSheet.absoluteFill, {
        opacity: imageFailed ? 1 : reveal.interpolate({ inputRange: [0, 1], outputRange: [1, 0] }),
      }]}>
        <Svg testID="logo-drawing" width="100%" height="100%" viewBox="0 0 320 320">
          {SHIPCODE_TRACES.map((trace, index) => <DrawPath key={index} testID={'logo-outline-' + trace.part + '-' + index} d={trace.d} fill="none"
            stroke={trace.part === 'ship' ? '#FFF4DF' : '#EAB074'} strokeWidth={index === 0 ? 1.8 : 2.2}
            strokeLinecap="round" strokeLinejoin="round" strokeDasharray={[trace.length, trace.length]}
            strokeDashoffset={drawing.interpolate({ inputRange: [0, 1], outputRange: [trace.length, 0] })} />)}
        </Svg>
      </Animated.View>
      <Animated.Image testID="logo-colour" source={SHIPCODE_INTRO} resizeMode="contain" fadeDuration={0}
        onLoad={() => setImageReady(true)} onError={() => { setImageFailed(true); setImageReady(true); }}
        style={[styles.logo, { opacity: reveal }]} />
    </Animated.View>
    <Animated.Text testID="intro-wordmark" style={styles.wordmark}>SellerPilot</Animated.Text>
  </Animated.View>;
}

const styles = StyleSheet.create({
  cover: { backgroundColor: '#111317', alignItems: 'center', justifyContent: 'center' },
  // Image's intrinsic dimensions must not escape the 224px tracing stage
  // on web. Explicit bounds also keep the native zoom centred on the artwork.
  logo: { position: 'absolute', left: 0, top: 0, width: 224, height: 224 },
  wordmark: { color: '#F7F5F1', fontSize: 26, fontWeight: '600', letterSpacing: -0.8, marginTop: 10 },
});
