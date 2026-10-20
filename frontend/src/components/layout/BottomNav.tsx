import { InterfaceIcon } from '../ui/InterfaceIcon';
import * as Haptics from 'expo-haptics';
import { ReactNode, useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, Image, Platform, Pressable, PressableProps, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../../theme/ThemeProvider';
import Svg, { Defs, LinearGradient, Path, Stop } from 'react-native-svg';
import { DockMask } from './DockMask';
import { DockMaterial } from './DockMaterial';
import { dockAppearance } from './dockAppearance';
import { ASSISTANT_BUTTON_SIZE, DOCK_BAR_TOP, DOCK_HEIGHT, dockPath } from './dockGeometry';

const SELLERPILOT_TAB_LOGO = require('../../../assets/sellerpilot-tab-logo.png');

export type MainTab = 'home' | 'products' | 'assistant' | 'orders' | 'shop';
const ITEMS = [
  { key: 'home', label: 'Quản lý', icon: 'overview' },
  { key: 'products', label: 'Sản phẩm', icon: 'products' },
  { key: 'assistant', label: 'SellerPilot', icon: 'assistant' },
  { key: 'orders', label: 'Đơn hàng', icon: 'orders' },
  { key: 'shop', label: 'Shop', icon: 'shop' },
] as const;

function TabFeedback({ children, reduceMotion, ...props }: PressableProps & { children: ReactNode; reduceMotion: boolean }) {
  const scale = useRef(new Animated.Value(1)).current;
  const settle = (pressed: boolean) => {
    if (reduceMotion) return;
    Animated.spring(scale, { toValue: pressed ? .97 : 1, stiffness: 380, damping: 31, mass: .65,
      useNativeDriver: Platform.OS !== 'web', isInteraction: false }).start();
  };
  useEffect(() => () => scale.stopAnimation(), [scale]);
  return <Pressable {...props} onPressIn={() => settle(true)} onPressOut={() => settle(false)}>
    <Animated.View style={{ flex: 1, alignSelf: 'stretch', alignItems: 'center', justifyContent: 'center', gap: 3,
      transform: [{ scale }] }}>{children}</Animated.View>
  </Pressable>;
}

export function BottomNav({ tab, onTab, reduceMotion = false }: { tab: MainTab; onTab: (tab: MainTab) => void; reduceMotion?: boolean }) {
  const { ui, isDark, BRAND } = useTheme();
  const insets = useSafeAreaInsets();
  const [width, setWidth] = useState(0), [reduceTransparency, setReduceTransparency] = useState(false);
  const x = useRef(new Animated.Value(0)).current;
  const selectionOpacity = useRef(new Animated.Value(tab === 'assistant' ? 0 : 1)).current;
  const previousWidth = useRef(0);
  const selected = ITEMS.findIndex(item => item.key === tab);
  const itemWidth = Math.max(0, (width - 12) / 5);
  useEffect(() => {
    // First layout / keyboard dismissal should not animate from the first tab.
    if (previousWidth.current !== itemWidth) {
      previousWidth.current = itemWidth; x.setValue(selected * itemWidth); return;
    }
    const animation = Animated.timing(x, { toValue: selected * itemWidth, duration: reduceMotion ? 0 : 200, easing: Easing.out(Easing.cubic), useNativeDriver: Platform.OS !== 'web' });
    animation.start(); return () => animation.stop();
  }, [selected, itemWidth, reduceMotion, x]);
  useEffect(() => {
    const animation = Animated.timing(selectionOpacity, { toValue: tab === 'assistant' ? 0 : 1, duration: reduceMotion ? 0 : 160, useNativeDriver: Platform.OS !== 'web', isInteraction: false });
    animation.start(); return () => animation.stop();
  }, [tab, reduceMotion, selectionOpacity]);
  useEffect(() => {
    if (Platform.OS !== 'ios') return;
    void AccessibilityInfo.isReduceTransparencyEnabled().then(setReduceTransparency);
    const listener = AccessibilityInfo.addEventListener('reduceTransparencyChanged', setReduceTransparency);
    return () => listener.remove();
  }, []);
  const choose = (next: MainTab) => { if (tab !== next && Platform.OS === 'ios') void Haptics.selectionAsync().catch(() => {}); onTab(next); };
  const path = dockPath(width);
  const material = dockAppearance(isDark);
  return <View testID="bottom-dock" pointerEvents="box-none" onLayout={event => setWidth(event.nativeEvent.layout.width)} style={[ui.dockOuter, { height: DOCK_HEIGHT, bottom: Math.max(insets.bottom, 12) }]}>
    {width > 0 ? <View pointerEvents="none" style={[StyleSheet.absoluteFill, ui.dockShadow]}>
      <DockMask key={`${isDark ? 'dark' : 'light'}-${reduceTransparency ? 'solid' : 'glass'}`} width={width} path={path}>
        <DockMaterial dark={isDark} opaque={reduceTransparency} />
        <Animated.View testID="dock-selection" pointerEvents="none" style={[ui.dockPill, { top: DOCK_BAR_TOP + 6, width: itemWidth, opacity: selectionOpacity, backgroundColor: isDark ? '#FF9B5424' : '#F0782420', borderColor: isDark ? '#FFB27D40' : '#E7A17466', transform: [{ translateX: x }] }]} />
      </DockMask>
      <Svg width={width} height={DOCK_HEIGHT} style={StyleSheet.absoluteFill}>
        <Defs><LinearGradient id="dock-edge" x1={0} y1={0} x2={0.25} y2={1}><Stop offset={0} stopColor="#FFF" stopOpacity={isDark ? .52 : .95} /><Stop offset={0.55} stopColor="#FFF" stopOpacity={isDark ? .08 : .2} /><Stop offset={1} stopColor="#FFF" stopOpacity={isDark ? .2 : .65} /></LinearGradient></Defs>
        <Path testID="dock-contour" d={path} fill="none" stroke={material.edge} strokeWidth={1.4} />
        <Path d={path} fill="none" stroke="url(#dock-edge)" strokeWidth={.6} />
      </Svg>
    </View> : null}
      <View style={[ui.dockInner, { marginTop: DOCK_BAR_TOP, height: DOCK_HEIGHT - DOCK_BAR_TOP }]}>
        {ITEMS.map(item => item.key === 'assistant' ? <View key={item.key} pointerEvents="none" style={{ flex: 1 }} /> : <TabFeedback reduceMotion={reduceMotion} key={item.key} accessibilityRole="tab" accessibilityLabel={item.label} accessibilityState={{ selected: tab === item.key }} aria-selected={tab === item.key} onPress={() => choose(item.key)} style={ui.dockTab}><InterfaceIcon name={item.icon} size={24} color={tab === item.key ? BRAND.orangeInk : isDark ? '#B8BBC5' : '#626773'} /><Text numberOfLines={1} maxFontSizeMultiplier={1.15} adjustsFontSizeToFit minimumFontScale={0.9} style={[ui.dockLabel, { width: itemWidth + 8, maxWidth: itemWidth + 8, flexShrink: 0, textAlign: 'center' }, tab === item.key && [ui.dockSelected, { color: BRAND.orangeInk }]]}>{item.label}</Text></TabFeedback>)}
      </View>
      <TabFeedback reduceMotion={reduceMotion} accessibilityRole="tab" accessibilityLabel="SellerPilot" accessibilityHint="Trò chuyện với trợ lý bán hàng" accessibilityState={{ selected: tab === 'assistant' }} aria-selected={tab === 'assistant'} onPress={() => choose('assistant')} style={[ui.aiNavItem, { left: Math.max(0, (width - ASSISTANT_BUTTON_SIZE) / 2) }]}>
        <View testID="assistant-dock-button" style={[ui.aiNavRing, tab === 'assistant' && ui.aiNavRingActive]}><Image source={SELLERPILOT_TAB_LOGO} fadeDuration={0} resizeMode="contain" style={ui.aiNavLogo} /></View>
        <Text maxFontSizeMultiplier={1.15} style={[ui.dockLabel, { marginTop: 4 }, tab === 'assistant' && [ui.dockSelected, { color: BRAND.orangeInk }]]}>Trợ lý</Text>
      </TabFeedback>
  </View>;
}
