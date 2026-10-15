const numberFormat = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 0 });
export const count = (value: number) => numberFormat.format(value);
export const money = (value: number) => count(value) + '₫';
