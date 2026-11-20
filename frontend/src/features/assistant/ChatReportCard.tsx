import { memo, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { SystemIcon } from '../../components/ui/SystemIcon';
import { ChatReport, ReportTable } from '../../api/types';
import { useTheme } from '../../theme/ThemeProvider';
import { ReportChart, reportLabel, reportValue } from './ReportChart';
import { MetricValue } from '../dashboard/OrderValue';
import type { LiveLanguage } from './live/locale';
import { reportText } from './reportLocale';

function DataTable({ table, language, onInteract }: { table: ReportTable; language?: LiveLanguage; onInteract?: () => void }) {
  const { IOS, ui, BRAND } = useTheme();
  const [all, setAll] = useState(false);
  const [width, setWidth] = useState(0);
  const en = language === 'en';
  const minWidth = table.columns.length > 2 ? 380 : 230;
  const rows = all ? table.rows : table.rows.slice(0, 5);
  return <View testID="chat-report-table" style={{ gap: 10 }}>
    <Text style={[ui.caption, { fontWeight: '600', color: IOS.label }]}>{reportText(table.title, language)}</Text>
    <ScrollView testID="chat-report-table-scroll" horizontal showsHorizontalScrollIndicator contentContainerStyle={{ flexGrow: 1 }}
      onScrollBeginDrag={onInteract}
      onLayout={event => setWidth(event.nativeEvent.layout.width)}>
      <View style={{ minWidth, flex: 1 }}>
        <View style={{ flexDirection: 'row', borderBottomWidth: 1, borderColor: IOS.separator, paddingBottom: 10, gap: 12 }}>
          {table.columns.map((column, i) => <Text key={i} style={[ui.caption, { flex: i === 0 ? 2 : 1, minWidth: i === 0 ? 110 : 80,
            textAlign: column.unit === 'text' ? 'left' : 'right', fontWeight: '600' }]}>{reportText(column.label, language)}</Text>)}
        </View>
        {rows.map((row, index) => <View key={index} style={{ flexDirection: 'row', paddingVertical: 12, gap: 12,
          borderBottomWidth: 1, borderColor: IOS.separator }}>
          {table.columns.map((column, i) => <Text key={i} style={[ui.caption, { flex: i === 0 ? 2 : 1, minWidth: i === 0 ? 110 : 80,
            textAlign: column.unit === 'text' ? 'left' : 'right', color: IOS.label, fontVariant: ['tabular-nums'] }]}>
            {row[i] === null || row[i] === undefined ? '—' : column.unit === 'text' ? reportLabel(String(row[i]))
              : typeof row[i] === 'number' ? reportValue(row[i], column.unit) : '—'}
          </Text>)}
        </View>)}
        {!rows.length ? <Text style={[ui.caption, { paddingVertical: 14 }]}>{en ? 'No matching products.' : 'Không có mặt hàng phù hợp.'}</Text> : null}
      </View>
    </ScrollView>
    {width > 0 && width < minWidth ? <Text style={ui.caption}>{en ? 'Scroll sideways to see every column.' : 'Vuốt ngang để xem đủ các cột.'}</Text> : null}
    {table.rows.length > 5 ? <Pressable accessibilityRole="button" onPress={() => { onInteract?.(); setAll(value => !value); }}
      style={{ minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start' }}>
      <Text style={[ui.caption, { color: BRAND.orangeInk, fontWeight: '600' }]}>{en ? all ? 'Collapse table' : `Show all ${table.rows.length} rows` :
        all ? 'Thu gọn bảng' : `Xem đủ ${table.rows.length} dòng`}</Text>
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

export const ChatReportCard = memo(function ChatReportCard({ report, language, onInteract }: {
  report: ChatReport; language?: LiveLanguage; onInteract?: () => void; snapshotKey?: string;
}) {
  const { IOS, BRAND, ui } = useTheme();
  const [active, setActive] = useState('chart-0');
  const [details, setDetails] = useState(false);
  const en = language === 'en';
  const tabs = [
    ...report.charts.map((chart, i) => ({ key: 'chart-' + i,
      label: chart.kind === 'line' ? en ? 'Trend' : 'Xu hướng' : chart.title.includes('Trạng thái') ? en ? 'Status' : 'Trạng thái'
        : chart.title.includes('Sản lượng') ? en ? 'Products' : 'Sản phẩm' : en ? 'Inventory' : 'Tồn kho', chart })),
    ...(report.table ? [{ key: 'table', label: en ? 'Data table' : 'Bảng số liệu', chart: null }] : []),
  ];
  const current = tabs.find(tab => tab.key === active) || tabs[0];
  const updated = updatedLabel(report, language);
  const detailsLabel = en ? details ? 'Collapse details' : 'Report details' : details ? 'Thu gọn báo cáo' : 'Chi tiết báo cáo';
  return <View testID="chat-report" style={{ marginTop: 12, borderWidth: 1, borderColor: IOS.separator,
    backgroundColor: IOS.card, borderRadius: 18, padding: 15, gap: 13, overflow: 'hidden' }}>
    <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}>
      <View style={{ width: 36, height: 36, alignItems: 'center', justifyContent: 'center', borderRadius: 11, backgroundColor: BRAND.orangeSoft }}>
        <SystemIcon name="pulse-outline" size={19} color={BRAND.orangeInk} />
      </View>
      <View style={{ gap: 3, flex: 1 }}>
        <Text accessibilityRole="header" style={{ fontSize: 17, lineHeight: 24, fontWeight: '700', color: IOS.label }}>{reportText(report.title, language)}</Text>
        <Text style={ui.caption}>{reportText(report.subtitle, language).replace(/\d{4}-\d{2}-\d{2}/g, date => reportLabel(date) + '/' + date.slice(0, 4))}</Text>
      </View>
    </View>
    <View style={{ flexDirection: 'row', gap: 1, borderColor: IOS.separator, borderWidth: 1, borderRadius: 12, overflow: 'hidden' }}>
      {report.metrics.slice(0, 2).map(metric => <View key={metric.label} style={{ flex: 1, minWidth: 0, gap: 2 }}>
        <View style={{ padding: 10, minHeight: 58, gap: 4, backgroundColor: IOS.bg }}>
        <Text style={ui.caption}>{reportText(metric.label, language)}</Text>
        <MetricValue testID="chat-report-metric" value={reportValue(metric.value, metric.unit)} colour={IOS.label} />
        {metric.change_percent != null && Number.isFinite(metric.change_percent) ? <Text style={[ui.caption, { color: metric.change_percent < 0 ? IOS.red : BRAND.orangeInk }]}>
          {metric.change_percent > 0 ? '+' : ''}{reportValue(metric.change_percent, 'percent')} {en ? 'vs. previous period' : 'so với kỳ trước'}
        </Text> : null}
        </View>
      </View>)}
    </View>
    {tabs.length > 1 ? <View accessibilityRole="tablist" accessibilityLabel={en ? 'Report views' : 'Nội dung báo cáo'}
      style={{ flexDirection: 'row', padding: 3, backgroundColor: IOS.fill, borderRadius: 12, gap: 3 }}>
      {tabs.map(tab => <Pressable key={tab.key} accessibilityRole="tab" accessibilityLabel={tab.label}
        accessibilityState={{ selected: tab.key === current?.key }} onPress={() => { onInteract?.(); setActive(tab.key); }}
        style={({ pressed }) => ({ flex: 1, minWidth: 0, minHeight: 44, justifyContent: 'center', alignItems: 'center',
          paddingHorizontal: 4, borderRadius: 9, backgroundColor: tab.key === current?.key ? IOS.card : 'transparent', opacity: pressed ? 0.7 : 1 })}>
        <Text style={[ui.caption, { textAlign: 'center', fontWeight: tab.key === current?.key ? '600' : '400',
          color: tab.key === current?.key ? BRAND.orangeInk : IOS.secondary }]}>{tab.label}</Text>
      </Pressable>)}
    </View> : null}
    {current?.chart ? <ReportChart key={current.key} chart={current.chart} language={language} onInteract={onInteract} />
      : current?.key === 'table' && report.table ? <DataTable table={report.table} language={language} onInteract={onInteract} /> : null}
    <View style={{ borderTopWidth: 1, borderColor: IOS.separator }}>
      <Pressable accessibilityRole="button" accessibilityLabel={detailsLabel}
        accessibilityState={{ expanded: details }} onPress={() => { onInteract?.(); setDetails(value => !value); }}
        style={{ minHeight: 44, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <Text style={ui.caption}>{detailsLabel}</Text>
        <SystemIcon name={details ? 'chevron-up' : 'chevron-down'} size={15} color={IOS.secondary} />
      </Pressable>
      {details ? <View testID="chat-report-details" style={{ gap: 10, paddingBottom: 4 }}>
        {report.metrics.slice(2).map(metric => <View key={metric.label} style={{ gap: 3 }}>
          <Text style={ui.caption}>{reportText(metric.label, language)}</Text>
          <Text style={[ui.caption, { color: IOS.label, fontWeight: '600' }]}>{reportValue(metric.value, metric.unit)}</Text>
        </View>)}
        {updated ? <Text style={ui.caption}>{updated}{report.timezone ? ` · ${report.timezone}` : ''}</Text> : null}
        {report.notes.map(note => <Text key={note} style={ui.caption}>{reportText(note, language)}</Text>)}
      </View> : null}
    </View>
  </View>;
}, (before, after) => before.language === after.language && before.onInteract === after.onInteract &&
  (before.report === after.report || Boolean(before.snapshotKey && before.snapshotKey === after.snapshotKey)));
