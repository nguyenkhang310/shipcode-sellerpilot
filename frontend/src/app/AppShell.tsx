import { StatusBar } from 'expo-status-bar';
import { ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, Keyboard, KeyboardAvoidingView, Linking, Platform, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { STORE_URL } from '../api/client';
import { useManagement } from '../features/dashboard/useManagement';
import { initialTab } from './navigation';
import { TopBar } from '../components/layout/TopBar';
import { BottomNav, MainTab } from '../components/layout/BottomNav';
import { DashboardScreen, ManagementRoute } from '../features/dashboard/DashboardScreen';
import { ManagementSheet } from '../features/dashboard/ManagementSheet';
import { AssistantChat, AssistantHandle } from '../features/assistant/AssistantChat';
import { useTheme } from '../theme/ThemeProvider';
import { inExtension, extensionCall } from '../integrations/extension';
import { ExtensionBar } from '../integrations/ExtensionBar';

const PANEL_ROUTES: Partial<Record<MainTab, ManagementRoute>> = { products: { kind: 'products' }, orders: { kind: 'orders' }, shop: { kind: 'settings' } };

function Scene({ active, reduceMotion, children }: { active: boolean; reduceMotion: boolean; children: ReactNode }) {
  const { ui } = useTheme();
  const value = useRef(new Animated.Value(active ? 1 : 0)).current;
  useEffect(() => {
    if (!active) { value.stopAnimation(); value.setValue(0); return; }
    const animation = Animated.timing(value, { toValue: 1, duration: reduceMotion ? 0 : 210, easing: Easing.out(Easing.cubic), useNativeDriver: Platform.OS !== 'web', isInteraction: false });
    animation.start(); return () => animation.stop();
  }, [active, reduceMotion, value]);
  // Only the incoming content fades over an opaque page. Crossfading both full
  // screens makes order rows show through the chat while switching tabs.
  return <View pointerEvents={active ? 'auto' : 'none'} accessibilityElementsHidden={!active} importantForAccessibility={active ? 'auto' : 'no-hide-descendants'} aria-hidden={!active} style={[ui.scene, { zIndex: active ? 1 : 0, display: active ? 'flex' : 'none' }]}><Animated.View style={{ flex: 1, opacity: value, transform: [{ translateY: value.interpolate({ inputRange: [0, 1], outputRange: [5, 0] }) }] }}>{children}</Animated.View></View>;
}

export function AppShell({ darkMode, onDarkModeChange }: { darkMode: boolean; onDarkModeChange: (value: boolean) => void }) {
  const { ui } = useTheme();
  const insets = useSafeAreaInsets();
  const [tab, setTab] = useState<MainTab>(() => initialTab() === 'assistant' ? 'assistant' : 'home');
  const [route, setRoute] = useState<ManagementRoute | null>(null);
  const { data, days, selectedDate, onDate, loading, refreshing, error, onDays, refresh, pullRefresh, ensureFresh } = useManagement(tab === 'home');
  const [shopRevision, setShopRevision] = useState(0);
  const refreshShop = useCallback(() => {
    setShopRevision(value => value + 1);
    void refresh();
  }, [refresh]);
  const [toast, setToast] = useState(''), [reduceMotion, setReduceMotion] = useState(false);
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const [webViewportHeight, setWebViewportHeight] = useState<number | undefined>();
  const chat = useRef<AssistantHandle>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showToast = useCallback((message: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast(message); toastTimer.current = setTimeout(() => setToast(''), 3600);
  }, []);
  useEffect(() => {
    void AccessibilityInfo.isReduceMotionEnabled().then(setReduceMotion);
    const listener = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduceMotion);
    return () => { listener.remove(); if (toastTimer.current) clearTimeout(toastTimer.current); };
  }, []);
  useEffect(() => {
    if (Platform.OS === 'web') {
      const viewport = window.visualViewport;
      const sync = () => {
        const visible = Boolean(viewport && window.innerHeight - viewport.height > 140);
        setKeyboardVisible(visible); setWebViewportHeight(visible ? viewport?.height : undefined);
      };
      viewport?.addEventListener('resize', sync);
      return () => viewport?.removeEventListener('resize', sync);
    }
    // KeyboardAvoidingView owns the keyboard animation; a second layout animation
    // here competes with it and makes the composer jump on native iOS.
    const show = Keyboard.addListener(Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow', () => setKeyboardVisible(true));
    const hide = Keyboard.addListener(Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide', () => setKeyboardVisible(false));
    return () => { show.remove(); hide.remove(); };
  }, []);
  const switchTab = (next: MainTab) => {
    if (next === tab) return;
    Keyboard.dismiss(); setTab(next);
    if (next === 'home') ensureFresh();
  };
  const ask = (message: string) => { setRoute(null); setTab('assistant'); chat.current?.ask(message); };
  const openStore = (path = '/seller') => { void (inExtension() ? extensionCall('open_store', {path}) : Linking.openURL(STORE_URL + path)).catch(() => showToast('Chưa mở được Shopee. Kiểm tra kết nối với máy chạy shop.')); };
  // Keep the avoiding view at screen origin. The safe area belongs INSIDE it;
  // otherwise frame.y already includes the top inset and an offset counts it twice.
  return <View style={ui.outer}><View style={[ui.app, webViewportHeight !== undefined && { maxHeight: webViewportHeight }]}><StatusBar style={darkMode ? 'light' : 'dark'} /><KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={0} style={{ flex: 1 }}><View style={{ flex: 1, paddingTop: insets.top }}>
    <TopBar tab={tab} hasTasks={Boolean(data && Object.values(data.tasks).some(value => value > 0))} onProfile={() => { Keyboard.dismiss(); setRoute({ kind: 'settings' }); }} onTasks={() => { Keyboard.dismiss(); setRoute({ kind: 'tasks' }); }} onHistory={() => { Keyboard.dismiss(); chat.current?.openHistory(); }} onNewChat={() => { Keyboard.dismiss(); chat.current?.newConversation(); }} />
    {inExtension() ? <ExtensionBar /> : null}
    <View style={ui.host}><Scene active={tab === 'home'} reduceMotion={reduceMotion}><DashboardScreen data={data} loading={loading} refreshing={refreshing} onPullRefresh={() => void pullRefresh()} error={error} days={days} selectedDate={selectedDate} onDate={onDate} reduceMotion={reduceMotion} onDays={onDays} onRefresh={refreshShop} onOpen={setRoute} onAsk={ask} onStore={openStore} /></Scene><Scene active={tab === 'assistant'} reduceMotion={reduceMotion}><AssistantChat ref={chat} keyboardVisible={keyboardVisible} reduceMotion={reduceMotion} onShopChanged={refreshShop} onToast={showToast} /></Scene>{(['products', 'orders', 'shop'] as const).map(key => <Scene key={key} active={tab === key} reduceMotion={reduceMotion}><ManagementSheet revision={shopRevision} embedded active={tab === key} route={PANEL_ROUTES[key]!} onClose={() => {}} onOpen={setRoute} data={data} onAsk={ask} onStore={openStore} connectionError={error} refreshing={loading} darkMode={darkMode} onDarkMode={onDarkModeChange} onRefresh={refreshShop} /></Scene>)}</View>
  </View></KeyboardAvoidingView>
    {!keyboardVisible ? <BottomNav tab={tab} onTab={switchTab} reduceMotion={reduceMotion} /> : null}
    <ManagementSheet revision={shopRevision} route={route} onClose={() => setRoute(null)} onOpen={setRoute} data={data} onAsk={ask} onStore={openStore} connectionError={error} refreshing={loading} darkMode={darkMode} onDarkMode={onDarkModeChange} onRefresh={refreshShop} />
    {toast ? <View pointerEvents="none" accessibilityLiveRegion="polite" style={ui.toast}><Text style={ui.toastText}>{toast}</Text></View> : null}
  </View></View>;
}
