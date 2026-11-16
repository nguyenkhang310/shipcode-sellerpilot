import { Platform } from 'react-native';

export const DOCK_HEIGHT = 86;
export const DOCK_BAR_TOP = 20;
export const DOCK_RADIUS = (DOCK_HEIGHT - DOCK_BAR_TOP) / 2;
export const ASSISTANT_BUTTON_SIZE = 62;

// An iPhone's bottom inset includes the space ABOVE the home indicator. A
// floating control can use part of that space, while staying clear of the
// indicator itself. Android must retain its entire navigation-system inset.
export const dockBottomInset = (safeBottom: number) => Platform.OS === 'ios' && safeBottom >= 30
  ? Math.max(12, safeBottom - 18) : Math.max(safeBottom, 8);

// Includes the raised button, safe area and breathing room for the last action.
export const dockContentInset = (safeBottom: number) => DOCK_HEIGHT + dockBottomInset(safeBottom) + 12;

export function dockPath(width: number) {
  const c = width / 2, r = DOCK_RADIUS, top = DOCK_BAR_TOP, bottom = DOCK_HEIGHT;
  const lip = ASSISTANT_BUTTON_SIZE / 2 + 15, depth = ASSISTANT_BUTTON_SIZE + 5;
  return `M ${r} ${top} H ${c - lip} C ${c - 37} ${top} ${c - 39} ${depth} ${c} ${depth} C ${c + 39} ${depth} ${c + 37} ${top} ${c + lip} ${top} H ${width - r} Q ${width} ${top} ${width} ${top + r} V ${bottom - r} Q ${width} ${bottom} ${width - r} ${bottom} H ${r} Q 0 ${bottom} 0 ${bottom - r} V ${top + r} Q 0 ${top} ${r} ${top} Z`;
}
