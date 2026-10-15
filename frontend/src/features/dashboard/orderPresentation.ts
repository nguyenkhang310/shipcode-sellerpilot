export const ORDER_STATES = [
  { key: 'pending', label: 'Chờ xác nhận', color: '#A67515', darkColor: '#E8BD68', icon: 'time-outline' },
  { key: 'paid', label: 'Chờ lấy hàng', color: '#8662B1', darkColor: '#C7A3EB', icon: 'cube-outline' },
  { key: 'shipped', label: 'Đang giao', color: '#3E78B4', darkColor: '#8BBCEA', icon: 'car-outline' },
  { key: 'delivered', label: 'Đã giao', color: '#318367', darkColor: '#81CBAF', icon: 'checkmark-circle-outline' },
  { key: 'cancelled', label: 'Đã hủy', color: '#AF625D', darkColor: '#E6A19B', icon: 'close-circle-outline' },
  { key: 'returned', label: 'Đã hoàn hàng', color: '#7A7F8A', darkColor: '#AFB6C3', icon: 'return-down-back-outline' },
] as const;

export function orderDate(value: string) {
  const iso = value.replace(' ', 'T');
  const date = new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(iso) ? iso : iso + 'Z');
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('vi-VN', {
    timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}
