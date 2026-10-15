import { Ionicons } from '@expo/vector-icons';
import { BlurView } from 'expo-blur';
import { GlassView, isGlassEffectAPIAvailable, isLiquidGlassAvailable } from 'expo-glass-effect';
import * as Haptics from 'expo-haptics';
import { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, Image, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../../theme/ThemeProvider';

const SELLERPILOT_TAB_LOGO = require('../../../assets/sellerpilot-tab-logo.png');

export type MainTab = 'home' | 'products' | 'assistant' | 'orders' | 'shop';
const ITEMS = [
  { key: 'home', label: 'Quản lý', icon: 'grid' },
  { key: 'products', label: 'Sản phẩm', icon: 'cube' },
  { key: 'assistant', label: 'SellerPilot', icon: 'sparkles' },
  { key: 'orders', label: 'Đơn hàng', icon: 'receipt' },
  { key: 'shop', label: 'Shop', icon: 'storefront' },
] as const;

export function BottomNav({ tab, onTab, reduceMotion = false }: { tab: MainTab; onTab: (tab: MainTab) => void; reduceMotion?: boolean }) {
  const { ui, isDark, IOS } = useTheme();
  const insets = useSafeAreaInsets();
  const [width, setWidth] = useState(0), [reduceTransparency, setReduceTransparency] = useState(false);
  const x = useRef(new Animated.Value(0)).current;
  const previousWidth = useRef(0);
  const selected = ITEMS.findIndex(item => item.key === tab);
  const itemWidth = Math.max(0, (width - 12) / 5);
  useEffect(() => {
    // First layout / keyboard dismissal should not animate from the first tab.
    if (previousWidth.current !== itemWidth) {
      previousWidth.current = itemWidth; x.setValue(selected * itemWidth); return;
    }
    const animation = Animated.timing(x, { toValue: selected * itemWidth, duration: reduceMotion ? 0 : 240, easing: Easing.out(Easing.cubic), useNativeDriver: Platform.OS !== 'web' });
    animation.start(); return () => animation.stop();
  }, [selected, itemWidth, reduceMotion, x]);
  useEffect(() => {
    if (Platform.OS !== 'ios') return;
    void AccessibilityInfo.isReduceTransparencyEnabled().then(setReduceTransparency);
    const listener = AccessibilityInfo.addEventListener('reduceTransparencyChanged', setReduceTransparency);
    return () => listener.remove();
  }, []);
  const nativeGlass = Platform.OS === 'ios' && !reduceTransparency && isGlassEffectAPIAvailable() && isLiquidGlassAvailable();
  const choose = (next: MainTab) => { if (tab !== next && Platform.OS === 'ios') void Haptics.selectionAsync().catch(() => {}); onTab(next); };
  return <View testID="bottom-dock" pointerEvents="box-none" style={[ui.dockOuter, { bottom: Math.max(insets.bottom, 12) }]}>
    <View style={ui.dockShadow}>
      <View pointerEvents="none" style={ui.dockGlass}>
        {/* Let iOS render its regular glass material without a solid tint over it. */}
        {nativeGlass ? <GlassView glassEffectStyle="regular" colorScheme={isDark ? 'dark' : 'light'} style={StyleSheet.absoluteFill} /> : reduceTransparency ? <View style={[StyleSheet.absoluteFill, { backgroundColor: IOS.card }]} /> : <BlurView intensity={55} tint={isDark ? 'systemMaterialDark' : 'systemMaterialLight'} style={StyleSheet.absoluteFill} />}
        {!nativeGlass && !reduceTransparency ? <View style={[StyleSheet.absoluteFill, { backgroundColor: isDark ? '#23232780' : '#FFFFFF99' }]} /> : null}
      </View>
      <View style={ui.dockInner} onLayout={event => setWidth(event.nativeEvent.layout.width)}>
        <Animated.View testID="dock-selection" pointerEvents="none" style={[ui.dockPill, { width: itemWidth, opacity: tab === 'assistant' ? 0 : 1, transform: [{ translateX: x }] }]} />
        {ITEMS.map(item => item.key === 'assistant' ? <Pressable key={item.key} accessibilityRole="tab" accessibilityLabel="SellerPilot" accessibilityHint="Trò chuyện với trợ lý bán hàng" accessibilityState={{ selected: tab === item.key }} onPress={() => choose(item.key)} style={({ pressed }) => [ui.aiNavItem, pressed && { transform: [{ scale: .94 }] }]}>
          <View style={[ui.aiNavRing, tab === 'assistant' && ui.aiNavRingActive]}><Image source={SELLERPILOT_TAB_LOGO} fadeDuration={0} resizeMode="contain" style={ui.aiNavLogo} /></View>
        </Pressable> : <Pressable key={item.key} accessibilityRole="tab" accessibilityLabel={item.label} accessibilityState={{ selected: tab === item.key }} onPress={() => choose(item.key)} style={({ pressed }) => [ui.dockTab, pressed && { opacity: .65 }]}><Ionicons name={item.icon} size={25} color={tab === item.key ? isDark ? '#64ADFF' : '#007AFF' : isDark ? '#F2F2F7' : '#252527'} /><Text numberOfLines={1} maxFontSizeMultiplier={1.2} style={[ui.dockLabel, itemWidth > 0 && itemWidth < 60 && { fontSize: 10 }, tab === item.key && ui.dockSelected]}>{item.label}</Text></Pressable>)}
      </View>
    </View>
  </View>;
}
