import { InterfaceIcon } from '../ui/InterfaceIcon';
import * as Haptics from 'expo-haptics';
import { memo, ReactNode, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, Image, Platform, Pressable, PressableProps, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../../theme/ThemeProvider';
import Svg, { Defs, LinearGradient, Path, Stop } from 'react-native-svg';
import { DockMask } from './DockMask';
import { DockMaterial } from './DockMaterial';
import { dockAppearance } from './dockAppearance';
import { ASSISTANT_BUTTON_SIZE, DOCK_BAR_TOP, DOCK_HEIGHT, dockBottomInset, dockPath } from './dockGeometry';

const SELLERPILOT_TAB_LOGO = require('../../../assets/sellerpilot-tab-logo.png');

export type MainTab = 'home' | 'products' | 'assistant' | 'orders' | 'shop';
const ITEMS = [
  { key: 'home', label: 'Quản lý', icon: 'overview' },
  { key: 'products', label: 'Sản phẩm', icon: 'products' },
  { key: 'assistant', label: 'SellerPilot', icon: 'assistant' },
  { key: 'orders', label: 'Đơn hàng', icon: 'orders' },
  { key: 'shop', label: 'Shop', icon: 'shop' },
] as const;

function TabFeedback({ children, raised = false, ...props }: PressableProps & { children: ReactNode; raised?: boolean }) {
  return <Pressable {...props}>
    {({ pressed }) => <View style={{ flex: 1, alignSelf: 'stretch', alignItems: 'center', justifyContent: raised ? 'flex-start' : 'center', gap: raised ? 0 : 3, opacity: pressed ? .72 : 1 }}>{children}</View>}
  </Pressable>;
}

export const BottomNav = memo(function BottomNav({ tab, onTab, reduceMotion = false }: { tab: MainTab; onTab: (tab: MainTab) => void; reduceMotion?: boolean }) {
  const { ui, isDark, BRAND } = useTheme();
  const insets = useSafeAreaInsets();
  const viewport = useWindowDimensions();
  // The dock has a known width constraint. Waiting for onLayout initially put
  // the raised logo at the left edge for a frame, also on keyboard dismissal.
  const width = Math.min(480, Math.max(0, Math.min(viewport.width, 600) - 24));
  const [reduceTransparency, setReduceTransparency] = useState(false);
  const selected = ITEMS.findIndex(item => item.key === tab);
  const itemWidth = Math.max(0, (width - 10) / 5);
  const x = useRef(new Animated.Value(selected * itemWidth)).current;
  const selectionOpacity = useRef(new Animated.Value(tab === 'assistant' ? 0 : 1)).current;
  const previousWidth = useRef(itemWidth);
  useLayoutEffect(() => {
    // First layout / keyboard dismissal should not animate from the first tab.
    const opacity = tab === 'assistant' ? 0 : 1;
    if (previousWidth.current !== itemWidth || reduceMotion) {
      previousWidth.current = itemWidth; x.setValue(selected * itemWidth); selectionOpacity.setValue(opacity); return;
    }
    // One short transition owns both parts of the selection; interrupted taps
    // stop the previous transition rather than queueing multiple effects.
    const config = { duration: 140, easing: Easing.out(Easing.cubic), useNativeDriver: Platform.OS !== 'web', isInteraction: false };
    const animation = Animated.parallel([
      Animated.timing(x, { ...config, toValue: selected * itemWidth }),
      Animated.timing(selectionOpacity, { ...config, toValue: opacity }),
    ]);
    animation.start(); return () => animation.stop();
  }, [selected, itemWidth, reduceMotion, x, tab, selectionOpacity]);
  useEffect(() => {
    if (Platform.OS !== 'ios') return;
    let active = true;
    void AccessibilityInfo.isReduceTransparencyEnabled().then(value => { if (active) setReduceTransparency(value); }).catch(() => {});
    const listener = AccessibilityInfo.addEventListener('reduceTransparencyChanged', setReduceTransparency);
    return () => { active = false; listener.remove(); };
  }, []);
  const choose = (next: MainTab) => { if (tab !== next && Platform.OS === 'ios') void Haptics.selectionAsync().catch(() => {}); onTab(next); };
  const path = dockPath(width);
  const material = dockAppearance(isDark);
  return <View testID="bottom-dock" pointerEvents="box-none" style={[ui.dockOuter, { width, height: DOCK_HEIGHT, bottom: dockBottomInset(insets.bottom) }]}>
    {width > 0 ? <View pointerEvents="none" style={[StyleSheet.absoluteFill, ui.dockShadow]}>
      <DockMask width={width} path={path}>
        <DockMaterial dark={isDark} opaque={reduceTransparency} />
        <Animated.View testID="dock-selection" pointerEvents="none" style={[ui.dockPill, { top: DOCK_BAR_TOP + 7, width: itemWidth, opacity: selectionOpacity, backgroundColor: isDark ? '#FF9B541F' : '#F078241A', borderColor: isDark ? '#FFB27D24' : '#E7A17433', transform: [{ translateX: x }] }]} />
      </DockMask>
      <Svg width={width} height={DOCK_HEIGHT} style={StyleSheet.absoluteFill}>
        <Defs><LinearGradient id="dock-edge" x1={0} y1={0} x2={0.25} y2={1}><Stop offset={0} stopColor="#FFF" stopOpacity={isDark ? .52 : .95} /><Stop offset={0.55} stopColor="#FFF" stopOpacity={isDark ? .08 : .2} /><Stop offset={1} stopColor="#FFF" stopOpacity={isDark ? .2 : .65} /></LinearGradient></Defs>
        <Path testID="dock-contour" d={path} fill="none" stroke={material.edge} strokeWidth={1} />
        <Path d={path} fill="none" stroke="url(#dock-edge)" strokeWidth={.45} />
      </Svg>
    </View> : null}
      <View style={[ui.dockInner, { marginTop: DOCK_BAR_TOP, height: DOCK_HEIGHT - DOCK_BAR_TOP }]}>
        {ITEMS.map(item => item.key === 'assistant' ? <View key={item.key} pointerEvents="none" style={{ flex: 1 }} /> : <TabFeedback key={item.key} accessibilityRole="tab" accessibilityLabel={item.label} accessibilityState={{ selected: tab === item.key }} aria-selected={tab === item.key} onPress={() => choose(item.key)} style={ui.dockTab}><InterfaceIcon name={item.icon} size={23} color={tab === item.key ? BRAND.orangeInk : isDark ? '#C3C3CB' : '#585A64'} /><Text numberOfLines={1} maxFontSizeMultiplier={1.15} adjustsFontSizeToFit minimumFontScale={0.9} style={[ui.dockLabel, { width: itemWidth + 8, maxWidth: itemWidth + 8, flexShrink: 0, textAlign: 'center' }, tab === item.key && [ui.dockSelected, { color: BRAND.orangeInk }]]}>{item.label}</Text></TabFeedback>)}
      </View>
      <TabFeedback raised accessibilityRole="tab" accessibilityLabel="SellerPilot" accessibilityHint="Trò chuyện với trợ lý bán hàng" accessibilityState={{ selected: tab === 'assistant' }} aria-selected={tab === 'assistant'} onPress={() => choose('assistant')} style={[ui.aiNavItem, { left: Math.max(0, (width - ASSISTANT_BUTTON_SIZE) / 2) }]}>
        <View testID="assistant-dock-button" style={[ui.aiNavRing, tab === 'assistant' && ui.aiNavRingActive]}><Image source={SELLERPILOT_TAB_LOGO} fadeDuration={0} resizeMode="contain" style={ui.aiNavLogo} /></View>
        <Text maxFontSizeMultiplier={1.15} style={[ui.dockLabel, { marginTop: 4 }, tab === 'assistant' && [ui.dockSelected, { color: BRAND.orangeInk }]]}>Trợ lý</Text>
      </TabFeedback>
  </View>;
});
