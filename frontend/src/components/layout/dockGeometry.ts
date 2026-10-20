export const DOCK_HEIGHT = 104;
export const DOCK_BAR_TOP = 28;
export const ASSISTANT_BUTTON_SIZE = 72;

// Includes the raised button, safe area and breathing room for the last action.
export const dockContentInset = (safeBottom: number) => DOCK_HEIGHT + Math.max(safeBottom, 12) + 16;

export function dockPath(width: number) {
  const c = width / 2, r = 38, top = DOCK_BAR_TOP, bottom = DOCK_HEIGHT;
  return `M ${r} ${top} H ${c - 54} C ${c - 41} ${top} ${c - 43} 80 ${c} 80 C ${c + 43} 80 ${c + 41} ${top} ${c + 54} ${top} H ${width - r} Q ${width} ${top} ${width} ${top + r} V ${bottom - r} Q ${width} ${bottom} ${width - r} ${bottom} H ${r} Q 0 ${bottom} 0 ${bottom - r} V ${top + r} Q 0 ${top} ${r} ${top} Z`;
}
