import { ReactNode, useEffect, useRef, useState } from 'react';
import { Animated, Easing, Modal, Platform, Pressable, StyleSheet, View, useWindowDimensions } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../../theme/ThemeProvider';

export function ChatHistoryDrawer({ visible, onClose, reduceMotion, children }: {
  visible: boolean; onClose: () => void; reduceMotion: boolean; children: ReactNode;
}) {
  const { ui } = useTheme();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const drawerWidth = Math.min(width * .88, 380);
  const [present, setPresent] = useState(visible);
  const progress = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (visible && !present) { setPresent(true); return; }
    if (!present) return;
    const transition = Animated.timing(progress, { toValue: visible ? 1 : 0,
      duration: reduceMotion ? 0 : visible ? 240 : 180,
      easing: Easing.out(Easing.cubic), useNativeDriver: Platform.OS !== 'web', isInteraction: false });
    transition.start(({ finished }) => { if (finished && !visible) setPresent(false); });
    return () => transition.stop();
  }, [visible, present, progress, reduceMotion]);
  return <Modal visible={present} transparent animationType="none" onRequestClose={onClose}>
    <View style={{ flex: 1, alignItems: 'center' }}>
      <Animated.View pointerEvents="none" style={[StyleSheet.absoluteFill, { backgroundColor: '#08172E66', opacity: progress }]} />
      <Pressable accessibilityRole="button" accessibilityLabel="Đóng lịch sử" onPress={onClose} style={StyleSheet.absoluteFill} />
      <View pointerEvents="box-none" style={{ width: '100%', maxWidth: 600, flex: 1 }}>
        <Animated.View testID="chat-history-panel" accessibilityViewIsModal style={[ui.historyDrawer, { width: drawerWidth,
          paddingTop: insets.top + 12, paddingBottom: insets.bottom + 16,
          transform: [{ translateX: progress.interpolate({ inputRange: [0, 1], outputRange: [-drawerWidth, 0] }) }] }]}>
          {children}
        </Animated.View>
      </View>
    </View>
  </Modal>;
}
