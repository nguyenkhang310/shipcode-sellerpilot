import { AudioModule, createAudioPlayer, requestRecordingPermissionsAsync, setAudioModeAsync } from 'expo-audio';
import { File, Paths } from 'expo-file-system';
import { createMessageId } from '../../../api/chatRequests';
import { MAX_PLAYBACK_SECONDS, NATIVE_REPLY_RATE, REPLY_SAMPLE_RATE, ReplyLead, ReplyVolume, type AudioCallbacks, type LiveAudio } from './audioTypes';
import { noteNativeAudioRelease, runNativeAudioWork, waitForNativeAudioRelease } from './nativeAudioSession';

const BYTES_PER_SECOND = REPLY_SAMPLE_RATE * 2;
// Bound pending PCM for very long replies.
const BUFFER_BYTES = BYTES_PER_SECOND * 18;
type Clip = { file: File; ready: Promise<void>; bytes: number };

function wav(chunks: Uint8Array[], size: number, volume: ReplyVolume) {
  const result = new Uint8Array(44 + size);
  const header = new DataView(result.buffer);
  header.setUint32(0, 0x52494646); // RIFF
  header.setUint32(4, 36 + size, true);
  header.setUint32(8, 0x57415645); // WAVE
  header.setUint32(12, 0x666d7420); // fmt
  header.setUint32(16, 16, true);
  header.setUint16(20, 1, true);
  header.setUint16(22, 1, true);
  header.setUint32(24, REPLY_SAMPLE_RATE, true);
  header.setUint32(28, BYTES_PER_SECOND, true);
  header.setUint16(32, 2, true);
  header.setUint16(34, 16, true);
  header.setUint32(36, 0x64617461); // data
  header.setUint32(40, size, true);
  let offset = 44;
  for (const chunk of chunks) {
    const samples = new DataView(chunk.buffer, chunk.byteOffset, chunk.byteLength);
    for (let i = 0; i < chunk.length; i += 2) {
      header.setInt16(offset, Math.round(volume.sample(samples.getInt16(i, true) / 32768) * 32767), true);
      offset += 2;
    }
  }
  return result;
}

export function createLiveAudio(callbacks: AudioCallbacks): LiveAudio {
  const Stream = AudioModule.AudioStream;
  if (!Stream) throw new Error('Bản app này chưa hỗ trợ micro Live. Cập nhật Expo Go hỗ trợ SDK 58 hoặc mở app bằng web.');
  const stream = new Stream({ sampleRate: 16_000, channels: 1, encoding: 'int16' });
  const playbackRate = callbacks.vietnamese ? 1.02 : NATIVE_REPLY_RATE;
  let player: ReturnType<typeof createAudioPlayer> | undefined;
  let listener: { remove: () => void } | undefined;
  let file: File | undefined;
  let playbackTimeout: ReturnType<typeof setTimeout> | undefined;
  let closed = false, muted = false, playing = false, capturing = false, configured = false;
  let playbackMode = false;
  let generation = 0, bufferedBytes = 0, queuedBytes = 0;
  let replyLead: ReplyLead | undefined = new ReplyLead();
  let volume = new ReplyVolume();
  let receivingReply = false;
  let buffer: Uint8Array[] = [];
  const queue: Clip[] = [];
  const mic = stream.addListener('audioStreamBuffer', packet => {
    // Keep playback out of the mic on devices without acoustic echo cancellation.
    if (!closed && !muted && !playing && !receivingReply && packet.channels === 1) {
      callbacks.microphone(new Uint8Array(packet.data), packet.sampleRate);
    }
  });
  function removeFile(item: File | undefined) {
    try { item?.delete(); } catch { /* A failed write may leave no file to delete. */ }
  }
  function releasePlayer() {
    clearTimeout(playbackTimeout);
    listener?.remove(); listener = undefined;
    if (player) {
      player.release();
      noteNativeAudioRelease();
      player = undefined;
    }
    removeFile(file); file = undefined;
  }
  function next() {
    releasePlayer();
    const clip = queue.shift();
    if (closed || !clip) {
      playing = false;
      if (!closed && receivingReply) return;
      callbacks.speaking(false);
      if (!closed) resumeMicrophone();
      return;
    }
    queuedBytes -= clip.bytes;
    playing = true;
    callbacks.speaking(true);
    const version = generation;
    const item = clip.file;
    void Promise.all([syncCapture(), clip.ready]).then(() => {
      if (closed || version !== generation) { removeFile(item); return; }
      file = item;
      player = createAudioPlayer(item.uri, { keepAudioSessionActive: true });
      player.shouldCorrectPitch = true;
      player.setPlaybackRate(playbackRate, 'high');
      listener = player.addListener('playbackStatusUpdate', status => {
        if (status.didJustFinish && version === generation) next();
      });
      playbackTimeout = setTimeout(() => {
        if (!closed && version === generation) next();
      }, Math.ceil(clip.bytes / BYTES_PER_SECOND / playbackRate * 1000) + 2300);
      player.play();
    }).catch(async () => {
      await clip.ready.catch(() => {});
      removeFile(item);
      if (!closed && version === generation) callbacks.error('Chưa phát được giọng nói. Mở lại phiên Live để thử lại.');
    });
  }
  function enqueue(size: number) {
    if (!size || closed) return;
    const pcm: Uint8Array[] = [];
    let remaining = size;
    while (remaining) {
      const next = buffer.shift()!;
      if (next.length > remaining) buffer.unshift(next.subarray(remaining));
      pcm.push(next.subarray(0, remaining));
      remaining -= Math.min(next.length, remaining);
    }
    bufferedBytes -= size;
    const chunk = wav(pcm, size, volume);
    const file = new File(Paths.cache, `sellerpilot-live-${createMessageId()}.wav`);
    // Prepare the next clip while the current one plays, so it can start without waiting for disk I/O.
    const ready = file.write(chunk);
    void ready.catch(() => {}); // A queued write may fail before playback reaches it.
    queuedBytes += size;
    queue.push({ file, ready, bytes: size });
    if (!playing) next();
  }
  function interrupt() {
    generation++;
    releasePlayer();
    for (const clip of queue.splice(0)) void clip.ready.finally(() => removeFile(clip.file)).catch(() => {});
    queuedBytes = 0;
    buffer = []; bufferedBytes = 0;
    replyLead = new ReplyLead();
    volume = new ReplyVolume();
    receivingReply = false;
    playing = false;
    callbacks.speaking(false);
    if (!closed) resumeMicrophone();
  }
  function syncCapture() {
    return runNativeAudioWork(async () => {
      if (closed || !configured) return;
      if ((muted || playing) && capturing) {
        stream.stop();
        noteNativeAudioRelease();
        capturing = false;
      }
      // Expo's PCM stream uses the record-only audio category on iOS.
      if (playing && !playbackMode) {
        await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
        playbackMode = true;
      } else if (!muted && !playing && !receivingReply && !capturing) {
        await waitForNativeAudioRelease();
        if (closed || muted || playing || receivingReply) return;
        await stream.start();
        capturing = true;
        playbackMode = false;
      }
    });
  }
  function resumeMicrophone() {
    void syncCapture().catch(() => {
      if (!closed) callbacks.error('Chưa mở lại được micro. Bạn mở lại phiên Live nhé.');
    });
  }
  return {
    async start(afterCue) {
      const [permission] = await Promise.all([requestRecordingPermissionsAsync(), afterCue]);
      if (closed) return;
      if (!permission.granted) throw new Error('Bạn cần cấp quyền micro trong Cài đặt để dùng Live.');
      configured = true;
      await syncCapture();
    },
    mute(value) {
      muted = value;
      resumeMicrophone();
    },
    play(pcm) {
      if (closed || !pcm.length) return;
      if (queuedBytes + bufferedBytes + pcm.length > BYTES_PER_SECOND * MAX_PLAYBACK_SECONDS) {
        callbacks.error('Âm thanh Live bị tồn đọng. Bạn mở lại phiên nhé.'); return;
      }
      buffer.push(pcm); bufferedBytes += pcm.length;
      const cut = replyLead?.observe(pcm, bufferedBytes) ?? 0;
      if (cut || bufferedBytes >= BUFFER_BYTES) {
        replyLead = undefined;
        receivingReply = true;
        enqueue(cut || bufferedBytes);
      }
    },
    flush() {
      const hadEarlyClip = receivingReply;
      receivingReply = false;
      replyLead = new ReplyLead();
      if (bufferedBytes) enqueue(bufferedBytes);
      else if (hadEarlyClip && !playing) {
        callbacks.speaking(false);
        resumeMicrophone();
      }
    },
    interrupt,
    close() {
      if (closed) return;
      closed = true;
      interrupt();
      mic.remove();
      void runNativeAudioWork(async () => {
        if (capturing) {
          stream.stop();
          noteNativeAudioRelease();
        }
        stream.release();
        if (configured) await setAudioModeAsync({ allowsRecording: false });
      }).catch(() => {});
    },
  };
}
