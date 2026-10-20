import Svg, { Path, Rect } from 'react-native-svg';

// One optical size and stroke weight for navigation and task shortcuts.
// Functional controls such as close/send retain their platform glyphs.
export type InterfaceIconName = 'overview' | 'products' | 'assistant' | 'orders' | 'shop' | 'trend' | 'inventory' | 'search' | 'plan';
export function InterfaceIcon({ name, size = 24, color }: { name: InterfaceIconName; size?: number; color: string }) {
  const drawing = {
    overview: <><Rect x={3.5} y={3.5} width={6} height={7} rx={1.2} /><Rect x={14.5} y={3.5} width={6} height={7} rx={1.2} /><Rect x={3.5} y={15} width={6} height={5.5} rx={1.2} /><Rect x={14.5} y={15} width={6} height={5.5} rx={1.2} /></>,
    products: <><Path d="m12 3 8.5 4.7v8.6L12 21l-8.5-4.7V7.7L12 3Z" /><Path d="m3.5 7.7 8.5 4.8 8.5-4.8M12 12.5V21M7.8 5.3l8.5 4.8" /></>,
    assistant: <Path d="M8 20.5H5a1.5 1.5 0 0 1-1.5-1.5V5A1.5 1.5 0 0 1 5 3.5h14A1.5 1.5 0 0 1 20.5 5v10a1.5 1.5 0 0 1-1.5 1.5h-7L8 20.5ZM8 8h8M8 12h5" />,
    orders: <Path d="M6 3.5h12v17l-3-1.8-3 1.8-3-1.8-3 1.8v-17ZM9 8h6M9 12h6M9 16h3" />,
    shop: <><Path d="M4.5 8.5h15l1 11a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1l1-11Z" /><Path d="M8 9V7a4 4 0 0 1 8 0v2" /></>,
    trend: <><Path d="M4 4v16h16M7.5 14l4-4 3 2 5-6M16 6h3.5v3.5" /></>,
    inventory: <><Rect x={3.5} y={4} width={17} height={4.5} rx={1} /><Path d="M5 8.5V20h14V8.5M9 12h6" /></>,
    search: <><Path d="M16.5 16.5 21 21" /><Path d="M18.5 10.5a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z" /></>,
    plan: <><Rect x={4} y={5.5} width={16} height={15} rx={2} /><Path d="M8 3v5M16 3v5M4 10.5h16M8 14h3M8 17h6" /></>,
  }[name];
  return <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={1.65} strokeLinecap="round" strokeLinejoin="round" accessible={false} accessibilityElementsHidden importantForAccessibility="no">{drawing}</Svg>;
}
