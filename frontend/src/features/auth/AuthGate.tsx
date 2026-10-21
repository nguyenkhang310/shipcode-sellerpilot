import { ReactNode, useEffect, useRef, useState } from 'react';
import { Animated, Easing, Keyboard, Platform, StyleSheet, View } from 'react-native';
import { useAuth } from './AuthProvider';
import { LoginScreen } from './LoginScreen';
import { useReducedMotion } from '../../components/layout/useReducedMotion';
import { useTheme } from '../../theme/ThemeProvider';
import { BrandIntro } from './BrandIntro';
import { BrandLogo } from '../../components/ui/BrandLogo';

export function AuthGate({ children }: { children: ReactNode }) {
  const auth = useAuth()!;
  const { isDark } = useTheme();
  const reduced = useReducedMotion();
  const motion = useRef(reduced);
  motion.current = reduced;
  const progress = useRef(new Animated.Value(0)).current;
  const previous = useRef(auth.phase);
  const current = useRef(auth.phase);
  current.current = auth.phase;
  const locked = useRef(auth.phase === 'locked');
  if (auth.phase === 'locked' || auth.phase === 'signed_out') locked.current = auth.phase === 'locked';
  const [retainLogin, setRetainLogin] = useState(true);
  const [entering, setEntering] = useState(false);
  const [intro, setIntro] = useState(true);
  const backgroundColor = isDark ? '#111315' : '#F6F6F8';

  useEffect(() => {
    const reduced = motion.current;
    const fromLogin = previous.current === 'signed_out' || previous.current === 'locked';
    previous.current = auth.phase;
    progress.stopAnimation();
    if (auth.phase !== 'signed_in') {
      progress.setValue(0); setRetainLogin(true); setEntering(false);
      return;
    }
    Keyboard.dismiss();
    setRetainLogin(fromLogin && !reduced); setEntering(!reduced);
    progress.setValue(reduced ? 1 : 0);
    const animation = Animated.sequence([
      // A short success check connects the server result with the next screen.
      // Session restoration skips it because no login form was visible.
      Animated.delay(fromLogin && !reduced ? 160 : 0),
      Animated.timing(progress, { toValue: 1, duration: reduced ? 0 : fromLogin ? 420 : 220,
        easing: Easing.out(Easing.cubic), useNativeDriver: Platform.OS !== 'web', isInteraction: false }),
    ]);
    animation.start(({ finished }) => {
      if (finished && current.current === 'signed_in') { setRetainLogin(false); setEntering(false); }
    });
    return () => animation.stop();
  }, [auth.phase, progress]);
  useEffect(() => {
    if (reduced && current.current === 'signed_in') {
      progress.stopAnimation(); progress.setValue(1); setRetainLogin(false); setEntering(false);
    }
  }, [reduced, progress]);
  const cover = { flex: 1, backgroundColor, alignItems: 'center' as const, justifyContent: 'center' as const, gap: 16 };
  const signedIn = auth.phase === 'signed_in';
  return <View testID="auth-transition" style={{ flex: 1, backgroundColor, overflow: 'hidden' }}>
    {signedIn ? <Animated.View testID="auth-protected-scene" pointerEvents={entering || retainLogin ? 'none' : 'auto'}
      style={[StyleSheet.absoluteFill, { opacity: progress, transform: [
        { translateY: progress.interpolate({ inputRange: [0, 1], outputRange: [18, 0] }) },
        { scale: progress.interpolate({ inputRange: [0, 1], outputRange: [0.99, 1] }) },
      ] }]}>{children}</Animated.View> : null}
    {auth.phase !== 'checking' && (!signedIn || retainLogin && previous.current !== 'checking') ? <Animated.View testID="auth-login-scene"
      pointerEvents={signedIn ? 'none' : 'auto'} accessibilityElementsHidden={signedIn}
      importantForAccessibility={signedIn ? 'no-hide-descendants' : 'auto'} aria-hidden={signedIn}
      style={[StyleSheet.absoluteFill, { opacity: signedIn ? progress.interpolate({ inputRange: [0, 1], outputRange: [1, 0] }) : 1,
        transform: [{ translateY: signedIn ? progress.interpolate({ inputRange: [0, 1], outputRange: [0, -14] }) : 0 }] }]}>
      <LoginScreen locked={locked.current} revealed={!intro} />
    </Animated.View> : null}
    {intro ? <BrandIntro ready={auth.phase !== 'checking'} onComplete={() => setIntro(false)} /> : null}
    {auth.privateScreen ? <View testID="privacy-screen" pointerEvents="auto" style={[cover, StyleSheet.absoluteFill]}><BrandLogo size={84} /></View> : null}
  </View>;
}
