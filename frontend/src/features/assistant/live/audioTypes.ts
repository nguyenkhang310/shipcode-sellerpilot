export const REPLY_SAMPLE_RATE = 24_000;
export const MAX_PLAYBACK_SECONDS = 45;
export const NATIVE_REPLY_RATE = 1.08;
export const WEB_REPLY_RATE = 1.05;
const MIN_VOICE_GAIN = 2.15;
const MAX_VOICE_GAIN = 3.65;
const TARGET_VOICE_RMS = .20;
const GAIN_WINDOW = REPLY_SAMPLE_RATE / 50;

const PAUSE_BLOCK = REPLY_SAMPLE_RATE / 50;
const QUIET_BLOCKS = 9;
const MIN_LEAD_SAMPLES = REPLY_SAMPLE_RATE * 1.2;
const LEAD_AHEAD_BYTES = REPLY_SAMPLE_RATE * 2 * .48;

/** Find one quiet join for starting native playback before a long reply finishes. */
export class ReplyLead {
  private samples = 0;
  private energy = 0;
  private quiet = 0;
  private hasSpeech = false;
  private cut = 0;

  observe(pcm: Uint8Array, bufferedBytes: number) {
    if (!this.cut && this.samples < REPLY_SAMPLE_RATE * 5) {
      const samples = new DataView(pcm.buffer, pcm.byteOffset, pcm.byteLength);
      for (let offset = 0; offset + 1 < pcm.length; offset += 2) {
        const sample = samples.getInt16(offset, true) / 32768;
        this.energy += sample * sample;
        this.samples++;
        if (this.samples % PAUSE_BLOCK) continue;
        const quiet = this.energy / PAUSE_BLOCK <= .008 ** 2;
        this.energy = 0;
        if (quiet) this.quiet++;
        else { this.quiet = 0; this.hasSpeech = true; }
        if (this.hasSpeech && this.samples >= MIN_LEAD_SAMPLES && this.quiet >= QUIET_BLOCKS) {
          this.cut = 2 * this.samples - PAUSE_BLOCK * QUIET_BLOCKS;
          break;
        }
      }
    }
    return this.cut && bufferedBytes - this.cut >= LEAD_AHEAD_BYTES ? this.cut : 0;
  }
}

/** Normalize gradually across PCM packets and limit peaks before output. */
export class ReplyVolume {
  private gain = 2.75;
  private target = this.gain;
  private energy = 0;
  private count = 0;

  sample(sample: number) {
    this.energy += sample * sample;
    if (++this.count === GAIN_WINDOW) {
      const rms = Math.sqrt(this.energy / this.count);
      // Keep the last gain through quiet parts, including breaths and pauses.
      if (rms > .025) this.target = Math.min(MAX_VOICE_GAIN, Math.max(MIN_VOICE_GAIN, TARGET_VOICE_RMS / rms));
      this.energy = this.count = 0;
    }
    this.gain += (this.target - this.gain) * (this.target < this.gain ? .003 : .0006);
    const amplified = sample * this.gain;
    const peak = Math.abs(amplified);
    return peak <= .70 ? amplified : Math.sign(amplified) * (.70 + .27 * (1 - Math.exp(-((peak - .70) / .27))));
  }
}

export type AudioCallbacks = {
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
