import { memo, useRef, useState } from 'react';
import { Platform, Pressable, StyleSheet, Text, useWindowDimensions, View, type ViewInstance } from 'react-native';
import Svg, { Circle, Line, Path, Text as SvgText } from 'react-native-svg';
import type { ReportChart as Chart, ReportUnit } from '../../api/types';
import { useTheme } from '../../theme/ThemeProvider';
import type { LiveLanguage } from './live/locale';
import { reportText } from './reportLocale';

export function reportValue(value: number | null, unit: ReportUnit, language?: LiveLanguage): string {
  if (value === null || !Number.isFinite(value)) return '—';
  const formatted = value.toLocaleString(language === 'en' ? 'en-GB' : 'vi-VN', {
    maximumFractionDigits: unit === 'percent' ? 1 : 0,
  });
  return formatted + (unit === 'vnd' ? '\u202F₫' : unit === 'percent' ? '%' : '');
}

export function reportLabel(label: string): string {
  if (!/^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2})?$/.test(label)) return label;
  const date = label.slice(8, 10) + '/' + label.slice(5, 7);
  return label.includes('T') ? label.slice(11, 16) + ' · ' + date : date;
}

function axisValue(value: number, unit: ReportUnit, language?: LiveLanguage) {
  const scale = value >= 1e9 ? 1e9 : value >= 1e6 ? 1e6 : value >= 1e3 ? 1e3 : 1;
  const suffix = scale === 1e9 ? language === 'en' ? 'B' : ' tỷ'
    : scale === 1e6 ? language === 'en' ? 'M' : ' tr' : scale === 1e3 ? 'k' : '';
  return (value / scale).toLocaleString(language === 'en' ? 'en-GB' : 'vi-VN', { maximumFractionDigits: 1 })
    + suffix + (unit === 'percent' ? '%' : '');
}

function tickStep(peak: number, unit: ReportUnit) {
  if (!peak) return 0;
  const base = 10 ** Math.floor(Math.log10(peak / 2));
  const nice = ([1, 2, 2.5, 5, 10].find(n => n * base >= peak / 2) ?? 10) * base;
  return unit === 'percent' ? nice : Math.max(1, Math.ceil(nice));
}

type ChartProps = { chart: Chart; language?: LiveLanguage; onInteract?: () => void };
const axisFont = Platform.select({ ios: 'Helvetica Neue', android: 'sans-serif', default: 'system-ui, sans-serif' });

function Trend({ chart, language, onInteract }: ChartProps) {
  const { IOS, BRAND } = useTheme();
  const plot = useRef<ViewInstance>(null);
  const [width, setWidth] = useState(0);
  const [selection, setSelection] = useState<string | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const points = chart.points;
  const saved = points.findIndex(p => p.label === selection);
  const pickedIndex = saved < 0 ? points.length - 1 : saved;
  const cursorIndex = hover !== null && hover < points.length ? hover : pickedIndex;
  const cursor = points[cursorIndex]!;
  const picked = points[pickedIndex]!;
  const peak = Math.max(...points.map(p => p.value));
  const step = tickStep(peak, chart.unit);
  const ticks = step ? [0, step, step * 2] : [0];
  const labels = ticks.map(value => axisValue(value, chart.unit, language));
  const axisLeft = Math.max(24, Math.max(...labels.map(label => label.length)) * 6.3 + 12);
  const axisRight = Math.max(axisLeft + 1, width - 12);
  const top = 10, baseline = 107, height = 133;
  const x = (index: number) => points.length === 1 ? (axisLeft + axisRight) / 2
    : axisLeft + index * (axisRight - axisLeft) / (points.length - 1);
  const y = (value: number) => baseline - (step ? value / (step * 2) : 0) * (baseline - top);
  const path = points.map((p, i) => `${i ? 'L' : 'M'}${x(i)},${y(p.value)}`).join(' ');
  const marks = [...new Set(width >= 360
    ? [0, Math.round((points.length - 1) / 3), Math.round((points.length - 1) * 2 / 3), points.length - 1]
    : width >= 200 ? [0, Math.floor((points.length - 1) / 2), points.length - 1] : [0, points.length - 1])];
  const nearest = (position: number) =>
    Math.max(0, Math.min(points.length - 1, Math.round((position - axisLeft) * (points.length - 1) / (axisRight - axisLeft))));
  const select = (index: number) => {
    onInteract?.();
    setHover(null);
    setSelection(points[Math.max(0, Math.min(points.length - 1, index))]!.label);
  };
  const browser = Platform.OS === 'web';
  const browserX = (clientX: number) => {
    const rect = (plot.current as unknown as HTMLElement | null)?.getBoundingClientRect();
    return rect && Number.isFinite(clientX) ? clientX - rect.left : null;
  };
  const title = reportText(chart.title, language);
  const format = (value: number) => reportValue(value, chart.unit, language);
  return <View style={{ gap: 5 }}>
    <View style={s.lineReadout} testID="chat-report-point">
      <Text style={[s.caption, { color: IOS.secondary }]}>{reportLabel(cursor.label)}</Text>
      <Text style={[s.value, { color: IOS.label }]}>{format(cursor.value)}</Text>
    </View>
    <Pressable ref={plot} testID="chat-report-trend" style={{ height }} onLayout={event => {
      setWidth(Math.floor(event.nativeEvent.layout.width));
    }} accessibilityRole="adjustable" accessibilityLabel={title}
      aria-valuemin={1} aria-valuemax={points.length} aria-valuenow={pickedIndex + 1}
      aria-valuetext={reportLabel(picked.label) + ', ' + format(picked.value)}
      accessibilityActions={[
        { name: 'increment', label: language === 'en' ? 'Next point' : 'Mốc tiếp theo' },
        { name: 'decrement', label: language === 'en' ? 'Previous point' : 'Mốc trước' },
      ]}
      onAccessibilityAction={event => select(pickedIndex + (event.nativeEvent.actionName === 'increment' ? 1 : -1))}
      onPress={event => {
        const native = event.nativeEvent;
        const position = browser ? browserX(native.pageX - window.scrollX) : native.locationX;
        // Keyboard activation can lack a pointer position.
        if (position !== null && Number.isFinite(position) && width > 0) select(nearest(position));
      }}
      onPointerMove={browser ? event => {
        if (event.nativeEvent.pointerType !== 'mouse') return;
        const position = browserX(event.nativeEvent.clientX);
        if (position !== null && width > 0) setHover(nearest(position));
      } : undefined}
      onPointerLeave={browser ? () => setHover(null) : undefined}
      onKeyDown={browser ? event => {
        const moves: Record<string, number> = {
          ArrowLeft: pickedIndex - 1, ArrowDown: pickedIndex - 1, ArrowRight: pickedIndex + 1,
          ArrowUp: pickedIndex + 1, Home: 0, End: points.length - 1,
        };
        const next = moves[event.nativeEvent.key];
        if (typeof next !== 'number') return;
        event.preventDefault();
        select(next);
      } : undefined}>
      {width > 0 ? <View pointerEvents="none">
        <Svg width={width} height={height} aria-hidden focusable={false}>
          {ticks.map((value, i) => <Line key={value} x1={axisLeft} x2={axisRight} y1={y(value)} y2={y(value)}
            stroke={i === 0 ? IOS.secondary : IOS.separator} strokeOpacity={i === 0 ? 0.52 : 1} />)}
          {ticks.map((value, i) => <SvgText key={value} x={axisLeft - 8} y={y(value) + 4} fontSize={11} fontFamily={axisFont}
            textAnchor="end" fill={IOS.secondary}>{labels[i]}</SvgText>)}
          <Line x1={x(cursorIndex)} x2={x(cursorIndex)} y1={top} y2={baseline}
            stroke={IOS.secondary} strokeOpacity={0.6} strokeDasharray="3 3" />
          {points.length > 1 ? <Path d={path} fill="none" stroke={BRAND.orange} strokeWidth={2}
            strokeLinecap="round" strokeLinejoin="round" /> : null}
          <Circle cx={x(cursorIndex)} cy={y(cursor.value)} r={4.5} fill={BRAND.orangeInk} stroke={IOS.card} strokeWidth={1.75} />
          {marks.map(i => <SvgText key={i} x={x(i)} y={127} fontSize={11} fontFamily={axisFont} fill={IOS.secondary}
            textAnchor={points.length === 1 ? 'middle' : i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'}>
            {reportLabel(points[i]!.label).split(' · ')[0]}
          </SvgText>)}
        </Svg>
      </View> : null}
    </Pressable>
  </View>;
}

function Bars({ chart, language, onInteract }: ChartProps) {
  const { IOS, BRAND } = useTheme();
  const { fontScale } = useWindowDimensions();
  const [expanded, setExpanded] = useState(false);
  const { points, unit } = chart;
  const max = Math.max(...points.map(point => point.value));
  const valueWidth = Math.max(24, reportValue(max, unit, language).length * 8 * fontScale);
  const visible = expanded ? points : points.slice(0, 6);
  return <View>
    {visible.map((point, index) => {
      const label = reportText(point.label, language);
      const value = reportValue(point.value, unit, language);
      return <View key={index} accessible accessibilityLabel={label + ', ' + value} style={[s.barRow,
        { borderColor: IOS.separator, borderBottomWidth: index < visible.length - 1 ? StyleSheet.hairlineWidth : 0 }]}>
        <Text style={[s.caption, { flex: 1.4, minWidth: 0, color: IOS.label }]}>{label}</Text>
        <View style={{ flex: 1, height: 6 }}>
          {point.value > 0 ? <View style={{ height: 6, minWidth: 1, width: `${point.value / max * 100}%`,
            borderRadius: 2, backgroundColor: BRAND.orange }} /> : null}
        </View>
        <Text style={[s.value, { width: valueWidth, maxWidth: '45%', color: IOS.label }]}>{value}</Text>
      </View>;
    })}
    {points.length > 6 ? <Pressable accessibilityRole="button" aria-expanded={expanded}
      onPress={() => { onInteract?.(); setExpanded(value => !value); }} style={s.toggle}>
      <Text style={[s.caption, { color: BRAND.orangeInk, fontWeight: '600' }]}>
        {language === 'en' ? expanded ? 'Show fewer' : `Show all ${points.length} items`
          : expanded ? 'Thu gọn' : `Xem đủ ${points.length} mục`}
      </Text>
    </Pressable> : null}
  </View>;
}

export const ReportChart = memo(function ReportChart(props: ChartProps) {
  const { IOS } = useTheme();
  const { chart, language } = props;
  return <View testID="chat-report-chart" style={{ gap: 11 }}>
    <View style={s.barLabel}>
      <Text style={[s.caption, { flex: 1, color: IOS.label, fontWeight: '600' }]}>{reportText(chart.title, language)}</Text>
      {chart.unit === 'vnd' ? <Text style={[s.caption, { color: IOS.secondary }]}>VND</Text> : null}
    </View>
    {!chart.points.length ? <Text style={[s.caption, { color: IOS.secondary }]}>
      {language === 'en' ? 'No data available for this period.' : 'Chưa có dữ liệu cho kỳ này.'}
    </Text> : chart.kind === 'line' ? <Trend {...props} /> : <Bars {...props} />}
  </View>;
});

const s = StyleSheet.create({
  caption: { fontSize: 13, lineHeight: 18 },
  value: { fontSize: 14, lineHeight: 20, textAlign: 'right', fontWeight: '600', fontVariant: ['tabular-nums'] },
  barLabel: { flexDirection: 'row', justifyContent: 'space-between', gap: 10 },
  barRow: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 33, paddingVertical: 6 },
  lineReadout: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'baseline', justifyContent: 'space-between', columnGap: 8, minHeight: 22 },
  toggle: { minHeight: 44, alignSelf: 'flex-start', justifyContent: 'center' },
});
