import { createContext, ReactNode, useContext, useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';
import { apiRequest, ApiError, onUnauthorized, setAccessToken } from '../../api/client';
import * as storage from './sessionStorage';

export type SellerIdentity = { user: { id: number; username: string; email: string }; shop: { slug: string; name: string; role: string }; expires_at: string };
type Phase = 'checking' | 'signed_out' | 'signed_in' | 'locked';
type AuthState = { phase: Phase; user: SellerIdentity | null; busy: boolean; error: string; privateScreen: boolean; biometric: boolean;
  capability: { available: boolean; label: string; reason: string };
  signIn: (login: string, password: string) => Promise<void>; unlock: () => Promise<void>; signOut: () => Promise<void>;
  changeBiometric: (enabled: boolean) => Promise<void>; lock: () => void; usePassword: () => void };
const AuthContext = createContext<AuthState | null>(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>('checking'), [user, setUser] = useState<SellerIdentity | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [privateScreen, setPrivateScreen] = useState(false);
  const [biometric, setBiometric] = useState(false), [capability, setCapability] = useState({ available: false, label: 'Face ID', reason: 'loading' });
  const epoch = useRef(0), token = useRef<string | null>(null), working = useRef(false), bio = useRef(false);
  bio.current = biometric;
  const clearMemory = () => { token.current = null; setAccessToken(null); };
  const lock = () => { ++epoch.current; working.current = false; setBusy(false); clearMemory(); setPhase(bio.current ? 'locked' : 'signed_out'); };
  const expired = () => {
    ++epoch.current; working.current = false; setBusy(false); clearMemory(); setUser(null); setPhase('signed_out'); setBiometric(false);
    setError('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.');
    void storage.clearCredentials().catch(() => {});
  };
  const verify = async (value: string | null, version: number) => {
    if (version !== epoch.current) return;
    setAccessToken(value);
    const result = await apiRequest<SellerIdentity>('/auth/me');
    if (!result.data?.user?.id || !result.data.shop?.slug) throw new ApiError(502, 'Chưa xác minh được tài khoản. Vui lòng thử lại.');
    if (version !== epoch.current) return;
    token.current = value; setUser(result.data); setPhase('signed_in'); setError('');
  };
  useEffect(() => {
    const version = ++epoch.current;
    onUnauthorized(expired);
    void storage.biometricCapability().then(setCapability);
    void (async () => {
      try {
        const enabled = await storage.biometricEnabled();
        if (version !== epoch.current) return;
        setBiometric(enabled);
        if (enabled) { setPhase('locked'); return; }
        await verify(await storage.savedToken(false), version);
      } catch (e) {
        if (version !== epoch.current) return;
        clearMemory(); setPhase('signed_out');
        if (!(e instanceof ApiError && e.status === 401)) setError('Chưa kết nối được SellerPilot. Bạn có thể thử đăng nhập lại.');
      }
    })();
    const listener = AppState.addEventListener('change', next => {
      setPrivateScreen(next !== 'active');
      if (storage.native && next === 'background' && bio.current) lock();
    });
    return () => { ++epoch.current; clearMemory(); onUnauthorized(); listener.remove(); };
  }, []);
  const signIn = async (login: string, password: string) => {
    if (working.current) return;
    const version = ++epoch.current; working.current = true; setBusy(true); setError('');
    try {
      const { data } = await apiRequest<SellerIdentity & { token: string }>('/auth/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ login_id: login.trim(), password }), timeoutMs: 15000,
      });
      if (version !== epoch.current) return;
      if (!data.token || !data.user?.id || !data.shop?.slug) throw new ApiError(502, 'Chưa xác minh được tài khoản. Vui lòng thử lại.');
      try { await storage.savePasswordSession(data.token); }
      catch (e) {
        await apiRequest('/auth/logout', { method: 'POST', headers: { Authorization: 'Bearer ' + data.token } }).catch(() => {});
        throw e;
      }
      if (version !== epoch.current) return;
      const { token: secret, ...identity } = data;
      token.current = secret; setAccessToken(secret); setBiometric(false); setUser(identity); setPhase('signed_in');
    } catch (e) { if (version === epoch.current) setError(e instanceof ApiError ? e.message : 'Chưa đăng nhập được. Kiểm tra kết nối rồi thử lại.'); }
    finally { if (version === epoch.current) { working.current = false; setBusy(false); } }
  };
  const unlock = async () => {
    if (working.current) return;
    const version = ++epoch.current; working.current = true; setBusy(true); setError('');
    try {
      const value = await storage.savedToken(true);
      if (version !== epoch.current) return;
      if (!value) { expired(); return; }
      await verify(value, version);
    } catch (e) {
      if (version !== epoch.current) return;
      clearMemory();
      if (e instanceof ApiError && e.status === 401) expired();
      else setError(e instanceof ApiError ? e.message : 'Chưa mở khóa được. Bạn có thể thử lại hoặc dùng mật khẩu.');
    } finally { if (version === epoch.current) { working.current = false; setBusy(false); } }
  };
  const signOut = async () => {
    if (working.current) return;
    working.current = true; setBusy(true);
    let revoked = false;
    try { await apiRequest('/auth/logout', { method: 'POST' }); revoked = true; }
    catch (e) { revoked = e instanceof ApiError && e.status === 401; }
    finally {
      ++epoch.current; clearMemory(); setUser(null); setPhase('signed_out'); setBiometric(false);
      await storage.clearCredentials().catch(() => {}); working.current = false; setBusy(false);
      setError(revoked ? '' : 'Đã đăng xuất trên thiết bị. Chưa xác nhận thu hồi phiên trên server do mất kết nối.');
    }
  };
  const changeBiometric = async (enabled: boolean) => {
    if (working.current || !token.current || !capability.available) return;
    const version = epoch.current; working.current = true; setBusy(true); setError('');
    try {
      if (enabled) await storage.protectSession(token.current); else await storage.unprotectSession();
      if (version === epoch.current) { bio.current = enabled; setBiometric(enabled); if (enabled && AppState.currentState === 'background') lock(); }
    } catch { if (version === epoch.current) setError('Chưa thay đổi được bảo mật. Vui lòng thử lại.'); }
    finally { if (version === epoch.current) { working.current = false; setBusy(false); } }
  };
  return <AuthContext.Provider value={{ phase, user, busy, error, privateScreen, biometric, capability, signIn, unlock, signOut, changeBiometric, lock,
    usePassword: () => { ++epoch.current; clearMemory(); setPhase('signed_out'); setError(''); working.current = false; setBusy(false); } }}>{children}</AuthContext.Provider>;
}
