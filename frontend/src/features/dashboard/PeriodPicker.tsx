import { Ionicons } from '@expo/vector-icons';
import { useEffect, useRef, useState } from 'react';
import { Animated, Easing, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../../theme/ThemeProvider';
import { displayDate, shiftDay, todayInShop } from './dates';

const choices = [[1, 'Hôm nay'], [7, '7 ngày'], [30, '30 ngày']] as const;
const monthOf = (date: string) => date.slice(0, 7) + '-01';
const shiftMonth = (month: string, delta: number) => {
  const date = new Date(month + 'T12:00:00Z'); date.setUTCMonth(date.getUTCMonth() + delta);
  return date.toISOString().slice(0, 10);
};

export function PeriodPicker({ days, date, onDays, onDate, reduceMotion }: {
  days: number; date: string | null; onDays: (days: number) => void; onDate: (date: string) => void; reduceMotion: boolean;
}) {
  const { IOS, BRAND, ui, isDark } = useTheme();
  const insets = useSafeAreaInsets();
  const today = todayInShop();
  const [open, setOpen] = useState(false), [pending, setPending] = useState(date || today), [month, setMonth] = useState(monthOf(date || today));
  const [width, setWidth] = useState(0);
  const selection = date ? 3 : Math.max(0, choices.findIndex(([value]) => value === days));
  const x = useRef(new Animated.Value(0)).current, measured = useRef(0);
  const cellWidth = Math.max(0, (width - 8) / 4);
  useEffect(() => {
    if (measured.current !== cellWidth || reduceMotion) { measured.current = cellWidth; x.setValue(selection * cellWidth); return; }
    const animation = Animated.timing(x, { toValue: selection * cellWidth, duration: 210, easing: Easing.out(Easing.cubic), useNativeDriver: Platform.OS !== 'web', isInteraction: false });
    animation.start(); return () => animation.stop();
  }, [selection, cellWidth, reduceMotion, x]);
  const show = () => { setPending(date || today); setMonth(monthOf(date || today)); setOpen(true); };
  const firstWeekday = (new Date(month + 'T12:00:00Z').getUTCDay() + 6) % 7;
  const nextMonth = shiftMonth(month, 1);
  const length = new Date(shiftDay(nextMonth, -1) + 'T12:00:00Z').getUTCDate();
  const cells = Array.from({ length: 42 }, (_, index) => {
    const day = index - firstWeekday + 1;
    return day > 0 && day <= length ? month.slice(0, 8) + String(day).padStart(2, '0') : null;
  });
  const chosenDay = date || today;
  return <>
    <View testID="period-picker" onLayout={event => setWidth(event.nativeEvent.layout.width)} style={[s.segment, { borderColor: IOS.separator, backgroundColor: isDark ? '#17191E' : '#ECEEF2' }]}>
      {cellWidth ? <Animated.View testID="period-indicator" pointerEvents="none" style={[s.indicator, { width: cellWidth, transform: [{ translateX: x }], backgroundColor: BRAND.orangeSoft, borderColor: isDark ? '#A9653D88' : '#E5A77D' }]} /> : null}
      {choices.map(([value, label], index) => <Pressable key={value} accessibilityRole="button" accessibilityState={{ selected: selection === index }} onPress={() => onDays(value)} style={s.segmentItem}><Text style={[s.segmentText, { color: selection === index ? BRAND.orangeInk : IOS.secondary, fontWeight: selection === index ? '600' : '400' }]}>{label}</Text></Pressable>)}
      <Pressable accessibilityRole="button" accessibilityLabel="Chọn ngày xem số liệu" accessibilityState={{ selected: Boolean(date), expanded: open }} onPress={show} style={s.segmentItem}><Ionicons name="calendar-outline" size={19} color={date ? BRAND.orangeInk : IOS.secondary} /></Pressable>
    </View>
    <View style={s.dateRow}>
      <Text numberOfLines={1} style={[s.dateText, { color: IOS.secondary, flex: 1 }]}>{days === 1 ? (date ? displayDate(date) : 'Hôm nay · ' + displayDate(today)) : days + ' ngày gần nhất'}</Text>
      <Pressable accessibilityRole="button" accessibilityLabel="Xem ngày trước" disabled={days !== 1 || chosenDay <= '1970-01-01'} onPress={() => onDate(shiftDay(chosenDay, -1))} style={[s.arrow, { opacity: days === 1 ? 1 : .3 }]}><Ionicons name="chevron-back" size={18} color={IOS.label} /></Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel="Xem ngày sau" disabled={days !== 1 || chosenDay >= today} onPress={() => onDate(shiftDay(chosenDay, 1))} style={[s.arrow, { opacity: days === 1 && chosenDay < today ? 1 : .3 }]}><Ionicons name="chevron-forward" size={18} color={IOS.label} /></Pressable>
    </View>
    <Modal visible={open} transparent animationType={reduceMotion ? 'none' : 'fade'} onRequestClose={() => setOpen(false)}>
      <View style={s.overlay}>
        <Pressable accessibilityRole="button" accessibilityLabel="Đóng lịch chọn ngày" onPress={() => setOpen(false)} style={StyleSheet.absoluteFill} />
        <View accessibilityViewIsModal style={[s.calendar, { backgroundColor: IOS.card, paddingBottom: Math.max(insets.bottom, 18) }]}>
          <View style={s.calendarHeader}><Text accessibilityRole="header" style={ui.sheetTitle}>Chọn ngày</Text><Pressable accessibilityRole="button" accessibilityLabel="Đóng lịch" onPress={() => setOpen(false)} style={s.arrow}><Ionicons name="close" size={22} color={IOS.label} /></Pressable></View>
          <ScrollView style={{ flexShrink: 1, minHeight: 0 }} contentContainerStyle={{ paddingHorizontal: 10 }}>
          <View style={s.calendarHeader}>
            <Pressable accessibilityRole="button" accessibilityLabel="Tháng trước" disabled={month <= '1970-01-01'} onPress={() => setMonth(shiftMonth(month, -1))} style={s.arrow}><Ionicons name="chevron-back" size={18} color={IOS.label} /></Pressable>
            <Text accessibilityLiveRegion="polite" style={[s.month, { color: IOS.label }]}>Tháng {Number(month.slice(5, 7))}, {month.slice(0, 4)}</Text>
            <Pressable accessibilityRole="button" accessibilityLabel="Tháng sau" disabled={nextMonth > today} onPress={() => setMonth(nextMonth)} style={[s.arrow, nextMonth > today && { opacity: .3 }]}><Ionicons name="chevron-forward" size={18} color={IOS.label} /></Pressable>
          </View>
          <View style={s.week}>{['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'].map(day => <Text key={day} style={[s.weekday, { color: IOS.secondary }]}>{day}</Text>)}</View>
          {Array.from({ length: 6 }, (_, week) => <View key={week} style={s.week}>{cells.slice(week * 7, week * 7 + 7).map((value, index) => value ? <Pressable key={value} accessibilityRole="button" accessibilityLabel={'Ngày ' + displayDate(value)} accessibilityState={{ selected: value === pending, disabled: value > today }} disabled={value > today} onPress={() => setPending(value)} style={[s.day, { backgroundColor: value === pending ? BRAND.orangeSoft : 'transparent', borderColor: value === pending ? BRAND.orange : value === today ? IOS.separator : 'transparent', opacity: value > today ? .25 : 1 }]}><Text style={{ fontSize: 15, fontWeight: value === pending ? '600' : '400', color: value === pending ? BRAND.orangeInk : IOS.label }}>{Number(value.slice(8))}</Text></Pressable> : <View key={'empty-' + index} style={s.day} />)}</View>)}
          </ScrollView>
          <Pressable accessibilityRole="button" onPress={() => { onDate(pending); setOpen(false); }} style={[ui.primaryButton, { marginTop: 16, marginHorizontal: 10 }]}><Text style={ui.primaryText}>Xem ngày {displayDate(pending)}</Text></Pressable>
        </View>
      </View>
    </Modal>
  </>;
}

const s = StyleSheet.create({
  segment: { flexDirection: 'row', borderWidth: StyleSheet.hairlineWidth, borderRadius: 13, padding: 4, position: 'relative' },
  indicator: { position: 'absolute', left: 4, top: 4, bottom: 4, borderRadius: 9, borderWidth: StyleSheet.hairlineWidth },
  segmentItem: { flex: 1, minHeight: 44, alignItems: 'center', justifyContent: 'center' }, segmentText: { fontSize: 14, lineHeight: 20 },
  dateRow: { flexDirection: 'row', alignItems: 'center', minHeight: 48, marginBottom: 4 }, dateText: { fontSize: 12, lineHeight: 18 }, arrow: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  overlay: { flex: 1, justifyContent: 'flex-end', alignItems: 'center', backgroundColor: '#00000055' },
  calendar: { width: '100%', maxWidth: 460, maxHeight: '94%', paddingHorizontal: 6, paddingTop: 12, borderTopLeftRadius: 24, borderTopRightRadius: 24 },
  calendarHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 10 }, month: { fontSize: 16, fontWeight: '600' },
  week: { flexDirection: 'row', marginHorizontal: -10 }, weekday: { flex: 1, textAlign: 'center', fontSize: 12, paddingVertical: 10 },
  day: { flex: 1, height: 44, borderWidth: 1, borderColor: 'transparent', borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
});
