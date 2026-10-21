import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';
import { getManagement } from '../../api/sellerPilot';
import { ApiError } from '../../api/client';
import { ManagementData } from '../../api/types';
import { matchesPeriod, todayInShop } from './dates';

const FRESH_FOR_MS = 60_000;
type Snapshot = { data: ManagementData; received: number; date: string };

/** Cache only this mounted shop session; writes and manual sync invalidate every period. */
export function useManagement(live = true) {
  const [state, setState] = useState<{ days: number; selectedDate: string | null; data: ManagementData | null; loading: boolean; refreshing: boolean; error: string }>({ days: 1, selectedDate: null, data: null, loading: true, refreshing: false, error: '' });
  const selected = useRef<{ days: number; date: string | null }>({ days: 1, date: null });
  const cache = useRef(new Map<string, Snapshot>());
  const request = useRef<AbortController | null>(null);
  const generation = useRef(0);

  const load = useCallback(async (days: number, force = false, background = false, pull = false, date: string | null = null) => {
    selected.current = { days, date };
    const key = date ? 'day:' + date : 'range:' + days;
    const version = ++generation.current;
    request.current?.abort();
    request.current = null;
    if (force && !background) cache.current.clear();
    const saved = cache.current.get(key);
    if (!force && saved && Date.now() - saved.received < FRESH_FOR_MS && saved.date === todayInShop()) {
      setState({ days, selectedDate: date, data: saved.data, loading: false, refreshing: false, error: '' });
      return;
    }
    const controller = new AbortController();
    request.current = controller;
    // Retain shop-wide counters and card geometry. The screen hides all
    // period-specific values until the selected response arrives.
    // RefreshControl must only run for an actual pull gesture. Starting it for
    // a range change adjusts the native iOS scroll inset and moves the page.
    if (!background) setState(previous => ({ days, selectedDate: date, data: previous.data, loading: true, refreshing: pull, error: '' }));
    try {
      const response = await getManagement(days, controller.signal, date);
      if (controller.signal.aborted || generation.current !== version) return;
      if (!matchesPeriod(response.data, days, date)) throw new Error('Kỳ số liệu trả về không khớp. Vui lòng đồng bộ lại.');
      const unchanged = saved && JSON.stringify({ ...saved.data, updated_at: undefined }) === JSON.stringify({ ...response.data, updated_at: undefined });
      // New orders invalidate the other ranges too; an unchanged background
      // read preserves warmed periods and avoids re-rendering the whole page.
      if (saved && !unchanged) cache.current.clear();
      cache.current.set(key, { data: response.data, received: Date.now(), date: todayInShop() });
      setState(previous => background && unchanged && !previous.error && !previous.loading
        ? previous : { days, selectedDate: date, data: response.data, loading: false, refreshing: false, error: '' });
    } catch (error) {
      if (controller.signal.aborted || generation.current !== version) return;
      setState(previous => ({ ...previous, loading: false, refreshing: false, error: error instanceof ApiError ? error.message : error instanceof Error && error.message.startsWith('Kỳ số liệu') ? error.message : 'Vui lòng kiểm tra Wi-Fi và backend trên máy của bạn.' }));
    } finally {
      if (request.current === controller) request.current = null;
    }
  }, []);

  useEffect(() => {
    void load(1);
    return () => { ++generation.current; request.current?.abort(); };
  }, [load]);

  useEffect(() => {
    if (!live) return;
    const poll = () => {
      if (AppState.currentState !== 'background' && AppState.currentState !== 'inactive' && !request.current) {
        void load(selected.current.days, true, true, false, selected.current.date);
      }
    };
    poll();
    const timer = setInterval(poll, 5000);
    const listener = AppState.addEventListener('change', state => { if (state === 'active') poll(); });
    return () => { clearInterval(timer); listener.remove(); };
  }, [live, load]);

  const onDays = useCallback((days: number) => {
    if (days !== selected.current.days || selected.current.date) void load(days);
  }, [load]);
  const onDate = useCallback((date: string) => {
    const chosen = date === todayInShop() ? null : date;
    if (selected.current.days !== 1 || selected.current.date !== chosen) void load(1, false, false, false, chosen);
  }, [load]);
  const refresh = useCallback(() => load(selected.current.days, true, false, false, selected.current.date), [load]);
  const pullRefresh = useCallback(() => load(selected.current.days, true, false, true, selected.current.date), [load]);
  const ensureFresh = useCallback(() => {
    if (!request.current) void load(selected.current.days, false, false, false, selected.current.date);
  }, [load]);

  return { ...state, onDays, onDate, refresh, pullRefresh, ensureFresh };
}
