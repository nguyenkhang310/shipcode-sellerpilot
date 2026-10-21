import { ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  Easing,
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Defs, LinearGradient, Stop, Rect } from 'react-native-svg';
import { useAuth } from './AuthProvider';
import { useModalViewport } from '../../components/layout/useModalViewport';
import { useReducedMotion } from '../../components/layout/useReducedMotion';
import { useTheme } from '../../theme/ThemeProvider';

const SHIPCODE_LOGO = require('../../../assets/shipcode-logo-transparent.png');

export function LoginScreen() {
  const auth = useAuth()!,
    insets = useSafeAreaInsets();
  const { isDark } = useTheme();
  const s = useMemo(() => createStyles(isDark), [isDark]);
  const { width, height } = useWindowDimensions();
  const reduceMotion = useReducedMotion();
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [loginFocused, setLoginFocused] = useState(false);
  const [passwordFocused, setPasswordFocused] = useState(false);

  const passwordField = useRef<TextInput>(null);
  const viewportHeight = useModalViewport();
  const locked = auth.phase === 'locked';
  const wide = width >= 880;
  const compact = (viewportHeight ?? height) < 740;

  /* ── Figma Animations: spin orbit (7s), dashed ring (40s), hover float (6s), glow breathe (4s) ── */
  const orbitAnim = useRef(new Animated.Value(0)).current;
  const dashedAnim = useRef(new Animated.Value(0)).current;
  const floatAnim = useRef(new Animated.Value(0)).current;
  const glowAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (reduceMotion) {
      orbitAnim.setValue(0); dashedAnim.setValue(0); floatAnim.setValue(0); glowAnim.setValue(0);
      return;
    }
    const animations = [Animated.loop(
      Animated.timing(orbitAnim, { toValue: 1, duration: 7000, easing: Easing.linear, useNativeDriver: true })
    ),
    Animated.loop(
      Animated.timing(dashedAnim, { toValue: 1, duration: 40000, easing: Easing.linear, useNativeDriver: true })
    ),
    Animated.loop(
      Animated.sequence([
        Animated.timing(floatAnim, { toValue: -7, duration: 3000, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
        Animated.timing(floatAnim, { toValue: 0, duration: 3000, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
      ])
    ),
    Animated.loop(
      Animated.sequence([
        Animated.timing(glowAnim, { toValue: 1, duration: 2000, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
        Animated.timing(glowAnim, { toValue: 0, duration: 2000, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
      ])
    )];
    animations.forEach(animation => animation.start());
    return () => animations.forEach(animation => animation.stop());
  }, [reduceMotion, orbitAnim, dashedAnim, floatAnim, glowAnim]);

  const orbitRotate = orbitAnim.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });
  const dashedRotate = dashedAnim.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });
  const glowScale = glowAnim.interpolate({ inputRange: [0, 1], outputRange: [1, 1.12] });
  const glowOpacity = glowAnim.interpolate({ inputRange: [0, 1], outputRange: [0.35, 0.6] });

  // The API accepts existing seller usernames (including "utech") or email.
  const validLogin = Boolean(login.trim());
  const validPassword = Boolean(password);
  const clientError = submitted
    ? !validLogin
      ? 'Nhập email hoặc tên đăng nhập của bạn.'
      : !validPassword
      ? 'Nhập mật khẩu của bạn.'
      : ''
    : '';

  const displayError = clientError || auth.error;

  const handleSubmit = () => {
    setSubmitted(true);
    if (!validLogin || !validPassword || auth.busy) return;
    void auth.signIn(login, password);
  };

  return (
    <KeyboardAvoidingView
      testID="login-screen"
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={[s.login, { maxHeight: viewportHeight }]}
    >
      {/* ── login-bg: 3 auroras + streaks ── */}
      <View pointerEvents="none" style={s.loginBg}>
        <View style={s.aurora1} />
        <View style={s.aurora2} />
        <View style={s.aurora3} />
        <View style={[s.streak, { top: '16%' }]} />
        <View style={[s.streak, { top: '31%', width: 90 }]} />
        <View style={[s.streak, { top: '44%', width: 180 }]} />
      </View>

      <ScrollView
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        contentContainerStyle={[
          s.scrollBody,
          wide ? s.scrollBodyWide : s.scrollBodyMobile,
          {
            paddingTop: Math.max(insets.top + (wide ? 32 : 24), 24),
            paddingBottom: Math.max(insets.bottom + 14, 20),
            paddingHorizontal: wide ? 40 : width < 360 ? 20 : 26,
          },
        ]}
      >
        {/* ═══════════ .login-hero ═══════════ */}
        <View style={[s.loginHero, wide && s.loginHeroWide, !wide && compact && { minHeight: 190, paddingVertical: 8 }]}>
          <View style={[s.loginEmblem, wide && s.loginEmblemWide, !wide && compact && { width: 150, height: 150 }]}>
            {/* Dashed outer ring: .login-emblem:before */}
            <Animated.View
              style={[
                s.emblemDashed,
                {
                  transform: [{ rotate: dashedRotate }],
                },
              ]}
            />

            {/* Glowing radial core: .login-emblem:after */}
            <Animated.View
              style={[
                s.emblemGlow,
                {
                  opacity: glowOpacity,
                  transform: [{ scale: glowScale }],
                },
              ]}
            />

            {/* Orbit with glowing bead: .orbit */}
            <Animated.View
              style={[
                s.orbitRing,
                {
                  transform: [{ rotate: orbitRotate }],
                },
              ]}
            >
              <View style={s.orbitBead} />
            </Animated.View>

            {/* Floating Logo: .login-logo */}
            <Animated.View
              style={[
                s.logoContainer,
                {
                  transform: [{ translateY: floatAnim }],
                },
              ]}
            >
              <Image
                source={SHIPCODE_LOGO}
                style={s.loginLogo}
                resizeMode="contain"
              />
            </Animated.View>
          </View>

          {/* .login-wordmark: —— SellerPilot —— */}
          <View style={s.loginWordmark}>
            <Svg width={28} height={1} style={{ marginRight: 12 }}>
              <Defs>
                <LinearGradient id="wmLineL" x1="0" y1="0" x2="28" y2="0" gradientUnits="userSpaceOnUse">
                  <Stop offset="0" stopColor="#ffb800" stopOpacity="0" />
                  <Stop offset="1" stopColor="#ffb800" stopOpacity="0.8" />
                </LinearGradient>
              </Defs>
              <Rect width={28} height={1} fill="url(#wmLineL)" />
            </Svg>

            <Text style={[s.wordmarkText, wide && { fontSize: 30 }]}>
              Seller<Text style={{ color: isDark ? '#FFD377' : '#9F4517', fontWeight: '700' }}>Pilot</Text>
            </Text>

            <Svg width={28} height={1} style={{ marginLeft: 12 }}>
              <Defs>
                <LinearGradient id="wmLineR" x1="0" y1="0" x2="28" y2="0" gradientUnits="userSpaceOnUse">
                  <Stop offset="0" stopColor="#ffb800" stopOpacity="0.8" />
                  <Stop offset="1" stopColor="#ffb800" stopOpacity="0" />
                </LinearGradient>
              </Defs>
              <Rect width={28} height={1} fill="url(#wmLineR)" />
            </Svg>
          </View>
          <Text style={s.heroCaption}>Gian hàng của bạn. Mọi việc trong tầm tay.</Text>
        </View>

        {/* ═══════════ .login-card ═══════════ */}
        <View style={[s.loginCard, wide && s.loginCardWide]}>
          {locked ? (
            /* Biometric Unlock Mode */
            <View style={{ alignItems: 'center', gap: 14 }}>
              <Text accessibilityRole="header" style={s.loginTitle}>Chào mừng trở lại</Text>
              <Text style={s.lockedDesc}>
                Mở khóa phiên làm việc an toàn với {auth.capability.label}
              </Text>
              {auth.error ? <Text accessibilityRole="alert" accessibilityLiveRegion="polite" style={s.loginError}>{auth.error}</Text> : null}

              <Pressable
                accessibilityRole="button"
                accessibilityLabel={'Mở khóa bằng ' + auth.capability.label}
                disabled={auth.busy || !auth.capability.available}
                onPress={() => void auth.unlock()}
                style={({ pressed }) => [
                  s.loginSubmit,
                  {
                    opacity: auth.busy || !auth.capability.available ? 0.5 : pressed ? 0.92 : 1,
                    transform: [{ scale: pressed ? 0.98 : 1 }],
                  },
                ]}
              >
                {auth.busy ? (
                  <ActivityIndicator color="#0b1f3f" />
                ) : (
                  <>
                    <Ionicons name="scan-outline" size={20} color="#0b1f3f" />
                    <Text style={s.submitText}>Mở khóa bằng {auth.capability.label}</Text>
                  </>
                )}
              </Pressable>

              <Pressable
                accessibilityRole="button"
                disabled={auth.busy}
                onPress={auth.usePassword}
                style={({ pressed }) => [{ opacity: pressed ? 0.6 : 1, minHeight: 44, justifyContent: 'center' }]}
              >
                <Text style={{ color: isDark ? '#FFD377' : '#9F4517', fontSize: 14, fontWeight: '600' }}>
                  Dùng mật khẩu tài khoản
                </Text>
              </Pressable>
            </View>
          ) : (
            /* Standard Login Mode (Exact Figma layout) */
            <View>
              <Text accessibilityRole="header" style={s.loginTitle}>Đăng nhập</Text>
              <Text style={s.formCaption}>Tiếp tục công việc của bạn.</Text>

              {/* .login-group */}
              <View style={[s.loginGroup, Boolean(displayError) && s.loginGroupInvalid]}>
                {/* Row 1: Email / phone */}
                <View style={[s.loginRow, loginFocused && s.loginRowFocused]}>
                  <View style={s.loginField}>
                    <Text style={[s.fieldLabel, loginFocused && s.fieldLabelFocused]}>
                      Email hoặc tên đăng nhập
                    </Text>
                    <TextInput
                      accessibilityLabel="Email hoặc tên đăng nhập"
                      value={login}
                      editable={!auth.busy}
                      onChangeText={t => {
                        setLogin(t);
                        if (submitted) setSubmitted(false);
                      }}
                      onFocus={() => setLoginFocused(true)}
                      onBlur={() => setLoginFocused(false)}
                      autoComplete="username"
                      textContentType="username"
                      autoCapitalize="none"
                      autoCorrect={false}
                      maxLength={180}
                      returnKeyType="next"
                      onSubmitEditing={() => passwordField.current?.focus()}
                      style={s.fieldInput}
                    />
                  </View>
                </View>

                {/* Divider between rows */}
                <View style={s.rowDivider} />

                {/* Row 2: Password */}
                <View style={[s.loginRow, passwordFocused && s.loginRowFocused]}>
                  <View style={s.loginField}>
                    <Text style={[s.fieldLabel, passwordFocused && s.fieldLabelFocused]}>
                      Mật khẩu
                    </Text>
                    <TextInput
                      ref={passwordField}
                      accessibilityLabel="Mật khẩu"
                      value={password}
                      editable={!auth.busy}
                      onChangeText={p => {
                        setPassword(p);
                        if (submitted) setSubmitted(false);
                      }}
                      onFocus={() => setPasswordFocused(true)}
                      onBlur={() => setPasswordFocused(false)}
                      autoComplete="current-password"
                      textContentType="password"
                      secureTextEntry={!showPassword}
                      autoCapitalize="none"
                      autoCorrect={false}
                      maxLength={256}
                      returnKeyType="go"
                      onSubmitEditing={handleSubmit}
                      style={[s.fieldInput, { flex: 1 }]}
                    />
                  </View>

                  {/* .login-eye */}
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                    onPress={() => setShowPassword(v => !v)}
                    style={s.loginEye}
                  >
                    <Ionicons
                      name={showPassword ? 'eye-off-outline' : 'eye-outline'}
                      color={isDark ? '#B7BFCD' : '#616C7B'}
                      size={20}
                    />
                  </Pressable>
                </View>
              </View>

              {/* .login-error */}
              {displayError ? (
                <Text accessibilityRole="alert" accessibilityLiveRegion="polite" style={s.loginError}>
                  {displayError}
                </Text>
              ) : null}

              {/* .login-options */}
              <View style={s.loginOptions}>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Trợ giúp đăng nhập"
                  accessibilityState={{ expanded: showHelp }}
                  onPress={() => setShowHelp(h => !h)}
                  style={({ pressed }) => ({ opacity: pressed ? 0.6 : 1, minHeight: 44, justifyContent: 'center' })}
                >
                  <Text style={s.textButton}>Quên mật khẩu?</Text>
                </Pressable>
              </View>

              {/* .login-help */}
              {showHelp ? (
                <View style={s.loginHelp}>
                  <Text style={s.helpText}>
                    Dùng tài khoản Kênh Người Bán của shop đã liên kết. Nếu quên mật khẩu, khôi phục qua Kênh Người Bán hoặc liên hệ người quản lý hệ thống.
                  </Text>
                </View>
              ) : null}

              {/* .login-submit */}
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Đăng nhập"
                disabled={auth.busy}
                accessibilityState={{ disabled: auth.busy }}
                onPress={handleSubmit}
                style={({ pressed }) => [
                  s.loginSubmit,
                  {
                    opacity: auth.busy ? 0.6 : pressed ? 0.9 : 1,
                    transform: [{ scale: pressed ? 0.98 : 1 }],
                  },
                ]}
              >
                {auth.busy ? (
                  <ActivityIndicator color="#0b1f3f" />
                ) : (
                  <Text style={s.submitText}>Đăng nhập</Text>
                )}
              </Pressable>

              {/* Quick Biometrics if supported on device */}
              {auth.biometric && auth.capability.available && Platform.OS !== 'web' ? (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={'Đăng nhập bằng ' + auth.capability.label}
                  onPress={() => void auth.unlock()}
                  style={({ pressed }) => [s.bioOption, { opacity: pressed ? 0.6 : 1 }]}
                >
                  <Ionicons name="scan-outline" size={17} color={isDark ? '#B7BFCD' : '#616C7B'} />
                  <Text style={s.bioText}>Sử dụng {auth.capability.label}</Text>
                </Pressable>
              ) : null}
            </View>
          )}
        </View>
        {!wide ? <View style={s.securityNote}><Ionicons name="shield-checkmark-outline" size={14} color={isDark ? '#AEB9CB' : '#616C7B'} /><Text style={s.securityText}>Không gian riêng dành cho gian hàng của bạn</Text></View> : null}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

export function AuthGate({ children }: { children: ReactNode }) {
  const auth = useAuth()!;
  const { isDark } = useTheme();
  if (auth.phase === 'checking')
    return (
      <View
        style={{
          flex: 1,
          backgroundColor: isDark ? '#071120' : '#F6F4F0',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 16,
        }}
      >
        <Image source={SHIPCODE_LOGO} style={{ width: 84, height: 84 }} resizeMode="contain" />
        <ActivityIndicator color="#ffb800" />
      </View>
    );
  return (
    <View style={{ flex: 1 }}>
      {auth.phase === 'signed_in' ? children : <LoginScreen />}
      {auth.privateScreen ? (
        <View
          testID="privacy-screen"
          pointerEvents="auto"
          style={{
            position: 'absolute',
            inset: 0,
            backgroundColor: isDark ? '#071120' : '#F6F4F0',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Image source={SHIPCODE_LOGO} style={{ width: 84, height: 84 }} resizeMode="contain" />
        </View>
      ) : null}
    </View>
  );
}

const createStyles = (dark: boolean) => StyleSheet.create({
  login: {
    flex: 1,
    backgroundColor: dark ? '#071120' : '#F6F4F0',
    position: 'relative',
  },
  scrollBody: {
    flexGrow: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  scrollBodyMobile: {
    width: '100%',
    flexDirection: 'column',
  },
  scrollBodyWide: {
    width: '100%',
    maxWidth: 1100,
    alignSelf: 'center',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 48,
  },

  /* ── login-bg ── */
  loginBg: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    overflow: 'hidden',
  },
  aurora1: {
    position: 'absolute',
    top: -140,
    right: -120,
    width: 380,
    height: 380,
    borderRadius: 190,
    backgroundColor: '#ffb800',
    opacity: Platform.OS === 'web' ? (dark ? 0.12 : 0.07) : 0.035,
    ...Platform.select({
      web: { filter: 'blur(70px)' } as object,
      default: {},
    }),
  },
  aurora2: {
    position: 'absolute',
    top: '28%',
    left: -180,
    width: 340,
    height: 340,
    borderRadius: 170,
    backgroundColor: '#f0233b',
    opacity: Platform.OS === 'web' ? (dark ? 0.07 : 0.035) : 0.02,
    ...Platform.select({
      web: { filter: 'blur(70px)' } as object,
      default: {},
    }),
  },
  aurora3: {
    position: 'absolute',
    bottom: -220,
    right: -120,
    width: 460,
    height: 460,
    borderRadius: 230,
    backgroundColor: '#163f86',
    opacity: Platform.OS === 'web' ? (dark ? 0.23 : 0.04) : 0.03,
    ...Platform.select({
      web: { filter: 'blur(70px)' } as object,
      default: {},
    }),
  },
  streak: {
    position: 'absolute',
    left: 0,
    height: 2,
    width: 140,
    backgroundColor: dark ? 'rgba(255,184,0,0.1)' : 'rgba(159,69,23,0.06)',
    borderRadius: 2,
  },

  /* ── login-hero ── */
  loginHero: {
    minHeight: 245,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 0,
    paddingVertical: 12,
    marginBottom: 24,
  },
  loginHeroWide: {
    flex: 1,
    minWidth: 0,
    minHeight: 380,
    paddingVertical: 40,
    marginBottom: 0,
  },
  loginEmblem: {
    width: 184,
    height: 184,
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  loginEmblemWide: {
    width: 270,
    height: 270,
  },
  emblemDashed: {
    position: 'absolute',
    inset: -14,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: dark ? 'rgba(255,255,255,0.16)' : 'rgba(42,48,58,0.15)',
    borderStyle: 'dashed',
  },
  emblemGlow: {
    position: 'absolute',
    inset: '14%',
    borderRadius: 999,
    backgroundColor: dark ? 'rgba(255,184,0,0.24)' : 'rgba(255,184,0,0.17)',
    ...Platform.select({
      web: { filter: 'blur(28px)' } as object,
      default: {},
    }),
  },
  orbitRing: {
    position: 'absolute',
    inset: -14,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'flex-start',
  },
  orbitBead: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#ffb800',
    marginTop: -4,
    ...Platform.select({
      web: {
        boxShadow: '0 0 14px 4px rgba(255, 184, 0, 0.7)',
      } as object,
      default: {
        shadowColor: '#ffb800',
        shadowOpacity: 0.8,
        shadowRadius: 8,
        elevation: 4,
      },
    }),
  },
  logoContainer: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
  },
  loginLogo: {
    width: '92%',
    height: '92%',
    ...Platform.select({
      web: {
        filter: dark ? 'drop-shadow(0 10px 18px rgba(0,0,0,0.2))' : 'none',
      } as object,
      default: {},
    }),
  },

  /* ── login-wordmark ── */
  loginWordmark: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 14,
  },
  wordmarkText: {
    fontSize: 25,
    lineHeight: 32,
    fontWeight: '600',
    letterSpacing: -0.8,
    color: dark ? '#F5F7FB' : '#242B35',
  },
  heroCaption: { color: dark ? '#AEB9CB' : '#616C7B', fontSize: 13, lineHeight: 21, marginTop: 9, textAlign: 'center' },
  formCaption: { color: dark ? '#AEB9CB' : '#616C7B', fontSize: 14, lineHeight: 22, marginBottom: 22, marginTop: 5 },
  securityNote: { flexDirection: 'row', gap: 7, alignItems: 'center', justifyContent: 'center', marginTop: 22, maxWidth: '100%' },
  securityText: { fontSize: 11, lineHeight: 18, color: dark ? '#AEB9CB' : '#616C7B', flexShrink: 1, textAlign: 'center' },

  /* ── login-card ── */
  loginCard: {
    width: '100%',
    maxWidth: 420,
    marginHorizontal: 0,
    backgroundColor: dark ? 'rgba(22,34,53,0.94)' : 'rgba(255,255,255,0.96)',
    borderWidth: 1,
    borderColor: dark ? '#35435A' : '#E1DED7',
    borderRadius: 24,
    paddingHorizontal: 22,
    paddingTop: 24,
    paddingBottom: 20,
    ...Platform.select({
      web: {
        backdropFilter: 'blur(28px) saturate(160%)',
        boxShadow: dark ? '0 18px 55px rgba(0,0,0,0.20), inset 0 1px rgba(255,255,255,0.05)' : '0 12px 45px rgba(62,45,26,0.06), inset 0 1px rgba(255,255,255,0.9)',
      } as object,
      default: {
        shadowColor: '#000',
        shadowOpacity: dark ? 0.2 : 0.06,
        shadowRadius: 18,
        shadowOffset: { width: 0, height: 8 },
        elevation: 3,
      },
    }),
  },
  loginCardWide: {
    flexBasis: 400,
    flexGrow: 0,
    flexShrink: 0,
    marginHorizontal: 0,
    paddingHorizontal: 32,
    paddingTop: 36,
    paddingBottom: 32,
  },
  loginTitle: {
    fontSize: 24,
    fontWeight: '600',
    letterSpacing: -0.6,
    color: dark ? '#F5F7FB' : '#242B35',
    marginBottom: 0,
  },

  /* ── login-group ── */
  loginGroup: {
    backgroundColor: dark ? '#1B2A40' : '#F7F7F9',
    borderWidth: 1,
    borderColor: dark ? '#42506A' : '#D6D9DF',
    borderRadius: 14,
    overflow: 'hidden',
  },
  loginGroupInvalid: {
    borderColor: '#ff6b6b',
  },
  loginRow: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 68,
    paddingLeft: 16,
    paddingRight: 6,
  },
  loginRowFocused: {
    backgroundColor: dark ? '#24344C' : '#FFF8EE',
  },
  rowDivider: {
    height: 1,
    backgroundColor: dark ? '#42506A' : '#D6D9DF',
  },
  loginField: {
    flex: 1,
    minWidth: 0,
    gap: 3,
    justifyContent: 'center',
  },
  fieldLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: dark ? '#AFBDD1' : '#616C7B',
  },
  fieldLabelFocused: {
    color: dark ? '#FFD377' : '#93420D',
  },
  fieldInput: {
    fontSize: 16,
    color: dark ? '#F5F7FB' : '#242B35',
    paddingVertical: 4,
    paddingHorizontal: 0,
    margin: 0,
    minHeight: 29,
    ...Platform.select({
      web: { outlineStyle: 'none' } as object,
      default: {},
    }),
  },
  loginEye: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
  },

  /* ── login-error ── */
  loginError: {
    color: dark ? '#FFA79C' : '#AB3024',
    fontSize: 13,
    lineHeight: 18,
    marginTop: 10,
    paddingHorizontal: 4,
  },

  /* ── login-options ── */
  loginOptions: {
    alignItems: 'flex-end',
    marginTop: 6,
  },
  textButton: {
    fontSize: 13,
    color: dark ? '#B7C3D6' : '#616C7B',
    fontWeight: '500',
  },

  /* ── login-help ── */
  loginHelp: {
    backgroundColor: dark ? '#24344C' : '#F4F3F0',
    borderRadius: 14,
    marginTop: 6,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  helpText: {
    fontSize: 13,
    lineHeight: 19,
    color: dark ? '#B7C3D6' : '#616C7B',
  },

  /* ── login-submit ── */
  loginSubmit: {
    backgroundColor: '#ffb800',
    borderRadius: 13,
    minHeight: 56,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
    ...Platform.select({
      web: {
        background: 'linear-gradient(#ffcb3d, #ffb800)',
        boxShadow: '0 5px 12px rgba(188,118,15,0.10), inset 0 1px rgba(255,255,255,0.5)',
      } as object,
      default: {
        shadowColor: '#ffb800',
        shadowOpacity: 0.35,
        shadowRadius: 14,
        shadowOffset: { width: 0, height: 6 },
        elevation: 4,
      },
    }),
  },
  submitText: {
    color: '#0b1f3f',
    fontSize: 16,
    fontWeight: '700',
    letterSpacing: 0.2,
  },

  bioOption: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    marginTop: 14,
    minHeight: 44,
  },
  bioText: {
    fontSize: 13,
    color: dark ? '#B7C3D6' : '#616C7B',
    fontWeight: '500',
  },

  lockedDesc: {
    fontSize: 14,
    color: dark ? '#B7C3D6' : '#616C7B',
    textAlign: 'center',
  },
});
