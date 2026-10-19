import { createContext, ReactNode, useContext, useMemo } from 'react';
import { BRAND, DARK_IOS, LIGHT_IOS } from './tokens';
import { createMobileStyles } from './mobileStyles';
import { createExtensionStyles } from './extensionStyles';

function buildTheme(darkMode: boolean, desktop: boolean) {
  const IOS = darkMode ? DARK_IOS : LIGHT_IOS;
  const brand = {
    ...BRAND,
    navy: darkMode ? '#9EB9DC' : BRAND.navy,
    navyDeep: darkMode ? '#101A2A' : BRAND.navyDeep,
  };
  const mobile = createMobileStyles(IOS, darkMode, brand);
  return { IOS, BRAND: brand, isDark: darkMode, desktop, ui: desktop ? createExtensionStyles(mobile, IOS) : mobile };
}

const ThemeContext = createContext<ReturnType<typeof buildTheme> | null>(null);

export function ThemeProvider({ darkMode, desktop = false, children }: { darkMode: boolean; desktop?: boolean; children: ReactNode }) {
  const theme = useMemo(() => buildTheme(darkMode, desktop), [darkMode, desktop]);
  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const theme = useContext(ThemeContext);
  if (!theme) throw new Error('useTheme requires ThemeProvider');
  return theme;
}
