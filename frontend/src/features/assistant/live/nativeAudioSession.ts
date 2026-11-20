import { Platform } from 'react-native';

let audioWork = Promise.resolve();
let releaseUntil = 0;

export function runNativeAudioWork(work: () => Promise<void>) {
  const next = audioWork.then(work);
  audioWork = next.catch(() => {});
  return next;
}

export function noteNativeAudioRelease() {
  if (Platform.OS === 'ios') releaseUntil = Date.now() + 180;
}

export async function waitForNativeAudioRelease() {
  // Expo can deactivate AVAudioSession 100 ms after player.release() or
  // stream.stop(). Its playback registry doesn't include PCM AudioStreams.
  for (let delay = releaseUntil - Date.now(); delay > 0; delay = releaseUntil - Date.now()) {
    await new Promise<void>(resolve => setTimeout(resolve, delay));
  }
}
