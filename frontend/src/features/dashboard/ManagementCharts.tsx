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

export function SalesTrend({ data }: { data: ManagementData }) {
  const { ui, IOS, isDark } = useTheme();
  const [selected, setSelected] = useState<number | null>(null);
  const chart = useRef<View>(null);
  const series = data.series;
  const index = selected === null ? null : Math.min(selected, series.length - 1);
  const max = Math.max(1, ...series.map(point => point.value));
  const ceiling = max === 1 ? 1 : Math.ceil(max / 10 ** Math.floor(Math.log10(max))) * 10 ** Math.floor(Math.log10(max));
  const points = series.map((point, i) => ({ x: 44 + i * 270 / Math.max(1, series.length - 1), y: 135 - point.value / ceiling * 115 }));
  const path = points.map((point, i) => `${i ? 'L' : 'M'}${point.x},${point.y}`).join(' ');
  const accent = isDark ? '#A4C0E1' : '#547CA5';
  const focus = index !== null && index >= 0 ? points[index] : null;
  const picked = index !== null && index >= 0 ? series[index] : null;
  const marks = series.length ? [...new Set([0, Math.floor((series.length - 1) / 2), series.length - 1])].filter(i => i >= 0) : [];
  return <View style={{ marginTop: 16 }}>
    <View style={[ui.between, { minHeight: 25, marginBottom: 4 }]}><Text style={ui.caption}>{picked ? pointLabel(picked.date, data.days === 1) : data.days === 1 ? 'Theo giờ · Hôm nay' : 'Theo ngày · ' + data.days + ' ngày'}</Text><Text style={[ui.caption, { fontWeight: '600', color: IOS.label }]}>{picked ? money(picked.value) : 'VND'}</Text></View>
    <Pressable ref={chart} testID="sales-chart" accessibilityRole="adjustable" accessibilityLabel="Biểu đồ giá trị đơn hàng" aria-valuemin={0} aria-valuemax={Math.max(0, series.length - 1)} aria-valuenow={index ?? 0} aria-valuetext={picked ? pointLabel(picked.date, data.days === 1) + ': ' + money(picked.value) : 'Chọn mốc để xem giá trị đơn hàng'} accessibilityActions={[{ name: 'increment', label: 'Mốc tiếp theo' }, { name: 'decrement', label: 'Mốc trước' }]}
      onAccessibilityAction={event => setSelected(previous => Math.max(0, Math.min(series.length - 1, (previous ?? 0) + (event.nativeEvent.actionName === 'increment' ? 1 : -1))))}
      onPress={event => {
        const pageX = event.nativeEvent.pageX;
        // SVG children report different local origins. Measure the whole plot
        // so taps resolve to the same time slot on iOS and web.
        chart.current?.measureInWindow((left, _top, width) => {
          if (!width || !Number.isFinite(pageX)) return;
          setSelected(Math.max(0, Math.min(series.length - 1, Math.round(((pageX - left) / width * 324 - 44) / 270 * (series.length - 1)))));
        });
      }}>
      <Svg width="100%" height={170} viewBox="0 0 324 170">
        <Defs><LinearGradient id="sales-shade" x1="0" y1="0" x2="0" y2="1"><Stop offset="0" stopColor={accent} stopOpacity=".22" /><Stop offset="1" stopColor={accent} stopOpacity=".015" /></LinearGradient></Defs>
        {[0, .5, 1].map(part => <ViewlessGrid key={part} y={135 - part * 115} label={shortMoney(ceiling * part)} dark={isDark} />)}
        {points.length ? <><Path d={path + ` L${points[points.length - 1]!.x},135 L44,135 Z`} fill="url(#sales-shade)" /><Path d={path} stroke={accent} strokeWidth={2.5} fill="none" strokeLinecap="round" strokeLinejoin="round" />{points.length === 1 ? <Circle cx={44} cy={points[0]!.y} r={4} fill={accent} /> : null}</> : null}
        {focus ? <><Line x1={focus.x} x2={focus.x} y1={15} y2={135} stroke={accent} strokeDasharray="3 4" /><Circle cx={focus.x} cy={focus.y} r={5} fill="#D9A53B" stroke={isDark ? '#1C2330' : '#FFF'} strokeWidth={2} /></> : null}
        {marks.map(i => <SvgText key={i} x={points[i]!.x} y={160} fontSize={10} fill={IOS.secondary} textAnchor={i === 0 ? 'start' : i === series.length - 1 ? 'end' : 'middle'}>{pointLabel(series[i]!.date, data.days === 1)}</SvgText>)}
      </Svg>
    </Pressable>
  </View>;
}
function ViewlessGrid({ y, label, dark }: { y: number; label: string; dark: boolean }) {
  return <><Line x1={44} x2={314} y1={y} y2={y} stroke={dark ? '#344052' : '#E7ECF2'} strokeDasharray="3 5" /><SvgText x={0} y={y + 3} fontSize={10} fill={dark ? '#A5ADBA' : '#748091'}>{label}</SvgText></>;
}

export function OrderDistribution({ data }: { data: ManagementData }) {
  const { ui, isDark } = useTheme();
  const counts = data.order_status_counts || {};
  const groups = [
    { label: 'Chờ xử lý', value: (counts.pending || 0) + (counts.paid || 0), color: '#DDB451' },
    { label: 'Đang giao', value: counts.shipped || 0, color: '#648CB6' },
    { label: 'Đã giao', value: counts.delivered || 0, color: '#66A28A' },
    { label: 'Hủy / Hoàn', value: (counts.cancelled || 0) + (counts.returned || 0), color: '#B7BDC8' },
  ];
  const total = groups.reduce((sum, group) => sum + group.value, 0);
  const circumference = 2 * Math.PI * 44;
  let offset = 0;
  return <View style={ui.distributionCard}>
    <View style={[ui.between, { marginBottom: 18 }]}><Text style={ui.listTitle}>Trạng thái đơn</Text><Text style={ui.caption}>{data.days === 1 ? 'Hôm nay' : data.days + ' ngày'}</Text></View>
    <View style={[ui.row, { gap: 20 }]}>
      <View style={{ width: 114, height: 114, alignItems: 'center', justifyContent: 'center' }} accessibilityLabel={count(total) + ' đơn trong kỳ'}>
        <Svg width={114} height={114} viewBox="0 0 114 114" style={{ position: 'absolute' }}><Circle cx={57} cy={57} r={44} fill="none" stroke={isDark ? '#303A49' : '#EEF1F5'} strokeWidth={11} />{groups.map(group => {
          const length = total ? group.value / total * circumference : 0;
          const segment = length ? <Circle key={group.label} cx={57} cy={57} r={44} fill="none" stroke={group.color} strokeWidth={11} strokeDasharray={`${Math.max(0, length - (group.value === total ? 0 : 3))} ${circumference}`} strokeDashoffset={-offset} transform="rotate(-90 57 57)" /> : null;
          offset += length; return segment;
        })}</Svg>
        <Text style={[ui.metricValue, { marginVertical: 0, fontSize: 25 }]}>{count(total)}</Text><Text style={[ui.caption, { fontSize: 11 }]}>đơn hàng</Text>
      </View>
      <View style={{ flex: 1, gap: 13 }}>{groups.map(group => <View key={group.label} style={[ui.between, { gap: 6 }]}><View style={[ui.row, { gap: 7, flex: 1 }]}><View style={{ width: 7, height: 7, borderRadius: 3, backgroundColor: group.color }} /><Text style={[ui.caption, { flexShrink: 1 }]}>{group.label}</Text></View><Text style={[ui.productName, { fontWeight: '600', fontVariant: ['tabular-nums'] }]}>{count(group.value)}</Text></View>)}</View>
    </View>
  </View>;
}
