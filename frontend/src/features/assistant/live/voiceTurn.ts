const START_MS = 60;
const SHORT_PAUSE_MS = 850;
const LONG_PAUSE_MS = 1120;

export const LIVE_WAVE_POINTS = 12;
export type MicFrame = { pcm: Uint8Array; rate: number; rms: number };

/** Reduce low-frequency rumble and raise quiet speech. Detect speech before applying gain. */
export class MicSignal {
  private previousInput = 0;
  private previousOutput = 0;
  private gain = 1;

  reset() {
    this.previousInput = this.previousOutput = 0;
    this.gain = 1;
  }

  process(raw: Uint8Array, rate: number): MicFrame {
    const source = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
    const pcm = new Uint8Array(raw.length);
    const output = new DataView(pcm.buffer);
    const coefficient = Math.exp(-2 * Math.PI * 78 / rate);
    let energy = 0;
    for (let offset = 0; offset + 1 < raw.length; offset += 2) {
      const input = source.getInt16(offset, true);
      const filtered = coefficient * (this.previousOutput + input - this.previousInput);
      this.previousInput = input;
      this.previousOutput = filtered;
      energy += filtered * filtered;
      output.setInt16(offset, Math.max(-32768, Math.min(32767, filtered)), true);
    }
    const rms = Math.sqrt(energy / Math.max(1, raw.length >> 1)) / 32768;
    const target = rms >= .004 ? Math.max(1, Math.min(3.2, .08 / rms)) : 1;
    const previousGain = this.gain;
    this.gain += (target - this.gain) * (target > this.gain ? .45 : .7);
    for (let offset = 0; offset + 1 < pcm.length; offset += 2) {
      const gain = previousGain + (this.gain - previousGain) * (offset + 2) / pcm.length;
      const sample = Math.max(-31456, Math.min(31456, output.getInt16(offset, true) * gain));
      output.setInt16(offset, Math.round(sample), true);
    }
    return { pcm, rate, rms };
  }
}

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
  constructor(private readonly longPauseMs = LONG_PAUSE_MS, private readonly shortPauseMs = SHORT_PAUSE_MS) {}

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
    return level >= this.threshold();
  }

  private threshold() {
    const level = this.active ? this.floor * 1.45 + .0008 : this.floor * 2 + .0012;
    return Math.max(this.active ? .0024 : .0033, Math.min(.013, level));
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
        this.onsetMs = Math.max(0, this.onsetMs - durationMs * .55);
        return 'hold';
      }
      this.onsetMs += durationMs;
      const onset = level >= this.threshold() * 2.2 ? 40 : START_MS;
      if (this.onsetMs < onset) return 'hold';
      this.speechMs = this.onsetMs;
      this.active = true;
      return 'start';
    }
    if (voice) {
      this.speechMs += durationMs;
      this.quietMs = 0;
    } else {
      this.quietMs += durationMs;
      if (this.quietMs >= (this.speechMs >= 420 ? this.longPauseMs : this.shortPauseMs)) {
        this.finish();
        return 'end';
      }
    }
    return 'send';
  }
}
