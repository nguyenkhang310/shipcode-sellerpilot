import { StyleSheet } from 'react-native';
import { createMobileStyles } from './mobileStyles';
import { LIGHT_IOS } from './tokens';

// Keep the input's font/line/padding identical to its measurement mirror.
// The browser layout has no mobile safe-area spacer or floating bottom dock.
export function createExtensionStyles(base: ReturnType<typeof createMobileStyles>, colors: typeof LIGHT_IOS) {
  return {...base, ...StyleSheet.create({
    chat: {...base.chat, backgroundColor: colors.bg, minHeight: 0},
    chatScroll: {...base.chatScroll, paddingHorizontal: 14, paddingTop: 16, paddingBottom: 12},
    chatEmpty: {...base.chatEmpty, paddingTop: 24, paddingBottom: 20},
    welcomeTitle: {...base.welcomeTitle, fontSize: 23, lineHeight: 30, letterSpacing: -.5},
    promptGrid: {...base.promptGrid, marginTop: 22, gap: 8},
    prompt: {...base.prompt, minHeight: 76, padding: 12, borderRadius: 12, gap: 8},
    promptText: {...base.promptText, fontSize: 12, lineHeight: 18},
    thread: {...base.thread, gap: 14},
    userBubble: {...base.userBubble, paddingHorizontal: 13, paddingVertical: 9, borderRadius: 15},
    userText: {...base.userText, fontSize: 14, lineHeight: 21},
    assistantBubble: {...base.assistantBubble, paddingHorizontal: 13, paddingVertical: 11, borderRadius: 13},
    markdown: {...base.markdown, fontSize: 14, lineHeight: 22},
    circleButton: {...base.circleButton, width: 34, height: 34, borderRadius: 9},
    composerArea: {...base.composerArea, paddingHorizontal: 12, paddingTop: 8},
    composer: {...base.composer, borderRadius: 18, minHeight: 58, padding: 6},
    caption: {...base.caption, fontSize: 12, lineHeight: 18},
    primaryButton: {...base.primaryButton, minHeight: 36, borderRadius: 8, paddingVertical: 8, paddingHorizontal: 12},
    secondaryButton: {...base.secondaryButton, minHeight: 36, borderRadius: 8, paddingVertical: 8, paddingHorizontal: 12},
    primaryText: {...base.primaryText, fontSize: 13},
    secondaryText: {...base.secondaryText, fontSize: 13},
    listTitle: {...base.listTitle, fontSize: 14, lineHeight: 20},
    errorCard: {...base.errorCard, padding: 12, borderRadius: 10, marginVertical: 8, gap: 8},
    draftImage: {...base.draftImage, height: 180},
    attachmentScroller: {...base.attachmentScroller, height: 84, maxHeight: 84},
    attachmentPreview: {...base.attachmentPreview, width: 64, height: 64},
    historyDrawer: {...base.historyDrawer, maxWidth: 340},
  })};
}
