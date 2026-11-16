// One material recipe per theme. Keep the visible edge independent of the
// backdrop tint, so it remains legible against both white cards and dark pages.
export function dockAppearance(dark: boolean) {
  return dark ? {
    frost: '#242428EB', solid: '#242428', edge: '#969BA866',
    nativeTint: '#2C2C2E3D',
  } : {
    frost: '#FAFAFCEB', solid: '#FAFAFC', edge: '#9297A366',
    nativeTint: '#FFFFFF1F',
  };
}
