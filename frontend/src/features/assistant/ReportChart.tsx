import { memo, useId, useRef, useState } from 'react';
import { Platform, Pressable, Text, View, type ViewInstance } from 'react-native';
import Svg, { Circle, Defs, Line, LinearGradient, Path, Stop, Text as SvgText } from 'react-native-svg';
import { ReportChart as Chart, ReportUnit } from '../../api/types';
import { count, money } from '../dashboard/formatters';
import { useTheme } from '../../theme/ThemeProvider';
import type { LiveLanguage } from './live/locale';
import { reportText } from './reportLocale';

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

function scaleMaximum(value: number, isCount: boolean) {
  if (!value) return 1;
  const base = 10 ** Math.floor(Math.log10(value / 2));
  const step = ([1, 2, 2.5, 5, 10].find(n => n * base >= value / 2) ?? 10) * base;
  return (isCount ? Math.max(1, Math.ceil(step)) : step) * 2;
}

export const ReportChart = memo(function ReportChart({ chart, language, onInteract }: {
  chart: Chart; language?: LiveLanguage; onInteract?: () => void;
}) {
  const { IOS, BRAND, ui } = useTheme();
  const width = useRef(0);
  const plot = useRef<ViewInstance>(null);
  const en = language === 'en';
  const [selected, setSelected] = useState<number | null>(null);
  const [expanded, setExpanded] = useState(false);
  const gradient = 'report-fill-' + useId().replace(/[^A-Za-z0-9-]/g, '');
  const points = chart.points.filter(point => Number.isFinite(point.value) && point.value >= 0);
  const visibleBars = points.length > 6 && !expanded ? points.slice(0, 4) : points;
  const peak = Math.max(0, ...points.map(p => p.value));
  const max = chart.kind === 'bar' ? Math.max(1, peak) : scaleMaximum(peak, chart.unit === 'count');
  const picked = selected === null ? null : points[selected];
  const positions = points.map((p, i) => ({
    x: points.length === 1 ? 180 : 50 + i * 254 / Math.max(1, points.length - 1),
    y: 124 - p.value / max * 100,
  }));
  const path = positions.map((p, i) => `${i ? 'L' : 'M'}${p.x},${p.y}`).join(' ');
  const marks = [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])].filter(i => i >= 0);
  return <View testID="chat-report-chart" style={{ gap: 10 }}>
    <Text style={[ui.caption, { color: IOS.label, fontWeight: '700' }]}>{reportText(chart.title, language)}</Text>
    {peak === 0 ? <View style={{ borderColor: IOS.separator, borderWidth: 1, padding: 14, borderRadius: 13 }}>
      <Text style={[ui.caption, { color: IOS.label, fontWeight: '600' }]}>{en ? 'No activity in this period' : 'Chưa có số liệu phát sinh'}</Text>
      <Text style={ui.caption}>{en ? 'Open the data table to review individual values.' :
        points.length ? 'Bạn có thể xem các mốc bằng bảng số liệu.' : 'Báo cáo chưa có dữ liệu cho kỳ này.'}</Text>
    </View> : null}
    {chart.kind === 'bar' ? <View style={{ gap: 10 }}>
      {visibleBars.map((p, i) => <View key={i} accessible accessibilityLabel={`${reportText(p.label, language)}: ${reportValue(p.value, chart.unit)}`}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12, marginBottom: 3 }}>
          <Text numberOfLines={2} style={[ui.caption, { flex: 1, color: IOS.label }]}>{reportText(p.label, language)}</Text>
          <Text style={[ui.caption, { color: IOS.label, fontVariant: ['tabular-nums'], fontWeight: '600' }]}>{reportValue(p.value, chart.unit)}</Text>
        </View>
        <View style={{ height: 4, borderRadius: 2, backgroundColor: IOS.fill, overflow: 'hidden' }}>
          <View style={{ height: 4, width: `${p.value / max * 100}%`, borderRadius: 2, backgroundColor: BRAND.orange }} />
        </View>
      </View>)}
      {points.length > 6 ? <Pressable accessibilityRole="button" onPress={() => { onInteract?.(); setExpanded(value => !value); }}
        style={{ minHeight: 44, justifyContent: 'center' }}>
        <Text style={[ui.caption, { color: BRAND.orangeInk }]}>{en ? expanded ? 'Collapse chart' : `Show all ${points.length} items` :
          expanded ? 'Thu gọn biểu đồ' : `Xem đủ ${points.length} mục`}</Text>
      </Pressable> : null}
    </View> : peak > 0 ? <View style={{ gap: 5, paddingHorizontal: 8, paddingTop: 6, borderRadius: 12, backgroundColor: IOS.bg }}>
      <View style={{ minHeight: 32, paddingHorizontal: 3, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <Text accessibilityLiveRegion="polite" numberOfLines={1} style={[ui.caption, { flex: 1, color: IOS.label, fontWeight: picked ? '600' : '400' }]}>
          {picked ? reportLabel(picked.label) : en ? 'Tap a point to see its value' : 'Chạm biểu đồ để xem từng mốc'}
        </Text>
        {picked ? <Text style={[ui.caption, { color: BRAND.orangeInk, fontWeight: '700', fontVariant: ['tabular-nums'] }]}>{reportValue(picked.value, chart.unit)}</Text> : null}
      </View>
      <Pressable ref={plot} testID="chat-report-trend" disabled={!points.length}
        onLayout={event => { width.current = event.nativeEvent.layout.width; }}
        accessibilityRole="adjustable" accessibilityLabel={reportText(chart.title, language)}
        aria-valuemin={0} aria-valuemax={Math.max(0, points.length - 1)} aria-valuenow={selected ?? 0}
        aria-valuetext={picked ? `${reportLabel(picked.label)}: ${reportValue(picked.value, chart.unit)}` : en ? 'Select a time' : 'Chọn mốc thời gian'}
        accessibilityActions={[{ name: 'increment', label: en ? 'Next point' : 'Mốc tiếp theo' },
          { name: 'decrement', label: en ? 'Previous point' : 'Mốc trước' }]}
        onAccessibilityAction={event => {
          onInteract?.();
          const step = event.nativeEvent.actionName === 'increment' ? 1 : -1;
          setSelected(index => Math.max(0, Math.min(points.length - 1, (index ?? 0) + step)));
        }}
        onPress={event => {
          const select = (x: number, measuredWidth: number) => {
            if (!measuredWidth || !Number.isFinite(x)) return;
            onInteract?.();
            const scale = Math.min(measuredWidth / 320, 1);
            const plotX = (x - (measuredWidth - 320 * scale) / 2) / scale;
            setSelected(Math.max(0, Math.min(points.length - 1, Math.round((plotX - 50) / 254 * (points.length - 1)))));
          };
          if (Platform.OS === 'web') {
            const rect = (plot.current as unknown as HTMLElement | null)?.getBoundingClientRect();
            if (rect) select(event.nativeEvent.pageX - rect.left - window.scrollX, rect.width);
          } else {
            select(event.nativeEvent.locationX, width.current);
          }
        }}>
        <View pointerEvents="none">
        <Svg width="100%" height={166} viewBox="0 0 320 166"
          {...(Platform.OS === 'web' ? { 'aria-hidden': true as const, focusable: false } : { accessible: false })}>
          <Defs><LinearGradient id={gradient} x1={0} y1={0} x2={0} y2={1}>
            <Stop offset={0} stopColor={BRAND.orange} stopOpacity={0.25} />
            <Stop offset={1} stopColor={BRAND.orange} stopOpacity={0.015} />
          </LinearGradient></Defs>
          {[0, 0.5, 1].map(part => <Line key={part} x1={50} x2={304} y1={124 - part * 100} y2={124 - part * 100} stroke={IOS.separator} strokeDasharray={part ? '3 4' : undefined} />)}
          {[0, 0.5, 1].map(part => <SvgText key={part} x={42} textAnchor="end" y={128 - part * 100} fontSize={13} fill={IOS.secondary}>{axisValue(max * part)}</SvgText>)}
          {positions.length > 1 ? <Path d={path + ' L304,124 L50,124 Z'} fill={'url(#' + gradient + ')'} /> : null}
          {positions.length ? <Path d={path} stroke={BRAND.orange} strokeWidth={2.5} fill="none" strokeLinejoin="round" strokeLinecap="round" /> : null}
          {selected !== null && positions[selected] ? <Line x1={positions[selected].x} x2={positions[selected].x} y1={20} y2={124} stroke={BRAND.orangeInk} strokeOpacity={0.42} strokeDasharray="3 4" /> : null}
          {(selected !== null && positions[selected] ? [selected] : positions.length === 1 ? [0] : []).map(i => <Circle key={i} cx={positions[i]!.x} cy={positions[i]!.y} r={4} fill={BRAND.orange} stroke={IOS.card} strokeWidth={2} />)}
          {marks.map(i => <SvgText key={i} x={positions[i]!.x} y={151} fontSize={13} fill={IOS.secondary}
            textAnchor={i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'}>{reportLabel(points[i]!.label).split(' · ')[0]}</SvgText>)}
        </Svg>
        </View>
      </Pressable>
    </View> : null}
  </View>;
});
