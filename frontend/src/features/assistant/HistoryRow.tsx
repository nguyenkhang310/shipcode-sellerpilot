import { Ionicons } from '@expo/vector-icons';
import { useEffect, useRef } from 'react';
import { ActivityIndicator, Animated, PanResponder, Platform, Pressable, Text, View } from 'react-native';
import { ConversationSummary } from '../../api/types';
import { useTheme } from '../../theme/ThemeProvider';

const ACTION_WIDTH = 136;
type Props = {
  item: ConversationSummary; selected: boolean; revealed: boolean; disabled: boolean; busy: boolean;
  onReveal: (id: string | null) => void; onOpen: () => void; onPin: () => void; onDelete: () => void;
};

export function HistoryRow(props: Props) {
  const { ui, IOS, isDark } = useTheme();
  const latest = useRef(props); latest.current = props;
  const x = useRef(new Animated.Value(0)).current;
  const origin = useRef(0);
  useEffect(() => {
    const animation = Animated.spring(x, { toValue: props.revealed ? -ACTION_WIDTH : 0, speed: 24, bounciness: 0, useNativeDriver: Platform.OS !== 'web' });
    animation.start(); return () => animation.stop();
  }, [props.revealed, x]);
  const gesture = useRef(PanResponder.create({
    onMoveShouldSetPanResponderCapture: (_event, state) => !latest.current.disabled && Math.abs(state.dx) > 10 && Math.abs(state.dx) > Math.abs(state.dy) * 1.4,
    onMoveShouldSetPanResponder: (_event, state) => !latest.current.disabled && Math.abs(state.dx) > 10 && Math.abs(state.dx) > Math.abs(state.dy) * 1.4,
    onPanResponderTerminationRequest: () => false,
    onPanResponderGrant: () => { origin.current = latest.current.revealed ? -ACTION_WIDTH : 0; x.stopAnimation(); },
    onPanResponderMove: (_event, state) => x.setValue(Math.min(0, Math.max(-ACTION_WIDTH, origin.current + state.dx))),
    onPanResponderRelease: (_event, state) => {
      const open = origin.current + state.dx < -ACTION_WIDTH * .4;
      latest.current.onReveal(open ? latest.current.item.id : null);
      Animated.spring(x, { toValue: open ? -ACTION_WIDTH : 0, speed: 24, bounciness: 0, useNativeDriver: Platform.OS !== 'web' }).start();
    },
    onPanResponderTerminate: () => Animated.spring(x, { toValue: latest.current.revealed ? -ACTION_WIDTH : 0, useNativeDriver: Platform.OS !== 'web' }).start(),
  })).current;
  return <View testID={'history-row-' + props.item.id} style={{ overflow: 'hidden', borderRadius: 12, marginBottom: 4 }} {...gesture.panHandlers}>
    <View pointerEvents={props.revealed ? 'auto' : 'none'} accessibilityElementsHidden={!props.revealed} importantForAccessibility={props.revealed ? 'auto' : 'no-hide-descendants'} aria-hidden={!props.revealed}
      style={{ position: 'absolute', right: 0, top: 0, bottom: 0, width: ACTION_WIDTH, flexDirection: 'row', paddingVertical: 4, gap: 4 }}>
      <Pressable accessibilityRole="button" accessibilityLabel={props.item.is_pinned ? 'Bỏ ghim cuộc trò chuyện' : 'Ghim cuộc trò chuyện'} disabled={props.disabled} onPress={props.onPin} style={({ pressed }) => ({ flex: 1, minHeight: 54, alignItems: 'center', justifyContent: 'center', gap: 6, borderRadius: 12, backgroundColor: isDark ? '#343640' : '#E6E8EE', opacity: pressed ? .65 : 1 })}>
        {props.busy ? <ActivityIndicator color={IOS.label} /> : <Ionicons name={props.item.is_pinned ? 'pin-outline' : 'pin'} size={21} color={IOS.label} />}<Text style={{ color: IOS.label, fontSize: 13 }}>{props.item.is_pinned ? 'Bỏ ghim' : 'Ghim'}</Text>
      </Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel="Xóa cuộc trò chuyện" disabled={props.disabled} onPress={props.onDelete} style={({ pressed }) => ({ flex: 1, minHeight: 54, alignItems: 'center', justifyContent: 'center', gap: 6, borderRadius: 12, backgroundColor: '#D94E49', opacity: pressed ? .65 : 1 })}>
        <Ionicons name="trash-outline" size={21} color="#FFF" /><Text style={{ color: '#FFF', fontSize: 13 }}>Xóa</Text>
      </Pressable>
    </View>
    <Animated.View style={{ transform: [{ translateX: x }], flexDirection: 'row', alignItems: 'center', backgroundColor: isDark ? '#101114' : '#F5F5F7' }}>
      <Pressable accessibilityRole="button" accessibilityLabel={props.item.title} accessibilityState={{ selected: props.selected }} disabled={props.disabled}
        onPress={() => props.revealed ? props.onReveal(null) : props.onOpen()} onLongPress={() => props.onReveal(props.revealed ? null : props.item.id)}
        style={[ui.historyRow, { flex: 1, minWidth: 0, paddingRight: 0 }, props.selected && { borderColor: IOS.label }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>{props.item.is_pinned ? <Ionicons name="pin" size={13} color={IOS.secondary} /> : null}<Text numberOfLines={2} style={[ui.listTitle, { flex: 1 }]}>{props.item.title}</Text></View>
        <Text style={ui.caption}>{new Date(props.item.updated_at).toLocaleDateString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', day: 'numeric', month: 'numeric' })}</Text>
      </Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel={'Thao tác: ' + props.item.title} accessibilityState={{ expanded: props.revealed }} disabled={props.disabled} onPress={() => props.onReveal(props.revealed ? null : props.item.id)} style={{ width: 44, minHeight: 60, alignItems: 'center', justifyContent: 'center' }}><Ionicons name="ellipsis-horizontal" size={19} color={IOS.secondary} /></Pressable>
    </Animated.View>
  </View>;
}
