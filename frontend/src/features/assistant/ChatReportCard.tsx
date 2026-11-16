import { memo, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { SystemIcon } from '../../components/ui/SystemIcon';
import { ChatReport, ReportTable } from '../../api/types';
import { useTheme } from '../../theme/ThemeProvider';
import { ReportChart, reportLabel, reportValue } from './ReportChart';
import { MetricValue } from '../dashboard/OrderValue';

function DataTable({ table }: { table: ReportTable }) {
  const { IOS, ui, BRAND } = useTheme();
  const [all, setAll] = useState(false);
  const [width, setWidth] = useState(0);
  const minWidth = table.columns.length > 2 ? 380 : 230;
  const rows = all ? table.rows : table.rows.slice(0, 5);
  return <View testID="chat-report-table" style={{ gap: 10 }}>
    <Text style={[ui.caption, { fontWeight: '600', color: IOS.label }]}>{table.title}</Text>
    <ScrollView testID="chat-report-table-scroll" horizontal showsHorizontalScrollIndicator contentContainerStyle={{ flexGrow: 1 }}
      onLayout={event => setWidth(event.nativeEvent.layout.width)}>
      <View style={{ minWidth, flex: 1 }}>
        <View style={{ flexDirection: 'row', borderBottomWidth: 1, borderColor: IOS.separator, paddingBottom: 10, gap: 12 }}>
          {table.columns.map((column, i) => <Text key={i} style={[ui.caption, { flex: i === 0 ? 2 : 1, minWidth: i === 0 ? 110 : 80,
            textAlign: column.unit === 'text' ? 'left' : 'right', fontWeight: '600' }]}>{column.label}</Text>)}
        </View>
        {rows.map((row, index) => <View key={index} style={{ flexDirection: 'row', paddingVertical: 12, gap: 12,
          borderBottomWidth: 1, borderColor: IOS.separator }}>
          {table.columns.map((column, i) => <Text key={i} style={[ui.caption, { flex: i === 0 ? 2 : 1, minWidth: i === 0 ? 110 : 80,
            textAlign: column.unit === 'text' ? 'left' : 'right', color: IOS.label, fontVariant: ['tabular-nums'] }]}>
            {row[i] === null || row[i] === undefined ? '—' : column.unit === 'text' ? reportLabel(String(row[i]))
              : typeof row[i] === 'number' ? reportValue(row[i], column.unit) : '—'}
          </Text>)}
        </View>)}
        {!rows.length ? <Text style={[ui.caption, { paddingVertical: 14 }]}>Không có mặt hàng phù hợp.</Text> : null}
      </View>
    </ScrollView>
    {width > 0 && width < minWidth ? <Text style={ui.caption}>Vuốt ngang để xem đủ các cột.</Text> : null}
    {table.rows.length > 5 ? <Pressable accessibilityRole="button" onPress={() => setAll(value => !value)}
      style={{ minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start' }}>
      <Text style={[ui.caption, { color: BRAND.orangeInk, fontWeight: '600' }]}>{all ? 'Thu gọn bảng' : `Xem đủ ${table.rows.length} dòng`}</Text>
    </Pressable> : null}
  </View>;
}

function updatedLabel(report: ChatReport) {
  if (!report.as_of || !Number.isFinite(Date.parse(report.as_of))) return null;
  return 'Cập nhật ' + new Date(report.as_of).toLocaleString('vi-VN', {
    timeZone: report.timezone || 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit',
  });
}

export const ChatReportCard = memo(function ChatReportCard({ report }: { report: ChatReport }) {
  const { IOS, BRAND, ui } = useTheme();
  const [active, setActive] = useState('chart-0');
  const [details, setDetails] = useState(false);
  const tabs = [
    ...report.charts.map((chart, i) => ({ key: 'chart-' + i,
      label: chart.kind === 'line' ? 'Xu hướng' : chart.title.includes('Trạng thái') ? 'Trạng thái'
        : chart.title.includes('Sản lượng') ? 'Sản phẩm' : 'Tồn kho', chart })),
    ...(report.table ? [{ key: 'table', label: 'Bảng số liệu', chart: null }] : []),
  ];
  const current = tabs.find(tab => tab.key === active) || tabs[0];
  const updated = updatedLabel(report);
  return <View testID="chat-report" style={{ marginTop: 12, borderWidth: 1, borderColor: IOS.separator,
    backgroundColor: IOS.card, borderRadius: 18, padding: 16, gap: 14, overflow: 'hidden' }}>
    <View style={{ gap: 4 }}>
      <Text accessibilityRole="header" style={{ fontSize: 17, lineHeight: 24, fontWeight: '700', color: IOS.label }}>{report.title}</Text>
      <Text style={ui.caption}>{report.subtitle.replace(/\d{4}-\d{2}-\d{2}/g, date => reportLabel(date) + '/' + date.slice(0, 4))}</Text>
    </View>
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
      {report.metrics.slice(0, 2).map(metric => <View key={metric.label} style={{ flex: 1, minWidth: 0, gap: 2 }}>
        <Text style={ui.caption}>{metric.label}</Text>
        <MetricValue testID="chat-report-metric" value={reportValue(metric.value, metric.unit)} colour={IOS.label} />
        {metric.change_percent !== null ? <Text style={[ui.caption, { color: metric.change_percent < 0 ? IOS.red : BRAND.orangeInk }]}>
          {metric.change_percent > 0 ? '+' : ''}{reportValue(metric.change_percent, 'percent')} so với kỳ trước
        </Text> : null}
      </View>)}
    </View>
    {tabs.length > 1 ? <View accessibilityRole="tablist" accessibilityLabel="Nội dung báo cáo"
      style={{ flexDirection: 'row', padding: 3, backgroundColor: IOS.fill, borderRadius: 12, gap: 3 }}>
      {tabs.map(tab => <Pressable key={tab.key} accessibilityRole="tab" accessibilityLabel={tab.label}
        accessibilityState={{ selected: tab.key === current?.key }} onPress={() => setActive(tab.key)}
        style={({ pressed }) => ({ flex: 1, minWidth: 0, minHeight: 44, justifyContent: 'center', alignItems: 'center',
          paddingHorizontal: 4, borderRadius: 9, backgroundColor: tab.key === current?.key ? IOS.card : 'transparent', opacity: pressed ? 0.7 : 1 })}>
        <Text style={[ui.caption, { textAlign: 'center', fontWeight: tab.key === current?.key ? '600' : '400',
          color: tab.key === current?.key ? BRAND.orangeInk : IOS.secondary }]}>{tab.label}</Text>
      </Pressable>)}
    </View> : null}
    {current?.chart ? <ReportChart key={current.key} chart={current.chart} />
      : current?.key === 'table' && report.table ? <DataTable table={report.table} /> : null}
    <View style={{ borderTopWidth: 1, borderColor: IOS.separator }}>
      <Pressable accessibilityRole="button" accessibilityLabel={details ? 'Thu gọn báo cáo' : 'Chi tiết báo cáo'}
        accessibilityState={{ expanded: details }} onPress={() => setDetails(value => !value)}
        style={{ minHeight: 44, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <Text style={ui.caption}>{details ? 'Thu gọn báo cáo' : 'Chi tiết báo cáo'}</Text>
        <SystemIcon name={details ? 'chevron-up' : 'chevron-down'} size={15} color={IOS.secondary} />
      </Pressable>
      {details ? <View testID="chat-report-details" style={{ gap: 10, paddingBottom: 4 }}>
        {report.metrics.slice(2).map(metric => <View key={metric.label} style={{ gap: 3 }}>
          <Text style={ui.caption}>{metric.label}</Text>
          <Text style={[ui.caption, { color: IOS.label, fontWeight: '600' }]}>{reportValue(metric.value, metric.unit)}</Text>
        </View>)}
        {updated ? <Text style={ui.caption}>{updated}{report.timezone ? ` · ${report.timezone}` : ''}</Text> : null}
        {report.notes.map(note => <Text key={note} style={ui.caption}>{note}</Text>)}
      </View> : null}
    </View>
  </View>;
});
