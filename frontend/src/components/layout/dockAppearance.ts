// One material recipe per theme. Keep the visible edge independent of the
// backdrop tint, so it remains legible against both white cards and dark pages.
export function dockAppearance(dark: boolean) {
  return dark ? {
    frost: '#252D3AD9', solid: '#252B35', edge: '#8292AC8A',
    highlight: '#DEE9FF66', nativeTint: '#9EB9DC0A',
  } : {
    frost: '#FFFFFFD9', solid: '#FAFAFC', edge: '#8795A77A',
    highlight: '#FFFFFFE6', nativeTint: '#FFFFFF14',
  };
}
