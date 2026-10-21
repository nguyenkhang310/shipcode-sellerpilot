import { useState } from 'react';
import { ActivityIndicator, Pressable, Switch, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from './AuthProvider';
import { useTheme } from '../../theme/ThemeProvider';

export function SecuritySettings() {
  const auth = useAuth(), { ui, IOS, BRAND } = useTheme(), [confirm, setConfirm] = useState(false);
  if (!auth?.user) return null;
  return <View style={[ui.listCard, { gap: 16 }]}>
    <View style={[ui.row, { gap: 12 }]}><Ionicons name="shield-checkmark-outline" size={23} color={BRAND.orangeInk} /><View style={{ flex: 1 }}><Text style={ui.listTitle}>Tài khoản & bảo mật</Text><Text style={ui.caption}>{auth.user.user.username} · {auth.user.shop.name}</Text></View></View>
    {auth.capability.reason !== 'web' ? <View style={[ui.between, { gap: 12 }]}><View style={{ flex: 1 }}><Text style={ui.productName}>Mở khóa bằng {auth.capability.label}</Text><Text style={[ui.caption, { marginTop: 4 }]}>{auth.capability.available ? 'Xác thực khi quay lại ứng dụng.' : auth.capability.reason === 'build' ? 'Khả dụng trong bản cài trên điện thoại.' : 'Thiết lập sinh trắc học trong Cài đặt thiết bị.'}</Text></View><Switch accessibilityLabel={'Mở khóa bằng ' + auth.capability.label} value={auth.biometric} disabled={auth.busy || !auth.capability.available} onValueChange={value => void auth.changeBiometric(value)} trackColor={{ true: BRAND.orange, false: IOS.fill }} /></View> : null}
    {auth.biometric ? <Pressable accessibilityRole="button" disabled={auth.busy} onPress={auth.lock} style={ui.secondaryButton}><Ionicons name="lock-closed-outline" size={18} color={IOS.label} /><Text style={ui.secondaryText}>Khóa ứng dụng</Text></Pressable> : null}
    {auth.error ? <Text accessibilityRole="alert" style={ui.error}>{auth.error}</Text> : null}
    {confirm ? <><Text style={ui.productName}>Đăng xuất khỏi tài khoản này?</Text><View style={ui.row}><Pressable accessibilityRole="button" disabled={auth.busy} onPress={() => setConfirm(false)} style={[ui.secondaryButton, { flex: 1 }]}><Text style={ui.secondaryText}>Ở lại</Text></Pressable><Pressable accessibilityRole="button" accessibilityLabel="Xác nhận đăng xuất" disabled={auth.busy} onPress={() => void auth.signOut()} style={[ui.secondaryButton, { flex: 1 }]}>{auth.busy ? <ActivityIndicator color={IOS.red} /> : <Text style={[ui.secondaryText, { color: IOS.red }]}>Đăng xuất</Text>}</Pressable></View></> : <Pressable accessibilityRole="button" accessibilityLabel="Đăng xuất" onPress={() => setConfirm(true)} style={ui.secondaryButton}><Ionicons name="log-out-outline" size={19} color={IOS.red} /><Text style={[ui.secondaryText, { color: IOS.red }]}>Đăng xuất</Text></Pressable>}
  </View>;
}
