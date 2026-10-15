import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEffect, useState } from 'react';
import { useColorScheme } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { AppShell } from './app/AppShell';
import { ThemeProvider } from './theme/ThemeProvider';

export default function App() {
  const systemScheme = useColorScheme();
  const [darkMode, setDarkMode] = useState(systemScheme === 'dark');

  useEffect(() => {
    let active = true;
    AsyncStorage.getItem('sellerpilot.theme').then((saved) => {
      if (active && (saved === 'dark' || saved === 'light')) setDarkMode(saved === 'dark');
    }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  const changeDarkMode = (value: boolean) => {
    setDarkMode(value);
    void AsyncStorage.setItem('sellerpilot.theme', value ? 'dark' : 'light').catch(() => undefined);
  };

  return (
    <SafeAreaProvider><ThemeProvider darkMode={darkMode}>
      <AppShell darkMode={darkMode} onDarkModeChange={changeDarkMode} />
    </ThemeProvider></SafeAreaProvider>
  );
}
