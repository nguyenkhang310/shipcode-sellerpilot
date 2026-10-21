import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator, Animated, Easing, KeyboardAvoidingView, Platform, Pressable, ScrollView,
  StyleSheet, Text, TextInput, useWindowDimensions, View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from './AuthProvider';
import { useModalViewport } from '../../components/layout/useModalViewport';
import { useReducedMotion } from '../../components/layout/useReducedMotion';
import { BrandLogo } from '../../components/ui/BrandLogo';

export function LoginScreen({ locked: lockedMode, revealed = true }: { locked?: boolean; revealed?: boolean }) {
  const auth = useAuth()!;
  const insets = useSafeAreaInsets();
  const { width, height } = useWindowDimensions();
  const viewportHeight = useModalViewport();
  const compact = (viewportHeight ?? height) < 720;
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [visible, setVisible] = useState(false);
  const [help, setHelp] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [hideServerError, setHideServerError] = useState(false);
  const [focused, setFocused] = useState<'login' | 'password' | null>(null);
  const passwordInput = useRef<TextInput>(null);
  const locked = lockedMode ?? auth.phase === 'locked';
  const success = auth.phase === 'signed_in';
  const reduced = useReducedMotion();
  const entrance = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (!revealed) return;
    const animation = Animated.timing(entrance, { toValue: 1, duration: reduced ? 0 : 520, easing: Easing.out(Easing.cubic), useNativeDriver: Platform.OS !== 'web', isInteraction: false });
    animation.start();
    return () => animation.stop();
  }, [entrance, reduced, revealed]);
  useEffect(() => { if (success) { setPassword(''); setVisible(false); setSubmitted(false); } }, [success]);
  useEffect(() => { setHideServerError(false); if (auth.error) setSubmitted(false); }, [auth.error]);

  const loginInvalid = submitted && !login.trim();
  const passwordInvalid = submitted && !password;
  const error = loginInvalid ? 'Nhập email hoặc tên đăng nhập của bạn.'
    : passwordInvalid ? 'Nhập mật khẩu của bạn.' : !hideServerError ? auth.error : '';
  const submit = () => {
    setSubmitted(true); setHideServerError(false);
    if (login.trim() && password && !auth.busy) void auth.signIn(login, password);
  };
  const edit = () => { setSubmitted(false); setHideServerError(true); };

  return (
    <KeyboardAvoidingView testID="login-screen" behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={[s.screen, { maxHeight: viewportHeight }]}>
      <ScrollView keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag"
        contentContainerStyle={[s.scroll, {
          paddingTop: Math.max(insets.top, 16),
          paddingBottom: 0,
          paddingHorizontal: 0,
        }]}>
        <View style={s.layout}>
          <Animated.View style={[s.hero, { paddingTop: compact ? 20 : 38, opacity: entrance,
            transform: [{ translateY: entrance.interpolate({ inputRange: [0, 1], outputRange: [-8, 0] }) }] }]}>
            <View style={s.brand}>
              <BrandLogo size={54} />
              <Text style={s.wordmark}>SellerPilot</Text>
            </View>
            <Text accessibilityRole="header" style={s.title}>Chào mừng trở lại.</Text>
            <Text style={s.subtitle}>{locked ? 'Mở khóa để tiếp tục công việc của bạn.' : 'Đăng nhập để tiếp tục công việc của bạn.'}</Text>
          </Animated.View>
          <Animated.View style={[s.formColumn, { paddingHorizontal: width < 360 ? 24 : 30,
            paddingBottom: Math.max(insets.bottom + 20, 28), opacity: entrance,
            transform: [{ translateY: entrance.interpolate({ inputRange: [0, 1], outputRange: [32, 0] }) }] }]}>
            <View style={s.formHeader}><Text style={s.formTitle}>{locked ? 'Mở khóa tài khoản' : 'Đăng nhập'}</Text><View style={s.formAccent} /></View>
            <View>
              {locked ? (
                <>
                  <View style={s.biometricMark}><Ionicons name="scan-outline" size={38} color={'#A84818'} /></View>
                  <Text style={s.lockedText}>Sử dụng {auth.capability.label} để mở khóa phiên của bạn trên thiết bị này.</Text>
                  {auth.error ? <Text accessibilityRole="alert" accessibilityLiveRegion="polite" style={s.error}>{auth.error}</Text> : null}
                  <LoginSubmit label={'Mở khóa bằng ' + auth.capability.label} busy={auth.busy} success={success}
                    disabled={!auth.capability.available} onPress={() => void auth.unlock()} />
                  <Pressable accessibilityRole="button" disabled={auth.busy} onPress={auth.usePassword} style={s.secondaryAction}>
                    <Text style={s.link}>Dùng mật khẩu tài khoản</Text>
                  </Pressable>
                </>
              ) : (
                <>
                  <View style={s.field}>
                    <Text style={s.label}>Email hoặc tên đăng nhập</Text>
                    <View style={[s.inputBox, focused === 'login' && s.focused, loginInvalid && s.invalid]}>
                      <TextInput accessibilityLabel="Email hoặc tên đăng nhập" value={login} editable={!auth.busy && !success}
                        onChangeText={value => { setLogin(value); edit(); }} onFocus={() => setFocused('login')} onBlur={() => setFocused(null)}
                        placeholder="Tên tài khoản của bạn" placeholderTextColor={'#777C85'}
                        autoComplete="username" textContentType="username" autoCapitalize="none" autoCorrect={false}
                        maxLength={180} returnKeyType="next" onSubmitEditing={() => passwordInput.current?.focus()} style={s.input} />
                    </View>
                  </View>
                  <View style={s.field}>
                    <Text style={s.label}>Mật khẩu</Text>
                    <View style={[s.inputBox, focused === 'password' && s.focused, passwordInvalid && s.invalid]}>
                      <TextInput ref={passwordInput} accessibilityLabel="Mật khẩu" value={password} editable={!auth.busy && !success}
                        onChangeText={value => { setPassword(value); edit(); }} onFocus={() => setFocused('password')} onBlur={() => setFocused(null)}
                        placeholder="Nhập mật khẩu" placeholderTextColor={'#777C85'}
                        autoComplete="current-password" textContentType="password" secureTextEntry={success || !visible}
                        autoCapitalize="none" autoCorrect={false} maxLength={256} returnKeyType="go" onSubmitEditing={submit} style={s.input} />
                      <Pressable accessibilityRole="button" accessibilityLabel={visible ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                        onPress={() => setVisible(value => !value)} style={s.eye}>
                        <Ionicons name={visible ? 'eye-off-outline' : 'eye-outline'} size={21} color={'#606772'} />
                      </Pressable>
                    </View>
                  </View>
                  {error ? <Text accessibilityRole="alert" accessibilityLiveRegion="polite" style={s.error}>{error}</Text> : null}
                  <Pressable accessibilityRole="button" accessibilityLabel="Trợ giúp đăng nhập" accessibilityState={{ expanded: help }}
                    onPress={() => setHelp(value => !value)} style={({ pressed }) => [s.helpAction, pressed && s.pressed]}>
                    <Text style={s.link}>Quên mật khẩu?</Text>
                  </Pressable>
                  {help ? <View style={s.help}><Text style={s.helpText}>Dùng tài khoản Kênh Người Bán của shop đã liên kết. Nếu quên mật khẩu, khôi phục qua Kênh Người Bán hoặc liên hệ người quản lý hệ thống.</Text></View> : null}
                  <LoginSubmit label="Đăng nhập" busy={auth.busy} success={success} onPress={submit} />
                  {auth.biometric && auth.capability.available && Platform.OS !== 'web' ? (
                    <Pressable accessibilityRole="button" accessibilityLabel={'Đăng nhập bằng ' + auth.capability.label}
                      disabled={auth.busy} onPress={() => void auth.unlock()} style={s.secondaryAction}>
                      <Ionicons name="scan-outline" size={20} color={'#A84818'} /><Text style={s.link}>Sử dụng {auth.capability.label}</Text>
                    </Pressable>
                  ) : null}
                </>
              )}
            </View>
            <Text style={s.footnote}>ShipCode · SellerPilot</Text>
          </Animated.View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function LoginSubmit({ label, busy, success, disabled = false, onPress }: {
  label: string; busy: boolean; success: boolean; disabled?: boolean; onPress: () => void;
}) {
  const reduced = useReducedMotion();
  const progress = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const animation = Animated.timing(progress, { toValue: busy || success ? 1 : 0,
      duration: reduced ? 0 : 180, easing: Easing.out(Easing.cubic), useNativeDriver: Platform.OS !== 'web', isInteraction: false });
    animation.start(); return () => animation.stop();
  }, [busy, success, reduced, progress]);
  return <Pressable accessibilityRole="button" accessibilityLabel={label}
    accessibilityState={{ disabled: disabled || busy || success, busy }} disabled={disabled || busy || success}
    onPress={onPress} style={({ pressed }) => [s.submit, disabled && s.disabled, pressed && s.pressed]}>
    <Animated.View pointerEvents="none" style={[StyleSheet.absoluteFill, s.buttonFill,
      { opacity: progress.interpolate({ inputRange: [0, 1], outputRange: [1, 0] }) }]} />
    <Animated.Text style={[s.submitText, { opacity: progress.interpolate({ inputRange: [0, 1], outputRange: [1, 0] }) }]}>{label}</Animated.Text>
    {(busy || success) ? <Animated.View testID={success ? 'login-success' : 'login-progress'} pointerEvents="none" style={[s.progressCircle,
      { opacity: progress, transform: [{ scale: progress.interpolate({ inputRange: [0, 1], outputRange: [0.86, 1] }) }] }]}>
      {success ? <Ionicons name="checkmark" color="#FFFFFF" size={25} /> : <ActivityIndicator color="#FFFFFF" />}
    </Animated.View> : null}
  </Pressable>;
}

// Authentication keeps a fixed light form surface in every app theme.
const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#111317' },
  scroll: { flexGrow: 1, alignItems: 'center' },
  layout: { flexGrow: 1, width: '100%', maxWidth: 520 },
  hero: { alignItems: 'center', paddingHorizontal: 24, paddingBottom: 34 },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 22 },
  wordmark: { fontSize: 23, fontWeight: '600', letterSpacing: -0.7, color: '#F7F5F1' },
  title: { fontSize: 28, fontWeight: '500', fontStyle: 'italic', lineHeight: 38, color: '#F7F5F1',
    fontFamily: Platform.select({ ios: 'Georgia', android: 'serif', web: 'Georgia, serif' }) },
  subtitle: { marginTop: 9, fontSize: 13, lineHeight: 21, color: '#B4B5BC', textAlign: 'center' },
  formColumn: { flexGrow: 1, width: '100%', paddingTop: 28, borderTopLeftRadius: 32, borderTopRightRadius: 32,
    backgroundColor: '#FFFFFF' },
  formHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 26 },
  formTitle: { fontSize: 19, fontWeight: '600', letterSpacing: -0.4, color: '#1D2026' },
  formAccent: { width: 25, height: 3, borderRadius: 2, backgroundColor: '#DF7C40' },
  field: { gap: 8, marginBottom: 20 },
  label: { fontSize: 13, fontWeight: '500', lineHeight: 20, color: '#555B65' },
  inputBox: { height: 56, borderRadius: 12, borderWidth: 1, borderColor: '#D3D5DC',
    backgroundColor: '#EDEEF2', flexDirection: 'row', alignItems: 'center' },
  focused: { borderColor: '#B34B1A' },
  invalid: { borderColor: '#B53524' },
  input: { flex: 1, minWidth: 0, height: '100%', paddingVertical: 0, paddingHorizontal: 16, fontSize: 16,
    textAlignVertical: 'center', includeFontPadding: false, color: '#20242A',
    ...Platform.select({ web: { outlineStyle: 'none' } as object, default: {} }) },
  eye: { width: 48, height: '100%', alignItems: 'center', justifyContent: 'center' },
  error: { color: '#AC3023', fontSize: 13, lineHeight: 20, marginBottom: 8 },
  helpAction: { alignSelf: 'flex-end', minHeight: 44, justifyContent: 'center', paddingLeft: 12, marginTop: -14, marginBottom: 16 },
  link: { color: '#A24315', fontSize: 13, lineHeight: 20, fontWeight: '500' },
  help: { paddingVertical: 4, marginBottom: 22 },
  helpText: { color: '#5B616A', fontSize: 13, lineHeight: 21 },
  submit: { minHeight: 54, paddingHorizontal: 20, paddingVertical: 14, alignItems: 'center', justifyContent: 'center', position: 'relative' },
  buttonFill: { borderRadius: 12, backgroundColor: '#B65323' },
  progressCircle: { position: 'absolute', width: 54, height: 54, borderRadius: 27, backgroundColor: '#B65323', alignItems: 'center', justifyContent: 'center' },
  submitText: { color: '#FFFFFF', fontSize: 16, fontWeight: '600', lineHeight: 24 },
  disabled: { opacity: 0.55 },
  pressed: { opacity: 0.82 },
  secondaryAction: { minHeight: 48, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 8, marginTop: 12 },
  biometricMark: { alignSelf: 'center', paddingVertical: 14 },
  lockedText: { color: '#676C75', fontSize: 15, textAlign: 'center', lineHeight: 24, marginBottom: 22 },
  footnote: { marginTop: 30, textAlign: 'center', fontSize: 11, lineHeight: 18, color: '#727781' },
});
