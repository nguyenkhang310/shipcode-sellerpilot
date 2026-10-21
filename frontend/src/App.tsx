import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEffect, useRef, useState } from 'react';
import { useColorScheme } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { AppShell } from './app/AppShell';
import { ThemeProvider } from './theme/ThemeProvider';
import { isShopeeExtension } from './integrations/extension';
import { ExtensionShell } from './integrations/ExtensionShell';
import { AuthProvider } from './features/auth/AuthProvider';
import { AuthGate } from './features/auth/AuthGate';
import { warmBrandAssets } from './components/ui/brandAssets';

export default function App() {
  useEffect(() => { void warmBrandAssets(); }, []);
  const systemScheme = useColorScheme();
  const [darkMode, setDarkMode] = useState(systemScheme === 'dark');
  const manualChoice = useRef(false), storedChoice = useRef(false);
  const writes = useRef(Promise.resolve());

  useEffect(() => {
    let active = true;
    AsyncStorage.getItem('sellerpilot.theme').then((saved) => {
      if (active && !manualChoice.current && (saved === 'dark' || saved === 'light')) {
        storedChoice.current = true; setDarkMode(saved === 'dark');
      }
    }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!manualChoice.current && !storedChoice.current) setDarkMode(systemScheme === 'dark');
  }, [systemScheme]);

  const changeDarkMode = (value: boolean) => {
    manualChoice.current = true;
    setDarkMode(value);
    writes.current = writes.current.then(() => AsyncStorage.setItem('sellerpilot.theme', value ? 'dark' : 'light')).catch(() => undefined);
  };

  return (
    <SafeAreaProvider><ThemeProvider darkMode={darkMode} desktop={isShopeeExtension()}>
      {isShopeeExtension() ? <ExtensionShell /> : <AuthProvider><AuthGate><AppShell darkMode={darkMode} onDarkModeChange={changeDarkMode} /></AuthGate></AuthProvider>}
    </ThemeProvider></SafeAreaProvider>
  );
}
