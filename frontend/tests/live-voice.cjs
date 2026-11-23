const assert = require('node:assert/strict');
const {readFileSync, statSync} = require('node:fs');
const {join} = require('node:path');
const {test} = require('node:test');
const ts = require('typescript');

function load(file, stubs = {}) {
  const directory = join(__dirname, '../src/features/assistant/live');
  const source = readFileSync(join(directory, file), 'utf8');
  const {outputText} = ts.transpileModule(source, {
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
  });
  const exports = {};
  new Function('exports', 'require', outputText)(exports, asset => {
    if (Object.hasOwn(stubs, asset)) return stubs[asset];
    const path = join(directory, asset);
    assert(statSync(path).size > 1000);
    return path;
  });
  return exports;
}
const voice = load('voiceTurn.ts');
const audioTypes = load('audioTypes.ts');
const {replyClipBytes, ReplyVolume, REPLY_SAMPLE_RATE} = audioTypes;
const {parseLivePreferences, liveErrorMessage} = load('locale.ts');
const {GreetingRotation, LIVE_GREETINGS} = load('greetings.ts');
const {upsertCaption} = load('timeline.ts');

test('partial, late and repeated captions never create another row for the same speaker and turn', () => {
  let items = upsertCaption([], { turnId: 'a', role: 'assistant', text: 'Shop có' });
  items = upsertCaption(items, { turnId: 'a', role: 'user', text: 'Hôm nay bao nhiêu đơn?' });
  items = upsertCaption(items, { turnId: 'a', role: 'assistant', text: 'Shop có ba đơn.' });
  const same = upsertCaption(items, { turnId: 'a', role: 'assistant', text: 'Shop có ba đơn.' });
  assert.equal(same, items);
  assert.deepEqual(items.map(item => item.role), ['user', 'assistant']);
  assert.equal(items[1].text, 'Shop có ba đơn.');
});

test('Live retains the latest startup audio in order and never exceeds the configured prefix', () => {
  const prefix = new voice.MicPrefix(120);
  for (const value of [1, 2, 3, 4]) {
    prefix.add({pcm: new Uint8Array(1280).fill(value), rate: 16000});
  }
  assert.deepEqual(prefix.drain().map(frame => frame.pcm[0]), [2, 3, 4]);
  assert.deepEqual(prefix.drain(), []);
});

test('Live restores language and voice independently and tolerates old or corrupt preferences', () => {
  assert.deepEqual(parseLivePreferences('{"language":"en","voice":"female"}'), {language: 'en', voice: 'female'});
  assert.deepEqual(parseLivePreferences('{"language":"en"}'), {language: 'en', voice: 'male'});
  assert.deepEqual(parseLivePreferences('{"language":"vi","voice":"male"}'), {language: 'vi', voice: 'male'});
  assert.deepEqual(parseLivePreferences(null), {language: 'vi', voice: 'female'});
  assert.deepEqual(parseLivePreferences('{'), {language: 'vi', voice: 'female'});
});

test('Live localizes known provider failures and preserves other server messages', () => {
  const message = 'Gemini Live đã hết tín dụng trả trước.';
  assert.equal(liveErrorMessage('vi', 'live_provider_billing', message), message);
  assert.match(liveErrorMessage('en', 'live_provider_billing', message), /out of prepaid credits/);
  assert.equal(liveErrorMessage('en', 'constructor', message), message);
  assert.equal(liveErrorMessage('en', undefined, message), message);
});

test('each language plays all five local greetings before reshuffling, without consecutive repeats', () => {
  const rotation = new GreetingRotation();
  for (const language of ['vi', 'en']) {
    let last;
    for (let cycle = 0; cycle < 4; cycle++) {
      const played = new Set();
      for (let turn = 0; turn < 5; turn++) {
        const voice = turn % 2 === 0 ? 'female' : 'male';
        const index = LIVE_GREETINGS[language][voice].indexOf(rotation.take({ language, voice }));
        assert(index >= 0);
        assert.notEqual(index, last);
        played.add(index);
        last = index;
      }
      assert.equal(played.size, 5);
    }
  }
});

test('quiet syllables and a mid-sentence pause are sent within one speech turn', () => {
  const turn = new voice.VoiceTurn();
  assert.equal(turn.observe(0, 1000), 'hold');
  assert.equal(turn.observe(.002, 40), 'hold');
  assert.equal(turn.observe(.007, 40), 'hold');
  assert.equal(turn.observe(.007, 40), 'start');
  assert.equal(turn.observe(.014, 440), 'send');
  assert.equal(turn.observe(0, 900), 'send');
  assert.equal(turn.observe(.005, 120), 'send');
  assert.equal(turn.observe(0, 1100), 'send');
  assert.equal(turn.observe(0, 40), 'end');
  assert.equal(turn.finish(), false);
  assert.equal(turn.observe(0, 500), 'hold');
  assert.equal(turn.observe(.06, 80), 'start');
  assert.equal(turn.observe(0, 840), 'send');
  assert.equal(turn.observe(0, 20), 'end');
  assert.equal(turn.observe(.02, 80), 'start');
  assert.equal(turn.finish(), true);
  assert.equal(turn.finish(), false);
});

test('Vietnamese speech retains a quiet onset before a stronger final word', () => {
  const detector = new voice.VoiceTurn(1050, 900);
  const prefix = new voice.MicPrefix(1400);
  const rate = 16000;
  const silent = new Uint8Array(1280);
  for (let frame = 0; frame < 35; frame++) prefix.add({pcm: silent, rate, rms: 0});
  for (let frame = 1; frame <= 15; frame++) {
    assert.equal(detector.observe(.0025, 40), 'hold');
    prefix.add({pcm: new Uint8Array(1280).fill(frame), rate, rms: .0025});
  }
  assert.equal(detector.observe(.019, 40), 'start');
  assert.deepEqual(prefix.drain().filter(frame => frame.pcm[0]).map(frame => frame.pcm[0]),
    Array.from({length: 15}, (_, index) => index + 1));
  assert.equal(detector.observe(0, 600), 'send');
  assert.equal(detector.observe(.005, 100), 'send');
});

test('Live estimates levels from little-endian PCM and handles empty frames', () => {
  const bytes = Buffer.alloc(24);
  bytes.writeInt16LE(8192, 0);
  bytes.writeInt16LE(-8192, 12);
  assert.equal(voice.pcmLevel(bytes), .25);
  assert.equal(voice.pcmLevel(new Uint8Array()), 0);
});

test('the microphone filter preserves quiet speech while reducing low rumble', () => {
  const rate = 16000;
  const microphone = new voice.MicSignal();
  const tone = (frequency, peak) => {
    const pcm = Buffer.alloc(rate / 25 * 2);
    for (let i = 0; i < pcm.length / 2; i++) {
      pcm.writeInt16LE(Math.round(Math.sin(2 * Math.PI * frequency * i / rate) * peak), i * 2);
    }
    return pcm;
  };
  const speech = tone(200, 420);
  const captured = microphone.process(speech, rate);
  assert(captured.rms > .007 && captured.rms < .011);
  assert(captured.rms < voice.pcmLevel(captured.pcm));
  microphone.reset();
  const rumble = tone(25, 420);
  const filtered = microphone.process(rumble, rate);
  assert(filtered.rms < voice.pcmLevel(rumble) * .4);
  assert.equal(new voice.VoiceTurn().observe(filtered.rms, 100), 'hold');
  microphone.reset();
  assert(microphone.process(Buffer.alloc(1280), rate).pcm.every(value => value === 0));
});

test('the Live light surface receives signed samples and goes flat on silence', () => {
  const points = new Float32Array(voice.LIVE_WAVE_POINTS);
  const pcm = Buffer.alloc(points.length * 4);
  pcm.writeInt16LE(6554, 0);
  pcm.writeInt16LE(-6554, 4);
  voice.readMicWave(pcm, points);
  assert.deepEqual(Array.from(points.slice(0, 3)), [1, -1, 0]);
  voice.readMicWave(new Uint8Array(0), points);
  assert(points.every(point => point === 0));
});

function replyPcm(ms, value = 0) {
  const pcm = Buffer.alloc(REPLY_SAMPLE_RATE * 2 * ms / 1000);
  for (let i = 0; i < pcm.length; i += 2) pcm.writeInt16LE(value, i);
  return pcm;
}

test('native Live prefers a quiet boundary near the end of each playable clip', () => {
  const pcm = Buffer.concat([replyPcm(360, 1500), replyPcm(30), replyPcm(50, 1700)]);
  assert.equal(replyClipBytes(pcm.subarray(0, -2), true), 0);
  assert.equal(replyClipBytes(pcm, true), replyPcm(385).length);
  assert.equal(replyClipBytes(pcm, false), 0);
});

test('native Live queues continuous speech before generation ends and restarts the mic after playback', async () => {
  const events = [];
  const tracks = [];
  const files = new Map();
  const status = new Map();
  const settle = () => new Promise(resolve => setImmediate(resolve));
  const {createLiveAudio} = load('audio.ts', {
    'expo-audio': {
      AudioModule: {AudioStream: class {
        addListener() { return {remove() {}}; }
        async start() { events.push('mic:on'); }
        stop() { events.push('mic:off'); }
        release() {}
      }},
      createAudioPlaylist({sources}) {
        tracks.push(...sources);
        return {
          add({uri}) { tracks.push(uri); },
          get trackCount() { return tracks.length; },
          addListener(name, handler) { status.set(name, handler); return {remove() { status.delete(name); }}; },
          play() { events.push('speaker:on'); },
          pause() {},
          release() { events.push('speaker:off'); },
        };
      },
      async requestRecordingPermissionsAsync() { return {granted: true}; },
      async setAudioModeAsync() {},
    },
    'expo-file-system': {Paths: {cache: ''}, File: class {
      constructor(_, uri) { this.uri = uri; }
      async write(data) { files.set(this.uri, data.length - 44); }
      delete() { files.delete(this.uri); }
    }},
    '../../../api/chatRequests': {createMessageId: () => String(files.size)},
    './audioTypes': audioTypes,
    './nativeAudioSession': {runNativeAudioWork: work => work(), noteNativeAudioRelease() {}, async waitForNativeAudioRelease() {}},
  });
  const audio = createLiveAudio({microphone() {}, speaking() {}, error: assert.fail});
  try {
    await audio.start();
    audio.play(replyPcm(460, 1450));
    await settle();
    assert.equal(tracks.length, 1);
    assert.deepEqual(events, ['mic:on', 'mic:off', 'speaker:on']);

    audio.play(replyPcm(1600, 1450));
    await settle();
    assert.equal(tracks.length, 3);
    audio.flush();
    await settle();
    assert.equal(tracks.length, 4);
    assert.equal([...files.values()].reduce((total, size) => total + size, 0), replyPcm(2060).length);
    status.get('trackChanged')({currentIndex: 1});
    assert.equal(files.size, 3);
    status.get('playlistStatusUpdate')({trackCount: 4, didJustFinish: true});
    await settle();
    assert.deepEqual(events, ['mic:on', 'mic:off', 'speaker:on', 'speaker:off', 'mic:on']);
    assert.equal(files.size, 0);
  } finally {
    audio.close();
  }
});

test('Live raises quiet speech while holding silence and keeping peaks below clipping', () => {
  const volume = new ReplyVolume();
  const samples = Array.from({length: REPLY_SAMPLE_RATE / 2}, (_, i) => volume.sample(i % 2 ? .055 : -.055));
  const settled = samples.slice(-240);
  assert(settled.every(sample => Math.abs(sample) > .25 && Math.abs(sample) < .29));
  assert(Math.abs(settled[0] + settled[1]) < .0001);
  assert.equal(volume.sample(0), 0);
  assert(Math.abs(volume.sample(1)) < .97);
});
