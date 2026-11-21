import { memo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { SystemIcon } from '../../components/ui/SystemIcon';
import type { ChatReport, ReportChart as Chart, ReportTable } from '../../api/types';
import { useTheme } from '../../theme/ThemeProvider';
import { ReportChart, reportLabel, reportValue } from './ReportChart';
import type { LiveLanguage } from './live/locale';
import { reportText } from './reportLocale';

function DataTable({ table, language, onInteract }: { table: ReportTable; language?: LiveLanguage; onInteract?: () => void }) {
  const { IOS, BRAND } = useTheme();
  const { fontScale } = useWindowDimensions();
  const [all, setAll] = useState(false);
  const [width, setWidth] = useState(0);
  const en = language === 'en';
  const columns = table.columns.map(column => ({
    flex: column.unit === 'text' ? 1.6 : 1,
    minWidth: Math.ceil((column.unit === 'text' ? 96 : column.unit === 'vnd' ? 80 : 48) * fontScale),
    textAlign: column.unit === 'text' ? 'left' as const : 'right' as const,
  }));
  const minWidth = columns.reduce((sum, column) => sum + column.minWidth, 0) + (columns.length - 1) * 10;
  const rows = all ? table.rows : table.rows.slice(0, 5);
  const ledger = <View style={{ minWidth, flexGrow: 1 }}>
    <View style={[s.tableRow, { borderColor: IOS.separator, paddingTop: 0, paddingBottom: 8 }]}>
      {table.columns.map((column, i) => <Text key={i} style={[s.caption, columns[i], { color: IOS.secondary }]}>
        {reportText(column.label, language)}
      </Text>)}
    </View>
    {rows.map((row, index) => <View key={index} style={[s.tableRow,
      { borderColor: IOS.separator, borderBottomWidth: index === rows.length - 1 ? 0 : StyleSheet.hairlineWidth }]}>
      {table.columns.map((column, i) => {
        const value = row[i];
        const [name, sku] = column.unit === 'text' && typeof value === 'string' ? value.split('\n', 2) : [];
        return <View key={i} style={columns[i]}>
          <Text style={[s.caption, { textAlign: columns[i]!.textAlign, color: IOS.label, fontVariant: ['tabular-nums'] }]}>
            {name !== undefined ? reportText(reportLabel(name), language) : typeof value === 'number' && column.unit !== 'text'
              ? reportValue(value, column.unit, language) : '—'}
          </Text>
          {sku ? <Text selectable style={[s.caption, { color: IOS.secondary }]}>{sku}</Text> : null}
        </View>;
      })}
    </View>)}
  </View>;
  return <View testID="chat-report-table" style={{ gap: 10 }}
    onLayout={event => setWidth(Math.floor(event.nativeEvent.layout.width))}>
    <Text style={[s.caption, { fontWeight: '600', color: IOS.label }]}>{reportText(table.title, language)}</Text>
    {rows.length ? width > 0 && width < minWidth ? <>
      <ScrollView testID="chat-report-table-scroll" horizontal onScrollBeginDrag={onInteract} keyboardShouldPersistTaps="handled">
        {ledger}
      </ScrollView>
      <Text style={[s.caption, { color: IOS.secondary }]}>
        {en ? 'Scroll sideways to see every column.' : 'Vuốt ngang để xem đủ các cột.'}
      </Text>
    </> : ledger : <Text style={[s.caption, { color: IOS.secondary, paddingVertical: 8 }]}>
      {en ? 'No results for this report.' : 'Không có mục nào trong báo cáo.'}
    </Text>}
    {table.rows.length > 5 ? <Pressable accessibilityRole="button" aria-expanded={all}
      onPress={() => { onInteract?.(); setAll(value => !value); }} style={s.toggle}>
      <Text style={[s.caption, { color: BRAND.orangeInk, fontWeight: '600' }]}>
        {en ? all ? 'Show fewer rows' : `Show all ${table.rows.length} rows` : all ? 'Thu gọn bảng' : `Xem đủ ${table.rows.length} dòng`}
      </Text>
    </Pressable> : null}
  </View>;
}

function updatedLabel(report: ChatReport, language?: LiveLanguage) {
  if (!report.as_of || !Number.isFinite(Date.parse(report.as_of))) return null;
  try {
    return (language === 'en' ? 'Updated ' : 'Cập nhật ') + new Date(report.as_of).toLocaleString(language === 'en' ? 'en-GB' : 'vi-VN', {
      timeZone: report.timezone || 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit',
    });
  } catch {
    return null;
  }
}

function chartTab(chart: Chart, language?: LiveLanguage) {
  if (chart.kind === 'line') return language === 'en' ? 'Trend' : 'Xu hướng';
  const labels: Record<string, [string, string]> = {
    'Trạng thái đơn trong kỳ': ['Trạng thái', 'Status'],
    'Sản lượng bán trong kỳ': ['Sản phẩm', 'Products'],
    'Phân bố tồn kho': ['Tồn kho', 'Inventory'],
    'Tồn kho theo SKU': ['Tồn kho', 'Inventory'],
  };
  return labels[chart.title]?.[language === 'en' ? 1 : 0] ?? reportText(chart.title, language);
}

export const ChatReportCard = memo(function ChatReportCard({ report, language, separated, onInteract }: {
  report: ChatReport; language?: LiveLanguage; separated: boolean; onInteract?: () => void;
}) {
  const { IOS, BRAND } = useTheme();
  const { width: windowWidth, fontScale } = useWindowDimensions();
  const [active, setActive] = useState('chart-0');
  const [details, setDetails] = useState(false);
  const [metricWidth, setMetricWidth] = useState(0);
  const en = language === 'en';
  const tabs = [
    ...report.charts.map((chart, i) => ({ key: 'chart-' + i, label: chartTab(chart, language), chart })),
    ...(report.table ? [{ key: 'table', label: en ? 'Data table' : 'Bảng số liệu', chart: null }] : []),
  ];
  const current = tabs.find(tab => tab.key === active) || tabs[0];
  const updated = updatedLabel(report, language);
  const detailMetrics = report.metrics.slice(2);
  const detailLabel = en ? 'Report details' : 'Chi tiết báo cáo';
  const [primary, secondary] = report.metrics;
  const headline = primary ? reportValue(primary.value, primary.unit, language) : '';
  const available = metricWidth || windowWidth - 64;
  const headlineSize = Math.min(31, Math.max(18, Math.floor(available / (Math.max(1, headline.length) * 0.64 * fontScale))));
  return <View testID="chat-report" style={[s.card, separated && { borderTopWidth: StyleSheet.hairlineWidth, borderColor: IOS.separator }]}>
    <View style={{ gap: 4 }}>
      <Text accessibilityRole="header" style={[s.title, { color: IOS.label }]}>{reportText(report.title, language)}</Text>
      {report.subtitle ? <Text style={[s.caption, { color: IOS.secondary }]}>
        {reportText(report.subtitle, language).replace(/\d{4}-\d{2}-\d{2}/g, date => reportLabel(date) + '/' + date.slice(0, 4))}
      </Text> : null}
    </View>
    {primary ? <View style={{ gap: 12 }} onLayout={event => setMetricWidth(Math.floor(event.nativeEvent.layout.width))}>
      <View style={{ gap: 3 }}>
        <Text style={[s.caption, { color: IOS.secondary }]}>{reportText(primary.label, language)}</Text>
        <Text testID="chat-report-metric" style={[s.primaryValue, { color: IOS.label, fontSize: headlineSize, lineHeight: headlineSize + 6 }]}>
          {headline}
        </Text>
        {primary.change_percent != null && Number.isFinite(primary.change_percent) ? <Text style={[s.caption, { color: IOS.secondary }]}>
          <Text style={{ color: primary.change_percent > 0 ? BRAND.orangeInk : IOS.label, fontWeight: '600', fontVariant: ['tabular-nums'] }}>
            {primary.change_percent > 0 ? '+' : ''}{reportValue(primary.change_percent, 'percent', language)}
          </Text>
          {en ? ' vs. previous period' : ' so với kỳ trước'}
        </Text> : null}
      </View>
      {secondary ? <View style={s.metricRow}>
        <Text style={[s.caption, { color: IOS.secondary, flexShrink: 1 }]}>{reportText(secondary.label, language)}</Text>
        <Text testID="chat-report-metric" style={[s.secondaryValue, { color: IOS.label }]}>{reportValue(secondary.value, secondary.unit, language)}</Text>
      </View> : null}
    </View> : null}
    {tabs.length > 1 ? <View accessibilityRole="tablist" accessibilityLabel={en ? 'Report views' : 'Nội dung báo cáo'}
      style={[s.tabRow, { borderColor: IOS.separator }]}>
      {tabs.map(tab => {
        const selected = tab.key === current?.key;
        return <Pressable key={tab.key} accessibilityRole="tab" accessibilityLabel={tab.label} aria-selected={selected}
          onPress={() => { if (!selected) { onInteract?.(); setActive(tab.key); } }}
          style={({ pressed }) => [s.tab, { borderColor: selected ? BRAND.orangeInk : 'transparent', opacity: pressed ? 0.7 : 1 }]}>
          <Text style={[s.caption, { color: selected ? IOS.label : IOS.secondary, fontWeight: selected ? '600' : '400' }]}>{tab.label}</Text>
        </Pressable>;
      })}
    </View> : null}
    {current?.chart ? <ReportChart key={current.key} chart={current.chart} language={language} onInteract={onInteract} />
      : current?.key === 'table' && report.table ? <DataTable table={report.table} language={language} onInteract={onInteract} /> : null}
    {detailMetrics.length || updated || report.notes.length ? <View style={[s.footer, { borderColor: IOS.separator }]}>
      <Pressable accessibilityRole="button" aria-expanded={details}
        onPress={() => { onInteract?.(); setDetails(value => !value); }} style={[s.metricRow, { minHeight: 44 }]}>
        <Text style={[s.caption, { color: IOS.secondary, flex: 1 }]}>{detailLabel}</Text>
        <SystemIcon name={details ? 'chevron-up' : 'chevron-down'} size={14} color={IOS.secondary} />
      </Pressable>
      {details ? <View testID="chat-report-details" style={{ gap: 10, paddingBottom: 12 }}>
        {detailMetrics.map(metric => <View key={metric.label} style={s.metricRow}>
          <Text style={[s.caption, { color: IOS.secondary, flexShrink: 1 }]}>{reportText(metric.label, language)}</Text>
          <Text style={[s.secondaryValue, { color: IOS.label }]}>{reportValue(metric.value, metric.unit, language)}</Text>
        </View>)}
        {updated ? <Text style={[s.caption, { color: IOS.secondary }]}>{updated}{report.timezone ? ` · ${report.timezone}` : ''}</Text> : null}
        {report.notes.map(note => <Text key={note} style={[s.caption, { color: IOS.secondary }]}>{reportText(note, language)}</Text>)}
      </View> : null}
    </View> : null}
  </View>;
});

const s = StyleSheet.create({
  card: { padding: 14, gap: 14, minWidth: 0 },
  title: { fontSize: 17, lineHeight: 23, letterSpacing: -0.25, fontWeight: '600' },
  caption: { fontSize: 13, lineHeight: 18 },
  primaryValue: { letterSpacing: -0.75, fontWeight: '600', fontVariant: ['tabular-nums'] },
  secondaryValue: { fontSize: 14, lineHeight: 20, fontWeight: '600', fontVariant: ['tabular-nums'] },
  metricRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  tabRow: { flexDirection: 'row', flexWrap: 'wrap', columnGap: 14, borderBottomWidth: StyleSheet.hairlineWidth },
  tab: { justifyContent: 'center', minHeight: 44, borderBottomWidth: 2 },
  tableRow: { flexDirection: 'row', gap: 10, borderBottomWidth: StyleSheet.hairlineWidth, paddingVertical: 9 },
  footer: { borderTopWidth: StyleSheet.hairlineWidth, marginBottom: -12 },
  toggle: { minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start' },
});
