const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {test} = require('node:test');
const ts = require('typescript');

function load(file) {
  const source = readFileSync(join(__dirname, '../src/features/assistant/live', file), 'utf8');
  const {outputText} = ts.transpileModule(source, {
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
  });
  const exports = {};
  new Function('exports', outputText)(exports);
  return exports;
}
const voice = load('voiceTurn.ts');
const {ReplyLead, ReplyVolume, REPLY_SAMPLE_RATE} = load('audioTypes.ts');
const {parseLivePreferences} = load('locale.ts');
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
  assert.deepEqual(parseLivePreferences('{'), {language: 'vi', voice: 'male'});
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

test('Live estimates levels from little-endian PCM and handles empty frames', () => {
  const bytes = Buffer.alloc(24);
  bytes.writeInt16LE(8192, 0);
  bytes.writeInt16LE(-8192, 12);
  assert.equal(voice.pcmLevel(bytes), .25);
  assert.equal(voice.pcmLevel(new Uint8Array()), 0);
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

test('native Live splits at a quiet join spanning packets only after buffering the next phrase', () => {
  const lead = new ReplyLead();
  let bytes = 0;
  const append = pcm => lead.observe(pcm, bytes += pcm.length);
  assert.equal(append(replyPcm(900, 1500)), 0);
  assert.equal(append(replyPcm(100)), 0);
  assert.equal(append(replyPcm(100)), 0);
  assert.equal(append(replyPcm(300, 1700)), replyPcm(970).length);
});

test('native Live leaves an uninterrupted phrase or all-silent audio in one clip', () => {
  for (const sample of [0, 1450]) {
    const lead = new ReplyLead();
    const pcm = replyPcm(3000, sample);
    assert.equal(lead.observe(pcm, pcm.length), 0);
  }
});

test('Live raises quiet speech while holding silence and keeping peaks below clipping', () => {
  const volume = new ReplyVolume();
  const samples = Array.from({length: REPLY_SAMPLE_RATE / 2}, (_, i) => volume.sample(i % 2 ? .055 : -.055));
  const settled = samples.slice(-240);
  assert(settled.every(sample => Math.abs(sample) > .16 && Math.abs(sample) < .205));
  assert(Math.abs(settled[0] + settled[1]) < .0001);
  assert.equal(volume.sample(0), 0);
  assert(Math.abs(volume.sample(1)) < .97);
});
