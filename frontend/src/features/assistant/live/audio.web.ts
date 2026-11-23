import { MAX_PLAYBACK_SECONDS, REPLY_SAMPLE_RATE, WEB_REPLY_RATE, ReplyVolume, type AudioCallbacks, type LiveAudio } from './audioTypes';

const FIRST_PLAY_BUFFER = .065;
const RECOVERY_BUFFER = .15;

// Integrate neighbouring input samples and emit 40 ms of mono PCM at 16 kHz.
const processorSource = `
class SellerPilotMic extends AudioWorkletProcessor {
  constructor() {
    super();
    this.phase = 0;
    this.total = 0;
    this.count = 0;
    this.offset = 0;
    this.frame = new ArrayBuffer(1280);
    this.view = new DataView(this.frame);
  }
  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input) return true;
    for (const sample of input) {
      this.total += sample;
      this.count++;
      this.phase += 16000;
      if (this.phase < sampleRate) continue;
      this.phase -= sampleRate;
      const value = Math.max(-1, Math.min(1, this.total / this.count));
      this.view.setInt16(this.offset, value * (value < 0 ? 32768 : 32767), true);
      this.total = 0;
      this.count = 0;
      this.offset += 2;
      if (this.offset === this.frame.byteLength) {
        this.port.postMessage(this.frame, [this.frame]);
        this.frame = new ArrayBuffer(1280);
        this.view = new DataView(this.frame);
        this.offset = 0;
      }
    }
    return true;
  }
}
registerProcessor('sellerpilot-mic', SellerPilotMic);`;

export function createLiveAudio(callbacks: AudioCallbacks): LiveAudio {
  if (!globalThis.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    throw new Error('Để dùng micro trên web, mở SellerPilot bằng localhost hoặc HTTPS.');
  }
  const context = new AudioContext();
  const playbackRate = callbacks.vietnamese ? 1.01 : WEB_REPLY_RATE;
  let stream: MediaStream | undefined;
  let input: MediaStreamAudioSourceNode | undefined;
  let worklet: AudioWorkletNode | undefined;
  let closed = false, muted = false, playAt = 0;
  let replyFinished = false;
  let volume = new ReplyVolume();
  const sources = new Set<AudioBufferSourceNode>();
  function interrupt() {
    for (const node of sources) { node.onended = null; node.stop(); node.disconnect(); }
    sources.clear(); playAt = 0;
    replyFinished = false;
    volume = new ReplyVolume();
    callbacks.speaking(false);
  }
  return {
    async start() {
      const script = URL.createObjectURL(new Blob([processorSource], { type: 'text/javascript' }));
      const constraints = {
        channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true,
        latency: .02,
      };
      const capture = navigator.mediaDevices.getUserMedia({ audio: constraints }).then(captured => {
        if (closed) captured.getTracks().forEach(track => track.stop());
        else {
          stream = captured;
          captured.getAudioTracks().forEach(track => { track.enabled = !muted; });
        }
        return captured;
      }, () => { throw new Error('Chưa mở được micro. Cho phép truy cập micro trong trình duyệt rồi thử lại.'); });
      const module = context.audioWorklet.addModule(script).finally(() => URL.revokeObjectURL(script));
      const [, captured] = await Promise.all([context.resume(), capture, module]);
      if (closed) return;
      input = context.createMediaStreamSource(captured);
      worklet = new AudioWorkletNode(context, 'sellerpilot-mic', { outputChannelCount: [1] });
      worklet.port.onmessage = event => {
        if (!closed && !muted) callbacks.microphone(new Uint8Array(event.data as ArrayBuffer), 16_000);
      };
      input.connect(worklet);
      // The worklet emits PCM over its port and leaves its speaker output at zero.
      // Connecting the silent output keeps the graph active even between spoken replies.
      worklet.connect(context.destination);
    },
    mute(value) {
      muted = value;
      stream?.getAudioTracks().forEach(track => { track.enabled = !value; });
    },
    play(pcm) {
      if (closed || !pcm.length) return;
      if (playAt - context.currentTime > MAX_PLAYBACK_SECONDS) {
        callbacks.error('Âm thanh Live bị tồn đọng. Bạn mở lại phiên nhé.'); return;
      }
      const samples = new DataView(pcm.buffer, pcm.byteOffset, pcm.byteLength);
      const buffer = context.createBuffer(1, pcm.length / 2, REPLY_SAMPLE_RATE);
      const channel = buffer.getChannelData(0);
      for (let i = 0; i < channel.length; i++) channel[i] = volume.sample(samples.getInt16(i * 2, true) / 32768);
      const node = context.createBufferSource();
      node.buffer = buffer;
      node.playbackRate.value = playbackRate;
      node.connect(context.destination);
      sources.add(node);
      node.onended = () => {
        node.disconnect();
        sources.delete(node);
        if (!sources.size) {
          if (replyFinished) playAt = 0;
          callbacks.speaking(false);
        }
      };
      replyFinished = false;
      const now = context.currentTime;
      const start = playAt > now ? playAt : now + (playAt ? RECOVERY_BUFFER : FIRST_PLAY_BUFFER);
      node.start(start);
      playAt = start + buffer.duration / playbackRate;
      callbacks.speaking(true);
    },
    flush() {
      replyFinished = true;
      if (!sources.size) playAt = 0;
    },
    interrupt,
    close() {
      if (closed) return;
      closed = true;
      interrupt();
      if (worklet) { worklet.port.onmessage = null; worklet.port.close(); worklet.disconnect(); }
      input?.disconnect();
      stream?.getTracks().forEach(track => track.stop());
      void context.close().catch(() => {});
    },
  };
}
