import { useCallback, useEffect, useRef, useState } from 'react';
import { getManagement } from '../../api/sellerPilot';
import { ApiError } from '../../api/client';
import { ManagementData } from '../../api/types';

const FRESH_FOR_MS = 60_000;
const shopDate = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' });
type Snapshot = { data: ManagementData; received: number; date: string };

/** Cache only this mounted shop session; writes and manual sync invalidate every period. */
export function useManagement() {
  const [state, setState] = useState<{ days: number; data: ManagementData | null; loading: boolean; error: string }>({ days: 1, data: null, loading: true, error: '' });
  const selected = useRef(1);
  const cache = useRef(new Map<number, Snapshot>());
  const request = useRef<AbortController | null>(null);
  const generation = useRef(0);

  const load = useCallback(async (days: number, force = false) => {
    selected.current = days;
    const version = ++generation.current;
    request.current?.abort();
    request.current = null;
    if (force) cache.current.clear();
    const saved = cache.current.get(days);
    if (saved && Date.now() - saved.received < FRESH_FOR_MS && saved.date === shopDate()) {
      setState({ days, data: saved.data, loading: false, error: '' });
      return;
    }
    const controller = new AbortController();
    request.current = controller;
    // Retain shop-wide counters and card geometry. The screen hides all
    // period-specific values until the selected response arrives.
    setState(previous => ({ days, data: previous.data, loading: true, error: '' }));
    try {
      const response = await getManagement(days, controller.signal);
      if (controller.signal.aborted || generation.current !== version) return;
      if (response.data.days !== days) throw new Error('Kỳ số liệu trả về không khớp. Vui lòng đồng bộ lại.');
      cache.current.set(days, { data: response.data, received: Date.now(), date: shopDate() });
      setState({ days, data: response.data, loading: false, error: '' });
    } catch (error) {
      if (controller.signal.aborted || generation.current !== version) return;
      setState(previous => ({ ...previous, loading: false, error: error instanceof ApiError ? error.message : error instanceof Error && error.message.startsWith('Kỳ số liệu') ? error.message : 'Vui lòng kiểm tra Wi-Fi và backend trên máy của bạn.' }));
    } finally {
      if (request.current === controller) request.current = null;
    }
  }, []);

  useEffect(() => {
    void load(1);
    return () => { ++generation.current; request.current?.abort(); };
  }, [load]);

  const onDays = useCallback((days: number) => {
    if (days !== selected.current) void load(days);
  }, [load]);
  const refresh = useCallback(() => load(selected.current, true), [load]);
  const ensureFresh = useCallback(() => {
    if (!request.current) void load(selected.current);
  }, [load]);

  return { ...state, onDays, refresh, ensureFresh };
}
