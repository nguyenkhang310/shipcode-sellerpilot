import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';
import { getManagement } from '../../api/sellerPilot';
import { ApiError } from '../../api/client';
import { ManagementData } from '../../api/types';

const FRESH_FOR_MS = 60_000;
const shopDate = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' });
type Snapshot = { data: ManagementData; received: number; date: string };

/** Cache only this mounted shop session; writes and manual sync invalidate every period. */
export function useManagement(live = true) {
  const [state, setState] = useState<{ days: number; data: ManagementData | null; loading: boolean; refreshing: boolean; error: string }>({ days: 1, data: null, loading: true, refreshing: false, error: '' });
  const selected = useRef(1);
  const cache = useRef(new Map<number, Snapshot>());
  const request = useRef<AbortController | null>(null);
  const generation = useRef(0);

  const load = useCallback(async (days: number, force = false, background = false, pull = false) => {
    selected.current = days;
    const version = ++generation.current;
    request.current?.abort();
    request.current = null;
    if (force && !background) cache.current.clear();
    const saved = cache.current.get(days);
    if (!force && saved && Date.now() - saved.received < FRESH_FOR_MS && saved.date === shopDate()) {
      setState({ days, data: saved.data, loading: false, refreshing: false, error: '' });
      return;
    }
    const controller = new AbortController();
    request.current = controller;
    // Retain shop-wide counters and card geometry. The screen hides all
    // period-specific values until the selected response arrives.
    // RefreshControl must only run for an actual pull gesture. Starting it for
    // a range change adjusts the native iOS scroll inset and moves the page.
    if (!background) setState(previous => ({ days, data: previous.data, loading: true, refreshing: pull, error: '' }));
    try {
      const response = await getManagement(days, controller.signal);
      if (controller.signal.aborted || generation.current !== version) return;
      if (response.data.days !== days) throw new Error('Kỳ số liệu trả về không khớp. Vui lòng đồng bộ lại.');
      const unchanged = saved && JSON.stringify({ ...saved.data, updated_at: undefined }) === JSON.stringify({ ...response.data, updated_at: undefined });
      // New orders invalidate the other ranges too; an unchanged background
      // read preserves warmed periods and avoids re-rendering the whole page.
      if (saved && !unchanged) cache.current.clear();
      cache.current.set(days, { data: response.data, received: Date.now(), date: shopDate() });
      setState(previous => background && unchanged && !previous.error && !previous.loading
        ? previous : { days, data: response.data, loading: false, refreshing: false, error: '' });
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
        void load(selected.current, true, true);
      }
    };
    poll();
    const timer = setInterval(poll, 5000);
    const listener = AppState.addEventListener('change', state => { if (state === 'active') poll(); });
    return () => { clearInterval(timer); listener.remove(); };
  }, [live, load]);

  const onDays = useCallback((days: number) => {
    if (days !== selected.current) void load(days);
  }, [load]);
  const refresh = useCallback(() => load(selected.current, true), [load]);
  const pullRefresh = useCallback(() => load(selected.current, true, false, true), [load]);
  const ensureFresh = useCallback(() => {
    if (!request.current) void load(selected.current);
  }, [load]);

  return { ...state, onDays, refresh, pullRefresh, ensureFresh };
}
