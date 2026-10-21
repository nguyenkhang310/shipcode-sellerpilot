import { Ionicons } from '@expo/vector-icons';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { ManagementData } from '../../api/types';
import { useTheme } from '../../theme/ThemeProvider';
import type { ManagementRoute } from './DashboardScreen';
import { SalesTrend } from './ManagementCharts';
import { matchesPeriod } from './dates';
import { count, money } from './formatters';

type Props = {
  data: ManagementData; days: number; selectedDate: string | null; loading: boolean; refreshing: boolean; error: string;
  onOpen: (route: ManagementRoute) => void;
};

/** Period-bound values stay inside one stable layout, including pending/error states. */
export function PerformanceOverview({ data, days, selectedDate, loading, refreshing, error, onOpen }: Props) {
  const { IOS, isDark, BRAND } = useTheme();
  const ready = matchesPeriod(data, days, selectedDate);
  const muted = isDark ? '#ADB6C3' : '#626D7C';
  const line = isDark ? '#333B47' : '#E0E5EC';
  const accent = BRAND.orangeInk;
  const change = ready ? data.change_percent : null;
  const changeInk = change !== null && change < 0 ? (isDark ? '#F0B1A8' : '#A54238') : (isDark ? '#A2D9BC' : '#287251');
  const shown = (value: number | undefined, currency = false) => ready && value !== undefined ? currency ? money(value) : count(value) : '—';
  const metrics = [
    { label: 'Đơn hợp lệ', value: shown(data.order_count), testID: 'dashboard-order-count', status: undefined },
    { label: 'Trung bình mỗi đơn', value: shown(data.average_order_vnd, true), testID: undefined, status: undefined },
  ];
  return <View testID="period-summary" accessibilityLabel={ready ? `Số liệu ${selectedDate || days + " ngày"}` : `${loading ? 'Đang tải' : 'Chưa có'} số liệu ${selectedDate || days + " ngày"}`}>
    <View style={s.headline}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}><View style={{ width: 4, height: 14, borderRadius: 2, backgroundColor: BRAND.orange }} /><Text style={[s.overline, { color: muted }]}>GIÁ TRỊ ĐƠN HÀNG</Text></View>
      <View style={s.amountRow}>
        <Text numberOfLines={1} adjustsFontSizeToFit style={[s.amount, { color: IOS.label }]}>{shown(data.order_value_vnd)}</Text>
        <Text style={[s.currency, { color: muted }]}>₫</Text>
      </View>
      <View style={s.comparison}>
        <View style={s.delta}>
          {change !== null ? <><Ionicons name={change >= 0 ? 'trending-up-outline' : 'trending-down-outline'} size={16} color={changeInk} /><Text style={[s.deltaText, { color: changeInk }]}>{change > 0 ? '+' : ''}{change}%</Text></> : <Text style={[s.note, { color: muted }]}>—</Text>}
        </View>
        <Text numberOfLines={2} style={[s.note, { color: muted, flex: 1 }]}>{ready ? change !== null ? 'So với cùng thời lượng kỳ trước' : 'Chưa có dữ liệu kỳ trước để so sánh' : 'Đang chờ số liệu kỳ này'}</Text>
      </View>
    </View>
    <View style={[s.metrics, { borderTopColor: line, borderBottomColor: line }]}>{metrics.map((metric, index) => <Pressable key={metric.label} accessibilityRole="button" onPress={() => onOpen({ kind: 'orders', status: metric.status })} style={({ pressed }) => [s.metric, index > 0 && { borderLeftWidth: StyleSheet.hairlineWidth, borderColor: line, paddingLeft: 18 }, { opacity: pressed ? .65 : 1 }]}>
      <Text style={[s.note, { color: muted }]}>{metric.label}</Text>
      <View style={s.metricValueRow}><Text testID={metric.testID} numberOfLines={1} adjustsFontSizeToFit style={[s.metricValue, { color: IOS.label }]}>{metric.value}</Text><Ionicons name="arrow-forward" size={14} color={muted} /></View>
    </Pressable>)}</View>
    <View style={[s.chart, { backgroundColor: IOS.card, borderColor: line }]}>
      <View style={s.chartTitleRow}><View style={{ flex: 1 }}><Text style={[s.chartTitle, { color: IOS.label }]}>Diễn biến đơn hàng</Text><Text style={[s.note, { color: muted, marginTop: 3 }]}>Giá trị theo thời điểm đặt đơn</Text></View></View>
      <SalesTrend data={data} days={days} selectedDate={selectedDate} pending={!ready} />
      <View style={[s.ledger, { borderColor: line }]}>
        <Pressable accessibilityRole="button" onPress={() => onOpen({ kind: 'orders', status: 'delivered' })} style={s.ledgerItem}><View style={s.ledgerLabel}><View style={[s.dot, { backgroundColor: isDark ? '#86B5A0' : '#4C816B' }]} /><Text style={[s.note, { color: muted, flex: 1 }]}>Giá trị đã giao</Text></View><Text numberOfLines={1} adjustsFontSizeToFit style={[s.ledgerValue, { color: IOS.label }]}>{shown(data.delivered_value_vnd, true)}</Text></Pressable>
        <Pressable accessibilityRole="button" onPress={() => onOpen({ kind: 'orders', status: 'cancelled' })} style={[s.ledgerItem, { paddingLeft: 16, borderLeftWidth: StyleSheet.hairlineWidth, borderColor: line }]}><View style={s.ledgerLabel}><View style={[s.dot, { backgroundColor: isDark ? '#B2B8C3' : '#9099A6' }]} /><Text style={[s.note, { color: muted, flex: 1 }]}>Đơn đã hủy</Text></View><Text numberOfLines={1} adjustsFontSizeToFit style={[s.ledgerValue, { color: IOS.label }]}>{shown(data.order_status_counts?.cancelled)}</Text></Pressable>
      </View>
    </View>
    <View style={s.status}>
      {loading && !refreshing ? <ActivityIndicator testID="period-loading" size="small" color={accent} /> : <Ionicons name={error ? 'alert-circle-outline' : 'information-circle-outline'} size={14} color={error ? IOS.red : muted} />}
      <Text accessibilityLiveRegion="polite" numberOfLines={2} style={[s.note, { color: error ? IOS.red : muted, flex: 1 }]}>{error || (loading ? 'Đang lấy số liệu kỳ này…' : 'Đơn hợp lệ không gồm đơn hủy / hoàn.')}</Text>
    </View>
  </View>;
}

const s = StyleSheet.create({
  headline: { paddingTop: 12, paddingBottom: 20 },
  overline: { fontSize: 11, lineHeight: 18, fontWeight: '600', letterSpacing: 1.2 },
  amountRow: { flexDirection: 'row', alignItems: 'baseline', gap: 8, marginTop: 6, minHeight: 58 },
  amount: { fontSize: 46, lineHeight: 58, fontWeight: '600', letterSpacing: -2, fontVariant: ['tabular-nums'], flexShrink: 1 },
  currency: { fontSize: 23, lineHeight: 32 },
  comparison: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 38, marginTop: 5 },
  delta: { flexDirection: 'row', gap: 4, alignItems: 'center', minWidth: 60 }, deltaText: { fontSize: 13, lineHeight: 20, fontWeight: '600', fontVariant: ['tabular-nums'] },
  note: { fontSize: 12, lineHeight: 18 },
  metrics: { flexDirection: 'row', paddingVertical: 17, borderTopWidth: StyleSheet.hairlineWidth, borderBottomWidth: StyleSheet.hairlineWidth, marginBottom: 22 },
  metric: { flex: 1, minWidth: 0, paddingRight: 10, minHeight: 51 },
  metricValueRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 6 },
  metricValue: { fontSize: 22, lineHeight: 28, letterSpacing: -.6, fontWeight: '600', fontVariant: ['tabular-nums'], flexShrink: 1 },
  chart: { borderRadius: 22, borderWidth: StyleSheet.hairlineWidth, padding: 18 },
  chartTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 12 }, chartTitle: { fontSize: 16, lineHeight: 23, fontWeight: '600', letterSpacing: -.2 },
  ledger: { flexDirection: 'row', borderTopWidth: StyleSheet.hairlineWidth, paddingTop: 16, marginTop: 9 },
  ledgerItem: { flex: 1, minWidth: 0, minHeight: 58, paddingRight: 8 }, ledgerLabel: { flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: 20 }, dot: { width: 5, height: 5, borderRadius: 3 },
  ledgerValue: { fontSize: 18, lineHeight: 26, fontWeight: '600', fontVariant: ['tabular-nums'], letterSpacing: -.3, marginTop: 6 },
  status: { flexDirection: 'row', alignItems: 'center', gap: 7, minHeight: 48, paddingHorizontal: 2 },
});
