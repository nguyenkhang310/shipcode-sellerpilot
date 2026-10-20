import { useRef, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import Svg, { Circle, Defs, Line, LinearGradient, Path, Stop, Text as SvgText } from 'react-native-svg';
import { ManagementData } from '../../api/types';
import { useTheme } from '../../theme/ThemeProvider';
import { count, money } from './formatters';

function shortMoney(value: number) {
  if (value >= 1_000_000_000) return (value / 1_000_000_000).toLocaleString('vi-VN', { maximumFractionDigits: 1 }) + ' tỷ';
  if (value >= 1_000_000) return (value / 1_000_000).toLocaleString('vi-VN', { maximumFractionDigits: 1 }) + ' tr';
  if (value >= 1_000) return (value / 1_000).toLocaleString('vi-VN', { maximumFractionDigits: 0 }) + ' k';
  return String(value);
}
function pointLabel(date: string, hourly: boolean) {
  return hourly ? date.slice(11, 16) : date.slice(8, 10) + '/' + date.slice(5, 7);
}

type ChartProps = { data: ManagementData; days: number; pending: boolean };

export function SalesTrend({ data, days, pending }: ChartProps) {
  const { ui, IOS, isDark, BRAND } = useTheme();
  const [selection, setSelection] = useState<{ days: number; index: number } | null>(null);
  const chart = useRef<View>(null);
  const series = pending ? [] : data.series;
  const selected = selection?.days === days ? selection.index : null;
  const index = selected === null ? null : Math.min(selected, series.length - 1);
  const max = Math.max(1, ...series.map(point => point.value));
  const ceiling = max === 1 ? 1 : Math.ceil(max / 10 ** Math.floor(Math.log10(max))) * 10 ** Math.floor(Math.log10(max));
  const points = series.map((point, i) => ({ x: 44 + i * 270 / Math.max(1, series.length - 1), y: 135 - point.value / ceiling * 115 }));
  // Control points share endpoint y values: softer joins without inventing
  // peaks/negative values between observed data points.
  const path = points.map((point, i) => {
    const previous = points[i - 1];
    if (!previous) return `M${point.x},${point.y}`;
    const mid = (previous.x + point.x) / 2;
    return `C${mid},${previous.y} ${mid},${point.y} ${point.x},${point.y}`;
  }).join(' ');
  const dark = isDark;
  const accent = BRAND.orange;
  const captionColor = IOS.secondary;
  const valueColor = IOS.label;
  const focus = index !== null && index >= 0 ? points[index] : null;
  const picked = index !== null && index >= 0 ? series[index] : null;
  const marks = series.length ? [...new Set([0, Math.floor((series.length - 1) / 2), series.length - 1])].filter(i => i >= 0) : [];
  return <View style={{ marginTop: 16 }}>
    <View style={[ui.between, { minHeight: 25, marginBottom: 4 }]}><Text style={[ui.caption, { color: captionColor }]}>{picked ? pointLabel(picked.date, days === 1) : days === 1 ? 'Theo giờ · Hôm nay' : 'Theo ngày · ' + days + ' ngày'}</Text><Text style={[ui.caption, { fontWeight: '600', color: valueColor }]}>{picked ? money(picked.value) : pending ? '—' : 'VND'}</Text></View>
    <Pressable disabled={pending || !series.length} ref={chart} testID="sales-chart" accessibilityRole="adjustable" accessibilityState={{ disabled: pending || !series.length }} accessibilityLabel="Biểu đồ giá trị đơn hàng" aria-valuemin={0} aria-valuemax={Math.max(0, series.length - 1)} aria-valuenow={index ?? 0} aria-valuetext={pending ? 'Chưa có số liệu kỳ này' : picked ? pointLabel(picked.date, days === 1) + ': ' + money(picked.value) : 'Chọn mốc để xem giá trị đơn hàng'} accessibilityActions={[{ name: 'increment', label: 'Mốc tiếp theo' }, { name: 'decrement', label: 'Mốc trước' }]}
      onAccessibilityAction={event => {
        if (pending || !series.length) return;
        setSelection({ days, index: Math.max(0, Math.min(series.length - 1, (selected ?? 0) + (event.nativeEvent.actionName === 'increment' ? 1 : -1))) });
      }}
      onPress={event => {
        const pageX = event.nativeEvent.pageX;
        // SVG children report different local origins. Measure the whole plot
        // so taps resolve to the same time slot on iOS and web.
        chart.current?.measureInWindow((left, _top, width) => {
          if (!width || !Number.isFinite(pageX)) return;
          setSelection({ days, index: Math.max(0, Math.min(series.length - 1, Math.round(((pageX - left) / width * 324 - 44) / 270 * (series.length - 1)))) });
        });
      }}>
      <Svg width="100%" height={170} viewBox="0 0 324 170">
        <Defs><LinearGradient id="sales-shade" x1={0} y1={0} x2={0} y2={1}><Stop offset={0} stopColor={accent} stopOpacity={0.22} /><Stop offset={1} stopColor={accent} stopOpacity={0.015} /></LinearGradient></Defs>
        {[0, .5, 1].map(part => <ViewlessGrid key={part} y={135 - part * 115} label={pending ? '—' : shortMoney(ceiling * part)} dark={dark} />)}
        {points.length ? <><Path d={path + ` L${points[points.length - 1]!.x},135 L44,135 Z`} fill="url(#sales-shade)" /><Path d={path} stroke={accent} strokeWidth={2.5} fill="none" strokeLinecap="round" strokeLinejoin="round" />{points.length === 1 ? <Circle cx={44} cy={points[0]!.y} r={4} fill={accent} /> : null}</> : null}
        {focus ? <><Line x1={focus.x} x2={focus.x} y1={15} y2={135} stroke={accent} strokeDasharray="3 4" /><Circle cx={focus.x} cy={focus.y} r={5} fill="#D9A53B" stroke={dark ? '#1C2330' : '#FFF'} strokeWidth={2} /></> : null}
        {marks.map(i => <SvgText key={i} x={points[i]!.x} y={160} fontSize={12} fill={captionColor} textAnchor={i === 0 ? 'start' : i === series.length - 1 ? 'end' : 'middle'}>{pointLabel(series[i]!.date, days === 1)}</SvgText>)}
      </Svg>
    </Pressable>
  </View>;
}
function ViewlessGrid({ y, label, dark }: { y: number; label: string; dark: boolean }) {
  return <><Line x1={44} x2={314} y1={y} y2={y} stroke={dark ? '#344052' : '#E7ECF2'} strokeDasharray="3 5" /><SvgText x={0} y={y + 3} fontSize={11} fill={dark ? '#A5ADBA' : '#748091'}>{label}</SvgText></>;
}

export function OrderDistribution({ data, days, pending }: ChartProps) {
  const { ui, isDark } = useTheme();
  const counts = pending ? {} : data.order_status_counts || {};
  const groups = [
    { label: 'Chờ xử lý', value: (counts.pending || 0) + (counts.paid || 0), color: '#DDB451' },
    { label: 'Đang giao', value: counts.shipped || 0, color: '#648CB6' },
    { label: 'Đã giao', value: counts.delivered || 0, color: '#66A28A' },
    { label: 'Hủy / Hoàn', value: (counts.cancelled || 0) + (counts.returned || 0), color: '#B7BDC8' },
  ];
  const total = groups.reduce((sum, group) => sum + group.value, 0);
  return <View testID="order-distribution" style={[ui.distributionCard, { borderRadius: 24, padding: 19 }]}>
    <View style={[ui.between, { marginBottom: 14 }]}><Text style={ui.listTitle}>Trạng thái đơn</Text><Text style={ui.caption}>{days === 1 ? 'Hôm nay' : days + ' ngày'}</Text></View>
    <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 6, minHeight: 38 }} accessibilityLabel={pending ? 'Chưa có số liệu kỳ này' : count(total) + ' đơn trong kỳ'}>
      <Text style={[ui.metricValue, { fontSize: 29, marginVertical: 0, letterSpacing: -.8 }]}>{pending ? '—' : count(total)}</Text><Text style={ui.caption}>đơn trong kỳ</Text>
    </View>
    <View style={{ flexDirection: 'row', gap: 3, height: 10, borderRadius: 5, overflow: 'hidden', backgroundColor: isDark ? '#303A49' : '#EDF0F4', marginTop: 10, marginBottom: 21 }}>
      {!pending && total > 0 ? groups.filter(group => group.value > 0).map(group => <View key={group.label} style={{ flex: group.value, backgroundColor: group.color, borderRadius: 3 }} />) : null}
    </View>
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', rowGap: 18 }}>{groups.map(group => <View key={group.label} style={{ width: '50%', paddingRight: 10 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: 22 }}><View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: group.color }} /><Text style={[ui.caption, { fontSize: 13, lineHeight: 19 }]}>{group.label}</Text></View>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 7, marginLeft: 12, minHeight: 28 }}><Text style={[ui.productName, { fontSize: 19, fontWeight: '600', fontVariant: ['tabular-nums'] }]}>{pending ? '—' : count(group.value)}</Text><Text style={[ui.caption, { fontSize: 12 }]}>{!pending && total > 0 ? Math.round(group.value / total * 100) + '%' : ' '}</Text></View>
    </View>)}</View>
  </View>;
}
