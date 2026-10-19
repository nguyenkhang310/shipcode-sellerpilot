import { Ionicons } from '@expo/vector-icons';
import { Image, Pressable, Text, View } from 'react-native';
import { BrandLogo } from '../ui/BrandLogo';
import { useTheme } from '../../theme/ThemeProvider';
import { MainTab } from './BottomNav';

const ACCOUNT_LOGO = require('../../../assets/hcm-ute-account-logo.png');

export function TopBar({ tab, onProfile, onTasks, onHistory, onNewChat, hasTasks }: {
  tab: MainTab; onProfile: () => void; onTasks: () => void; onHistory: () => void; onNewChat: () => void; hasTasks: boolean;
}) {
  const { ui, IOS } = useTheme();
  return <View style={ui.header}>
    <View style={[ui.row, ui.grow]}>{tab === 'assistant' ? <Pressable accessibilityRole="button" accessibilityLabel="Lịch sử trò chuyện" onPress={onHistory} style={ui.circleButton}><Ionicons name="menu-outline" size={25} color={IOS.label} /></Pressable> : <BrandLogo size={42} />}
      <View style={ui.grow}><Text numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.8} style={ui.headerBrand}>SellerPilot</Text></View>
    </View><View style={[ui.row, { gap: 9 }]}><Pressable accessibilityRole="button" accessibilityLabel={tab === 'assistant' ? 'Tạo cuộc trò chuyện mới' : 'Việc cần xử lý'} onPress={tab === 'assistant' ? onNewChat : onTasks} style={ui.circleButton}><Ionicons name={tab === 'assistant' ? 'create-outline' : 'notifications-outline'} size={21} color={IOS.label} />{tab === 'home' && hasTasks ? <View style={ui.notificationDot} /> : null}</Pressable><Pressable accessibilityRole="button" accessibilityLabel="Cài đặt shop và giao diện" onPress={onProfile} style={{ minHeight: 44, minWidth: 44, alignItems: 'center', justifyContent: 'center' }}><View style={ui.avatar}><Image accessibilityLabel="Logo Trường Đại học Sư phạm Kỹ thuật Thành phố Hồ Chí Minh" source={ACCOUNT_LOGO} resizeMode="contain" fadeDuration={0} style={ui.avatarImage} /></View></Pressable></View>
  </View>;
}
