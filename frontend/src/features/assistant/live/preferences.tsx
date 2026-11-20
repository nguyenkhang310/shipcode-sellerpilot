import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Pressable, Text, View } from 'react-native';
import { API_URL } from '../../../api/client';
import { SystemIcon } from '../../../components/ui/SystemIcon';
import { useTheme } from '../../../theme/ThemeProvider';
import { useAuth } from '../../auth/AuthProvider';
import { DEFAULT_LIVE_PREFERENCES, parseLivePreferences, type LivePreferences } from './locale';

const Preferences = createContext<null | {
  value: LivePreferences;
  ready: boolean;
  update: (change: Partial<LivePreferences>) => void;
}>(null);

export const useLivePreferences = () => useContext(Preferences);

export function LivePreferencesProvider({ children }: { children: ReactNode }) {
  const user = useAuth()?.user;
  const storageKey = 'sellerpilot:live:' + API_URL + ':' + user?.shop.slug + ':' + user?.user.id;
  const [stored, setStored] = useState<{ key: string; value: LivePreferences }>();
  const value = stored?.key === storageKey ? stored.value : DEFAULT_LIVE_PREFERENCES;
  const ready = stored?.key === storageKey;
  const current = useRef(value);
  const writes = useRef(Promise.resolve());

  useEffect(() => {
    let active = true;
    void AsyncStorage.getItem(storageKey).catch(() => null).then(raw => {
      if (!active) return;
      const preferences = parseLivePreferences(raw);
      current.current = preferences;
      setStored({ key: storageKey, value: preferences });
    });
    return () => { active = false; };
  }, [storageKey]);

  const context = useMemo(() => ({
    value, ready,
    update(change: Partial<LivePreferences>) {
      if (!ready) return;
      const next = { ...current.current, ...change };
      current.current = next;
      setStored({ key: storageKey, value: next });
      writes.current = writes.current.then(() => AsyncStorage.setItem(storageKey, JSON.stringify(next))).catch(() => {});
    },
  }), [ready, storageKey, value]);
  return <Preferences.Provider value={context}>{children}</Preferences.Provider>;
}

export function LiveVoiceSettings() {
  const preferences = useLivePreferences();
  const { ui, IOS, BRAND } = useTheme();
  if (!preferences) return null;
  const { value, update, ready } = preferences;

  function choices<Key extends keyof LivePreferences>(field: Key, title: string,
    options: ReadonlyArray<readonly [LivePreferences[Key], string]>) {
    return <View style={{ gap: 7 }}>
      <Text style={ui.caption}>{title}</Text>
      <View accessibilityRole="radiogroup" accessibilityLabel={title} style={{ flexDirection: 'row', gap: 7 }}>
        {options.map(([option, label]) => <Pressable key={option} disabled={!ready} accessibilityRole="radio"
          accessibilityLabel={label} aria-checked={value[field] === option}
          accessibilityState={{ checked: value[field] === option, disabled: !ready }}
          onPress={() => update({ [field]: option })}
          style={({pressed}) => ({ flex: 1, minWidth: 0, minHeight: 44, padding: 8, justifyContent: 'center',
            alignItems: 'center', borderRadius: 11, backgroundColor: value[field] === option ? BRAND.orangeSoft : IOS.fill,
            opacity: pressed || !ready ? .6 : 1 })}>
          <Text style={[ui.caption, { color: value[field] === option ? BRAND.orangeInk : IOS.label,
            fontWeight: value[field] === option ? '700' : '500', textAlign: 'center' }]}>{label}</Text>
        </Pressable>)}
      </View>
    </View>;
  }
  return <View style={ui.listCard} testID="live-voice-settings">
    <View style={ui.row}><SystemIcon name="mic-outline" size={21} color={BRAND.navy} />
      <Text accessibilityRole="header" style={ui.listTitle}>Giọng trợ lý</Text>
    </View>
    {choices('voice', 'Giọng nói', [['male', 'Nam'], ['female', 'Nữ']])}
    {choices('language', 'Ngôn ngữ trò chuyện Live', [['vi', 'Tiếng Việt'], ['en', 'English']])}
    <Text style={ui.caption}>Áp dụng khi mở phiên Live tiếp theo.</Text>
  </View>;
}
