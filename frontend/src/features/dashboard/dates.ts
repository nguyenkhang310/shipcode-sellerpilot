import type { ManagementData } from '../../api/types';

export const todayInShop = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' });
export const shiftDay = (date: string, amount: number) => {
  const value = new Date(date + 'T12:00:00Z');
  value.setUTCDate(value.getUTCDate() + amount);
  return value.toISOString().slice(0, 10);
};
export const displayDate = (date: string) => date.slice(8, 10) + '/' + date.slice(5, 7) + '/' + date.slice(0, 4);
export const matchesPeriod = (data: ManagementData | null, days: number, date: string | null) => Boolean(data && data.days === days && (date ? data.from_date === date && data.to_date === date : !data.selected_date));
