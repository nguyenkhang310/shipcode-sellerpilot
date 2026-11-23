import { AudioModule, createAudioPlaylist, requestRecordingPermissionsAsync, setAudioModeAsync } from 'expo-audio';
import { File, Paths } from 'expo-file-system';
import { createMessageId } from '../../../api/chatRequests';
import { MAX_PLAYBACK_SECONDS, NATIVE_REPLY_RATE, REPLY_SAMPLE_RATE, replyClipBytes, ReplyVolume, type AudioCallbacks, type LiveAudio } from './audioTypes';
import { noteNativeAudioRelease, runNativeAudioWork, waitForNativeAudioRelease } from './nativeAudioSession';

const BYTES_PER_SECOND = REPLY_SAMPLE_RATE * 2;
type Clip = { file: File; ready: Promise<void>; bytes: number };

function wav(pcm: Uint8Array, volume: ReplyVolume) {
  const size = pcm.length;
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
  const samples = new DataView(pcm.buffer, pcm.byteOffset, size);
  for (let offset = 0; offset < size; offset += 2) {
    header.setInt16(44 + offset, Math.round(volume.sample(samples.getInt16(offset, true) / 32768) * 32767), true);
  }
  return result;
}

export function createLiveAudio(callbacks: AudioCallbacks): LiveAudio {
  const Stream = AudioModule.AudioStream;
  if (!Stream) throw new Error('Bản app này chưa hỗ trợ micro Live. Cập nhật Expo Go hỗ trợ SDK 58 hoặc mở app bằng web.');
  const stream = new Stream({ sampleRate: 16_000, channels: 1, encoding: 'int16' });
  const playbackRate = callbacks.vietnamese ? 1.02 : NATIVE_REPLY_RATE;
  let player: ReturnType<typeof createAudioPlaylist> | undefined;
  let listeners: { remove: () => void }[] = [];
  const playingClips: Clip[] = [];
  let playbackTimeout: ReturnType<typeof setTimeout> | undefined;
  let expectedEnd = 0, releasedTracks = 0;
  let closed = false, muted = false, playing = false, capturing = false, configured = false;
  let playbackMode = false;
  let generation = 0, queuedBytes = 0;
  let pumping = false, firstClip = true;
  let volume = new ReplyVolume();
  let receivingReply = false;
  let buffer: Uint8Array<ArrayBufferLike> = new Uint8Array();
  const queue: Clip[] = [];
  const mic = stream.addListener('audioStreamBuffer', packet => {
    // Keep playback out of the mic on devices without acoustic echo cancellation.
    if (!closed && !muted && !playing && !receivingReply && packet.channels === 1) {
      const pcm = new Uint8Array(packet.data);
      const frameBytes = Math.round(packet.sampleRate * .02) * 2;
      for (let offset = 0; frameBytes > 0 && offset + 1 < pcm.length; offset += frameBytes) {
        if (closed || muted || playing) break;
        callbacks.microphone(pcm.subarray(offset, Math.min(offset + frameBytes, pcm.length & ~1)), packet.sampleRate);
      }
    }
  });
  function removeFile(item: File | undefined) {
    try { item?.delete(); } catch { /* A failed write may leave no file to delete. */ }
  }
  function releasePlayer() {
    clearTimeout(playbackTimeout);
    for (const listener of listeners) listener.remove();
    listeners = [];
    if (player) {
      player.pause();
      player.release();
      noteNativeAudioRelease();
      player = undefined;
    }
    releasePlayedClips(playingClips.length);
    playingClips.length = 0;
    releasedTracks = expectedEnd = 0;
  }
  function releasePlayedClips(through: number) {
    while (releasedTracks < Math.min(through, playingClips.length)) {
      const clip = playingClips[releasedTracks++]!;
      queuedBytes -= clip.bytes;
      removeFile(clip.file);
    }
  }
  function settlePlayback() {
    if (closed || !playing || player || queue.length || pumping || receivingReply) return;
    playing = false;
    callbacks.speaking(false);
    resumeMicrophone();
  }
  function pump() {
    if (closed || pumping || !queue.length) return;
    pumping = true;
    const version = generation;
    if (!playing) {
      playing = true;
      callbacks.speaking(true);
    }
    void (async () => {
      await syncCapture();
      while (!closed && version === generation && queue.length) {
        const clip = queue[0]!;
        await clip.ready;
        if (closed || version !== generation) return;
        queue.shift();
        playingClips.push(clip);
        if (player) {
          player.add({ uri: clip.file.uri });
        } else {
          const playlist = player = createAudioPlaylist({ sources: [clip.file.uri], updateInterval: 50 });
          playlist.volume = 1;
          playlist.playbackRate = playbackRate;
          listeners = [
            playlist.addListener('trackChanged', ({ currentIndex }) => {
              if (player === playlist) releasePlayedClips(currentIndex);
            }),
            playlist.addListener('playlistStatusUpdate', status => {
              if (player !== playlist || !status.didJustFinish) return;
              if (status.trackCount < playlist.trackCount) {
                if (playlist.currentIndex < status.trackCount || !playlist.playing) {
                  playlist.skipTo(status.trackCount);
                  playlist.play();
                }
                return;
              }
              releasePlayer();
              settlePlayback();
            }),
          ];
          playlist.play();
        }
        expectedEnd = Math.max(expectedEnd, Date.now()) + clip.bytes / BYTES_PER_SECOND / playbackRate * 1000;
        clearTimeout(playbackTimeout);
        playbackTimeout = setTimeout(() => {
          if (!closed && version === generation) callbacks.error('Âm thanh Live bị gián đoạn. Bạn mở lại phiên nhé.');
        }, expectedEnd - Date.now() + 2500);
      }
    })().catch(() => {
      if (!closed && version === generation) callbacks.error('Chưa phát được giọng nói. Mở lại phiên Live để thử lại.');
    }).finally(() => {
      if (version !== generation) return;
      pumping = false;
      settlePlayback();
    });
  }
  function enqueue(size: number) {
    const chunk = wav(buffer.subarray(0, size), volume);
    buffer = buffer.subarray(size);
    const file = new File(Paths.cache, `sellerpilot-live-${createMessageId()}.wav`);
    // Prepare the next clip while the current one plays, so it can start without waiting for disk I/O.
    const ready = file.write(chunk);
    void ready.catch(() => {}); // A queued write may fail before playback reaches it.
    queuedBytes += size;
    queue.push({ file, ready, bytes: size });
    pump();
  }
  function interrupt() {
    generation++;
    releasePlayer();
    for (const clip of queue.splice(0)) void clip.ready.finally(() => removeFile(clip.file)).catch(() => {});
    queuedBytes = 0;
    buffer = new Uint8Array();
    firstClip = true;
    pumping = false;
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
        await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true, shouldRouteThroughEarpiece: false });
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
      await afterCue;
      if (closed) return;
      const permission = await requestRecordingPermissionsAsync();
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
      if (queuedBytes + buffer.length + pcm.length > BYTES_PER_SECOND * MAX_PLAYBACK_SECONDS) {
        callbacks.error('Âm thanh Live bị tồn đọng. Bạn mở lại phiên nhé.'); return;
      }
      const combined = new Uint8Array(buffer.length + pcm.length);
      combined.set(buffer);
      combined.set(pcm, buffer.length);
      buffer = combined;
      for (let cut = replyClipBytes(buffer, firstClip); cut; cut = replyClipBytes(buffer, firstClip)) {
        firstClip = false;
        receivingReply = true;
        enqueue(cut);
      }
    },
    flush() {
      receivingReply = false;
      firstClip = true;
      if (buffer.length) enqueue(buffer.length);
      settlePlayback();
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
