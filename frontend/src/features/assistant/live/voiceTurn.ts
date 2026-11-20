const START_MS = 65;
const SHORT_PAUSE_MS = 850;
const LONG_PAUSE_MS = 1120;

export const LIVE_WAVE_POINTS = 12;
export type MicFrame = { pcm: Uint8Array; rate: number };

/** Keep a bounded prefix while connecting or waiting for the next utterance. */
export class MicPrefix {
  private frames: MicFrame[] = [];
  private ms = 0;

  constructor(private readonly limitMs: number) {}

  add(frame: MicFrame) {
    const duration = frame.pcm.byteLength * 500 / frame.rate;
    if (duration > this.limitMs) return;
    this.frames.push(frame);
    this.ms += duration;
    while (this.ms > this.limitMs && this.frames.length > 1) {
      const first = this.frames.shift()!;
      this.ms -= first.pcm.byteLength * 500 / first.rate;
    }
  }

  drain() {
    const frames = this.frames;
    this.frames = [];
    this.ms = 0;
    return frames;
  }
}

/** Feed the light surface with signed peaks sampled across the current mic frame. */
export function readMicWave(pcm: Uint8Array, points: Float32Array) {
  const samples = new DataView(pcm.buffer, pcm.byteOffset, pcm.byteLength);
  const length = pcm.byteLength >> 1;
  for (let i = 0; i < points.length; i++) {
    const start = Math.floor(i * length / points.length);
    const end = Math.floor((i + 1) * length / points.length);
    let peak = 0;
    for (let index = start; index < end; index += 2) {
      const sample = samples.getInt16(index * 2, true) / 32768;
      if (Math.abs(sample) > Math.abs(peak)) peak = sample;
    }
    points[i] = Math.max(-1, Math.min(1, peak * 5));
  }
}

export function pcmLevel(pcm: Uint8Array) {
  const samples = new DataView(pcm.buffer, pcm.byteOffset, pcm.byteLength);
  let total = 0;
  let count = 0;
  for (let i = 0; i + 1 < pcm.length; i += 12) {
    const value = samples.getInt16(i, true) / 32768;
    total += value * value;
    count++;
  }
  return Math.sqrt(total / (count || 1));
}

/** Detect one local turn while retaining weak syllables and pauses inside it. */
export class VoiceTurn {
  private active = false;
  private floor = .0015;
  private onsetMs = 0;
  private speechMs = 0;
  private quietMs = 0;

  reset() {
    this.active = false;
    this.onsetMs = this.speechMs = this.quietMs = 0;
  }

  get hasSpeech() {
    return this.active;
  }

  audible(level: number) {
    const threshold = this.active ? this.floor * 1.45 + .001 : this.floor * 2.2 + .0015;
    return level >= Math.max(this.active ? .003 : .004, Math.min(.013, threshold));
  }

  finish() {
    if (!this.active) return false;
    this.reset();
    return true;
  }

  observe(level: number, durationMs: number) {
    const voice = this.audible(level);
    if (!this.active) {
      if (!voice) {
        this.floor += (Math.max(.0004, level) - this.floor) * .12;
        this.onsetMs = 0;
        return 'hold';
      }
      this.onsetMs += durationMs;
      if (this.onsetMs < START_MS) return 'hold';
      this.speechMs = this.onsetMs;
      this.active = true;
      return 'start';
    }
    if (voice) {
      this.speechMs += durationMs;
      this.quietMs = 0;
    } else {
      this.quietMs += durationMs;
      if (this.quietMs >= (this.speechMs >= 420 ? LONG_PAUSE_MS : SHORT_PAUSE_MS)) {
        this.finish();
        return 'end';
      }
    }
    return 'send';
  }
}
