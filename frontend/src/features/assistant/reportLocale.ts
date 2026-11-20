import type { LiveLanguage } from './live/locale';

const ENGLISH: Record<string, string> = {
  'Hiệu quả kinh doanh': 'Sales performance',
  'Giá trị đơn hàng': 'Order value',
  'Đơn hợp lệ': 'Valid orders',
  'Giá trị đã giao': 'Delivered order value',
  'Trung bình / đơn': 'Average order value',
  'Diễn biến giá trị đơn hàng': 'Order value over time',
  'Trạng thái đơn trong kỳ': 'Order status by period',
  'Chi tiết giá trị đơn hàng': 'Order value breakdown',
  'Thời điểm': 'Time',
  'Giá trị đơn': 'Order value',
  'Chờ xác nhận': 'Awaiting confirmation',
  'Chờ lấy hàng': 'Ready for pickup',
  'Đang giao': 'In transit',
  'Đã giao': 'Delivered',
  'Đã hủy': 'Cancelled',
  'Đã hoàn': 'Returned',
  'Tổng quan tồn kho': 'Inventory overview',
  'Tồn khả dụng theo SKU đang bán': 'Available stock by active SKU',
  'SKU đang bán': 'Active SKUs',
  'Số lượng trong kho': 'Units in stock',
  'Sắp hết hàng': 'Low stock',
  'Đã hết hàng': 'Out of stock',
  'Phân bố tồn kho': 'Stock breakdown',
  'Hết hàng': 'Out of stock',
  'Hàng cần bổ sung': 'Products to restock',
  'SKU trong danh sách': 'SKUs in this report',
  'Tồn kho theo SKU': 'Stock by SKU',
  'Chi tiết tồn kho': 'Inventory details',
  'Sản phẩm / SKU': 'Product / SKU',
  'Còn': 'In stock',
  'Giá bán': 'Price',
  'Sản lượng bán trong kỳ': 'Units sold in this period',
  'Sản phẩm bán tốt trong kỳ': 'Top-selling products',
  'Đã bán': 'Units sold',
  'Giá trị hàng': 'Item value',
  'Số liệu được lưu cùng câu trả lời': 'Report saved with this reply',
  'Giá trị đơn hàng loại đơn hủy/hoàn; không đồng nghĩa tiền đã thu hoặc lợi nhuận.': 'Order value excludes cancellations and returns. It differs from payments collected and profit.',
  'Hôm nay mới tính tới thời điểm cập nhật; so sánh với cùng thời lượng kỳ trước.': 'Today is partial and is compared with the same elapsed time in the previous period.',
  'Chưa có cơ sở kỳ trước để tính tỷ lệ tăng/giảm.': 'A comparison requires data from the previous period.',
  'Tính theo SKU/biến thể hoạt động, không cộng trùng tồn sản phẩm cha.': 'Counts active SKUs and variants once.',
  'Danh sách giới hạn 50 SKU; biểu đồ hiển thị tối đa 8 SKU đầu.': 'The table shows up to 50 SKUs. The chart shows up to eight.',
  'Biểu đồ hiển thị tối đa 8 SKU đầu.': 'The chart shows up to eight SKUs.',
  'Giá trị hàng tính theo giá lúc mua, chưa phân bổ phí vận chuyển/giảm giá cấp đơn.': 'Item value uses the purchase price before order-level shipping and discounts.',
  'Chưa có dòng hàng đủ dữ kiện để xếp hạng sản phẩm trong kỳ.': 'There is not enough item data to rank products in this period.',
  'Một số dòng hàng chưa khớp danh mục; bảng sản phẩm chưa bao phủ toàn bộ đơn.': 'Some order lines could not be matched to the catalogue.',
};

export function reportText(value: string, language?: LiveLanguage) {
  if (language !== 'en') return value;
  const translated = Object.prototype.hasOwnProperty.call(ENGLISH, value) ? ENGLISH[value] : undefined;
  return translated ?? value.replace(/^Ngày (?=\d)/, 'Date ')
    .replace(/^Tồn kho không quá (?=\d)/, 'Stock at or below ')
    .replace(/^Trên (?=\d)/, 'Above ').replace(/^Còn (?=\d)/, 'In stock ');
}
