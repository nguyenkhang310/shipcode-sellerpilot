import { useRef, useState } from 'react';
import { Pressable, Text, View, ViewInstance } from 'react-native';
import Svg, { Circle, Line, Path, Text as SvgText } from 'react-native-svg';
import { ReportChart as Chart, ReportUnit } from '../../api/types';
import { count, money } from '../dashboard/formatters';
import { useTheme } from '../../theme/ThemeProvider';

export function reportValue(value: number | null, unit: ReportUnit): string {
  if (value === null || !Number.isFinite(value)) return '—';
  return unit === 'vnd' ? money(value) : unit === 'percent'
    ? value.toLocaleString('vi-VN', { maximumFractionDigits: 1 }) + '%' : count(value);
}

export function reportLabel(label: string): string {
  if (!/^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2})?$/.test(label)) return label;
  const date = label.slice(8, 10) + '/' + label.slice(5, 7);
  return label.includes('T') ? label.slice(11, 16) + ' · ' + date : date;
}

function axisValue(value: number): string {
  const scale = value >= 1e9 ? 1e9 : value >= 1e6 ? 1e6 : value >= 1e3 ? 1e3 : 1;
  return (value / scale).toLocaleString('vi-VN', { maximumFractionDigits: 1 })
    + (scale === 1e9 ? ' tỷ' : scale === 1e6 ? ' tr' : scale === 1e3 ? ' k' : '');
}

export function ReportChart({ chart }: { chart: Chart }) {
  const { IOS, BRAND, ui } = useTheme();
  const plot = useRef<ViewInstance>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [expanded, setExpanded] = useState(false);
  const points = chart.points;
  const visibleBars = points.length > 6 && !expanded ? points.slice(0, 4) : points;
  const max = Math.max(1, ...points.map(p => p.value));
  const picked = selected === null ? null : points[selected];
  const positions = points.map((p, i) => ({
    x: points.length === 1 ? 180 : 50 + i * 254 / Math.max(1, points.length - 1),
    y: 124 - p.value / max * 100,
  }));
  const path = positions.map((p, i) => `${i ? 'L' : 'M'}${p.x},${p.y}`).join(' ');
  const marks = [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])].filter(i => i >= 0);
  return <View testID="chat-report-chart" style={{ gap: 10 }}>
    <Text style={[ui.caption, { color: IOS.label, fontWeight: '600' }]}>{chart.title}</Text>
    {chart.kind === 'bar' ? <View style={{ gap: 10 }}>
      {visibleBars.map((p, i) => <View key={i} accessible accessibilityLabel={`${p.label}: ${reportValue(p.value, chart.unit)}`}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12, marginBottom: 3 }}>
          <Text numberOfLines={2} style={[ui.caption, { flex: 1, color: IOS.label }]}>{p.label}</Text>
          <Text style={[ui.caption, { color: IOS.label, fontVariant: ['tabular-nums'], fontWeight: '600' }]}>{reportValue(p.value, chart.unit)}</Text>
        </View>
        <View style={{ height: 4, borderRadius: 2, backgroundColor: IOS.fill, overflow: 'hidden' }}>
          <View style={{ height: 4, width: `${p.value / max * 100}%`, borderRadius: 2, backgroundColor: BRAND.orange }} />
        </View>
      </View>)}
      {points.length > 6 ? <Pressable accessibilityRole="button" onPress={() => setExpanded(value => !value)}
        style={{ minHeight: 44, justifyContent: 'center' }}>
        <Text style={[ui.caption, { color: BRAND.orangeInk }]}>{expanded ? 'Thu gọn biểu đồ' : `Xem đủ ${points.length} mục`}</Text>
      </Pressable> : null}
    </View> : <View>
      <Text accessibilityLiveRegion="polite" style={[ui.caption, { minHeight: 24, color: IOS.label }]}>
        {picked ? `${reportLabel(picked.label)} · ${reportValue(picked.value, chart.unit)}` : 'Chạm biểu đồ để xem từng mốc'}
      </Text>
      <Pressable ref={plot} testID="chat-report-trend" disabled={!points.length}
        accessibilityRole="adjustable" accessibilityLabel={chart.title}
        aria-valuemin={0} aria-valuemax={Math.max(0, points.length - 1)} aria-valuenow={selected ?? 0}
        aria-valuetext={picked ? `${reportLabel(picked.label)}: ${reportValue(picked.value, chart.unit)}` : 'Chọn mốc thời gian'}
        accessibilityActions={[{ name: 'increment', label: 'Mốc tiếp theo' }, { name: 'decrement', label: 'Mốc trước' }]}
        onAccessibilityAction={event => setSelected(Math.max(0, Math.min(points.length - 1,
          (selected ?? 0) + (event.nativeEvent.actionName === 'increment' ? 1 : -1))))}
        onPress={event => {
          const x = event.nativeEvent.pageX;
          plot.current?.measureInWindow((left, _top, width) => {
            if (!width || !Number.isFinite(x)) return;
            setSelected(Math.max(0, Math.min(points.length - 1, Math.round(((x - left) / width * 320 - 50) / 254 * (points.length - 1)))));
          });
        }}>
        <Svg width="100%" height={166} viewBox="0 0 320 166" accessible={false}>
          {[0, 0.5, 1].map(part => <Line key={part} x1={50} x2={304} y1={124 - part * 100} y2={124 - part * 100} stroke={IOS.separator} strokeDasharray="3 5" />)}
          {[0, 1].map(part => <SvgText key={part} x={0} y={128 - part * 100} fontSize={11} fill={IOS.secondary}>{axisValue(max === 1 && !points.some(p => p.value) ? 0 : max * part)}</SvgText>)}
          {positions.length > 1 ? <Path d={path + ' L304,124 L50,124 Z'} fill={BRAND.orange} fillOpacity={0.08} /> : null}
          {positions.length ? <Path d={path} stroke={BRAND.orange} strokeWidth={2.5} fill="none" strokeLinejoin="round" strokeLinecap="round" /> : null}
          {(selected !== null && positions[selected] ? [selected] : positions.length === 1 ? [0] : []).map(i => <Circle key={i} cx={positions[i]!.x} cy={positions[i]!.y} r={4} fill={BRAND.orange} stroke={IOS.card} strokeWidth={2} />)}
          {marks.map(i => <SvgText key={i} x={positions[i]!.x} y={151} fontSize={11} fill={IOS.secondary}
            textAnchor={i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'}>{reportLabel(points[i]!.label).split(' · ')[0]}</SvgText>)}
        </Svg>
      </Pressable>
    </View>}
    {!points.length || points.every(p => p.value === 0) ? <Text style={ui.caption}>Chưa có số liệu phát sinh trong phạm vi này.</Text> : null}
  </View>;
}
