import { createContext, ReactNode, useContext, useMemo } from 'react';
import { BRAND, DARK_IOS, LIGHT_IOS } from './tokens';
import { createMobileStyles } from './mobileStyles';

function buildTheme(darkMode: boolean) {
  const IOS = darkMode ? DARK_IOS : LIGHT_IOS;
  const brand = {
    ...BRAND,
    navy: darkMode ? '#9EB9DC' : BRAND.navy,
    navyDeep: darkMode ? '#101A2A' : BRAND.navyDeep,
  };
  return { IOS, BRAND: brand, isDark: darkMode, ui: createMobileStyles(IOS, darkMode, brand) };
}

const ThemeContext = createContext<ReturnType<typeof buildTheme> | null>(null);

export function ThemeProvider({ darkMode, children }: { darkMode: boolean; children: ReactNode }) {
  const theme = useMemo(() => buildTheme(darkMode), [darkMode]);
  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const theme = useContext(ThemeContext);
  if (!theme) throw new Error('useTheme requires ThemeProvider');
  return theme;
}
