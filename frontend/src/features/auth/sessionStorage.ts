import Constants, { ExecutionEnvironment } from 'expo-constants';
import * as SecureStore from 'expo-secure-store';
import * as LocalAuthentication from 'expo-local-authentication';
import { Platform } from 'react-native';
import { API_URL } from '../../api/client';

const namespace = Array.from(API_URL).map(char => char.charCodeAt(0).toString(16).padStart(4, '0')).join('');
const key = (name: string) => 'sellerpilot.auth.' + namespace + '.' + name;
const plain = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };
const protectedOptions = { ...plain, keychainService: 'sellerpilot.biometric', requireAuthentication: true, authenticationPrompt: 'Mở khóa SellerPilot' };
export const native = Platform.OS !== 'web';
let mutations = Promise.resolve();
function serial(work: () => Promise<void>) {
  const pending = mutations.catch(() => {}).then(work);
  mutations = pending.catch(() => {});
  return pending;
}

export async function biometricCapability() {
  const face = Platform.OS === 'ios';
  const label = face ? 'Face ID' : 'Sinh trắc học';
  if (!native) return { available: false, label, reason: 'web' };
  if (Constants.executionEnvironment === ExecutionEnvironment.StoreClient) return { available: false, label, reason: 'build' };
  try {
    const types = await LocalAuthentication.supportedAuthenticationTypesAsync();
    const name = face && types.includes(LocalAuthentication.AuthenticationType.FACIAL_RECOGNITION) ? 'Face ID' : face ? 'Touch ID' : 'Sinh trắc học';
    return { available: await LocalAuthentication.hasHardwareAsync() && await LocalAuthentication.isEnrolledAsync() && SecureStore.canUseBiometricAuthentication(), label: name, reason: 'enrollment' };
  } catch { return { available: false, label, reason: 'unavailable' }; }
}

export const biometricEnabled = async () => {
  await mutations;
  return native && await SecureStore.getItemAsync(key('signedout')) !== '1' && await SecureStore.getItemAsync(key('biometric')) === '1';
};
export const savedToken = async (biometric: boolean) => {
  await mutations;
  if (!native || await SecureStore.getItemAsync(key('signedout')) === '1') return null;
  return SecureStore.getItemAsync(key(biometric ? 'protected' : 'session'), biometric ? protectedOptions : plain);
};
async function clearStored() {
  if (!native) return;
  // Durable tombstone prevents a failed key deletion restoring a logged-out
  // session on the next launch (including while the server is offline).
  await SecureStore.setItemAsync(key('signedout'), '1', plain);
  await Promise.all([SecureStore.deleteItemAsync(key('session'), plain), SecureStore.deleteItemAsync(key('protected'), protectedOptions), SecureStore.deleteItemAsync(key('biometric'))]);
}
export const clearCredentials = () => serial(clearStored);
export const savePasswordSession = (token: string) => serial(async () => {
  if (!native) return;
  await clearStored();
  await SecureStore.setItemAsync(key('session'), token, plain);
  await SecureStore.deleteItemAsync(key('signedout'));
});
export const protectSession = (token: string) => serial(async () => {
  if (!native) return;
  await SecureStore.setItemAsync(key('signedout'), '1', plain);
  await SecureStore.setItemAsync(key('protected'), token, protectedOptions);
  await SecureStore.deleteItemAsync(key('session'), plain);
  await SecureStore.setItemAsync(key('biometric'), '1');
  await SecureStore.deleteItemAsync(key('signedout'));
});
export const unprotectSession = () => serial(async () => {
  if (!native) return;
  const token = await SecureStore.getItemAsync(key('protected'), protectedOptions);
  if (!token) throw new Error('Vui lòng đăng nhập bằng mật khẩu để thay đổi bảo mật.');
  await SecureStore.setItemAsync(key('signedout'), '1', plain);
  await SecureStore.setItemAsync(key('session'), token, plain);
  await SecureStore.deleteItemAsync(key('biometric'));
  await SecureStore.deleteItemAsync(key('protected'), protectedOptions);
  await SecureStore.deleteItemAsync(key('signedout'));
});
