import { Text, View } from 'react-native';
import { useTheme } from '../../theme/ThemeProvider';

/** Small native renderer: text stays selectable; model output is never HTML. */
export function MessageText({ text }: { text: string }) {
  const { ui } = useTheme();
  return <View>{text.split(/\n\n+/).map((paragraph, index) => <Text selectable key={index} style={[ui.markdown, ui.markdownParagraph]}>
    {paragraph.replace(/^#{1,3}\s/gm, '').split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
      part.startsWith('**') && part.endsWith('**')
        ? <Text key={i} style={{ fontWeight: '600' }}>{part.slice(2, -2)}</Text>
        : part
    )}
  </Text>)}</View>;
}
