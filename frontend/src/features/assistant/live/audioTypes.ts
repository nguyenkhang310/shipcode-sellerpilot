export const REPLY_SAMPLE_RATE = 24_000;
export const MAX_PLAYBACK_SECONDS = 45;
export const NATIVE_REPLY_RATE = 1.08;
export const WEB_REPLY_RATE = 1.05;
const MAX_VOICE_GAIN = 5.25;
const TARGET_VOICE_RMS = .27;
const GAIN_WINDOW = REPLY_SAMPLE_RATE / 50;

/** Start playback quickly and prefer a quiet boundary in each subsequent clip. */
export function replyClipBytes(pcm: Uint8Array, first: boolean) {
  const bytesPerMs = REPLY_SAMPLE_RATE * 2 / 1000;
  const end = (first ? 440 : 760) * bytesPerMs;
  if (pcm.length < end) return 0;
  const samples = new DataView(pcm.buffer, pcm.byteOffset, pcm.byteLength);
  const window = 10 * bytesPerMs;
  for (let offset = end; offset > end - 110 * bytesPerMs; offset -= window) {
    let energy = 0;
    for (let i = offset - window; i < offset; i += 2) {
      const value = samples.getInt16(i, true);
      energy += value * value;
    }
    if (energy / (window / 2) < (32768 * .008) ** 2) return offset - window / 2;
  }
  let cut = end;
  let smallest = Infinity;
  for (let offset = end - 5 * bytesPerMs; offset < end; offset += 2) {
    const peak = Math.abs(samples.getInt16(offset - 2, true)) + Math.abs(samples.getInt16(offset, true));
    if (peak < smallest) { smallest = peak; cut = offset; }
  }
  return cut;
}

/** Normalize gradually across PCM packets and limit peaks before output. */
export class ReplyVolume {
  private gain = 3.3;
  private target = this.gain;
  private energy = 0;
  private count = 0;

  sample(sample: number) {
    this.energy += sample * sample;
    if (++this.count === GAIN_WINDOW) {
      const rms = Math.sqrt(this.energy / this.count);
      // Keep the last gain through quiet parts, including breaths and pauses.
      if (rms > .015) this.target = Math.min(MAX_VOICE_GAIN, Math.max(1, TARGET_VOICE_RMS / rms));
      this.energy = this.count = 0;
    }
    this.gain += (this.target - this.gain) * (this.target < this.gain ? .003 : .0006);
    const amplified = sample * this.gain;
    const peak = Math.abs(amplified);
    return peak <= .70 ? amplified : Math.sign(amplified) * (.70 + .27 * (1 - Math.exp(-((peak - .70) / .27))));
  }
}

export type AudioCallbacks = {
  vietnamese?: boolean;
  microphone: (pcm: Uint8Array, rate: number) => void;
  speaking: (playing: boolean) => void;
  error: (message: string) => void;
};

export type LiveAudio = {
  start: (afterCue?: Promise<void>) => Promise<void>;
  mute: (muted: boolean) => void;
  play: (pcm: Uint8Array) => void;
  flush: () => void;
  interrupt: () => void;
  close: () => void;
};
