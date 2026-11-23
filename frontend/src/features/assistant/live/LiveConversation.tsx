import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { Animated, AppState, BackHandler, Easing, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { createAudioPlayer, setAudioModeAsync } from 'expo-audio';
import { Asset } from 'expo-asset';
import * as Haptics from 'expo-haptics';
import { fromByteArray, toByteArray } from 'base64-js';
import { ApiError, openSellerLiveSocket } from '../../../api/client';
import { SystemIcon } from '../../../components/ui/SystemIcon';
import { useTheme } from '../../../theme/ThemeProvider';
import type { ChatData, ConversationDetail, ProductDraft } from '../../../api/types';
import { uploadProductImages } from '../../../api/sellerPilot';
import { createMessageId } from '../../../api/chatRequests';
import { money } from '../../dashboard/formatters';
import { pickProductImages, type PendingImage } from '../productImages';
import { createLiveAudio } from './audio';
import type { LiveAudio } from './audioTypes';
import { LiveOrb } from './LiveOrb';
import { noteNativeAudioRelease, runNativeAudioWork, waitForNativeAudioRelease } from './nativeAudioSession';
import { LIVE_WAVE_POINTS, MicPrefix, pcmLevel, readMicWave, VoiceTurn, type MicFrame } from './voiceTurn';
import { LIVE_TEXT, type LiveLanguage, type LivePreferences } from './locale';
import { liveMessageKey, upsertCaption, type LiveCaption } from './timeline';

export type { LiveCaption } from './timeline';
export type LiveShopResult = {
  id?: string;
  language?: LiveLanguage;
  question: string;
  answer: string;
  report: ChatData['report'];
  order_id: number | null;
  turn_id?: string;
  spoken_summary?: string;
  sales_context?: { sales_metric?: string; compare_yesterday?: boolean };
};
type LiveEvent =
  | { type: 'ready'; turn_protocol?: number; greeting_count?: number }
  | { type: 'audio_received' | 'interrupted' | 'audio_end' | 'finished' | 'reconnecting' }
  | { type: 'turn_end'; clear_captions?: boolean; turn_id?: string }
  | { type: 'audio'; data: string; review?: boolean }
  | { type: 'transcript'; role: LiveCaption['role']; text: string; final?: boolean; snapshot?: boolean; unclear?: boolean; turn_id?: string }
  | { type: 'turn_saved'; turn: ConversationDetail['turns'][number] }
  | { type: 'draft'; draft: ProductDraft | null }
  | { type: 'archive_review'; name: string }
  | { type: 'action_done'; changed: boolean; message: string; draft: ProductDraft | null }
  | { type: 'shop_result' } & LiveShopResult
  | { type: 'error' | 'ended' | 'image_rejected'; message: string };

type Session = {
  conversationId: string;
  voice: VoiceTurn;
  preRoll: MicPrefix;
  startup: MicPrefix;
  captured: boolean;
  language: LiveLanguage;
  audio?: LiveAudio;
  socket?: WebSocket;
  watchdog?: ReturnType<typeof setTimeout>;
  reconnectTimer?: ReturnType<typeof setTimeout>;
  stopCue?: () => void;
  finish?: (acknowledged?: boolean) => void;
  finishTimeout?: ReturnType<typeof setTimeout>;
  inputTimeout?: ReturnType<typeof setTimeout>;
  pendingHistory: boolean;
  captureStarted: boolean;
  ready: boolean;
  manualTurns: boolean;
  waiting: boolean;
  playing: boolean;
  fallbackTurn: string;
  captions: Map<string, LiveCaption>;
  closedTurns: Set<string>;
  visibleUserTurns: Set<string>;
  captionTimer?: ReturnType<typeof setTimeout>;
  muted: boolean;
  picking: boolean;
  skipOutput: boolean;
  outputOpen: boolean;
  readingReview?: boolean;
  gallery?: { images: PendingImage[]; requestId: string };
};
type Props = {
  visible: boolean;
  conversationId: string | null;
  progress: Animated.Value;
  preferences: LivePreferences;
  onCaptions: Dispatch<SetStateAction<LiveCaption[]>>;
  onResult: (result: LiveShopResult | null) => void;
  onSaved: (turn: ConversationDetail['turns'][number]) => void;
  onOpen: () => void;
  onExit: (orderId?: number) => void;
  onDrain: (draining: boolean, recoverId?: string) => void;
  onShopChanged?: () => void;
  reduceMotion: boolean;
};
export type LiveConversationHandle = { start: () => void; openOrder: (id: number) => void };

const USE_NATIVE_DRIVER = Platform.OS !== 'web';
const ENTER_CUE = require('../../../../assets/sellerpilot-live-enter.wav');
const EXIT_CUE = require('../../../../assets/sellerpilot-live-exit.wav');

function sendPcm(socket: WebSocket, pcm: Uint8Array, rate: number) {
  const size = Math.floor(rate / 2) * 2;
  for (let offset = 0; offset < pcm.length; offset += size) {
    socket.send(JSON.stringify({ type: 'audio', rate, data: fromByteArray(pcm.subarray(offset, offset + size)) }));
  }
}

function playCue(source: number | string, afterNativeRelease = false) {
  let stop = () => {};
  const done = new Promise<void>(resolve => {
    let player: ReturnType<typeof createAudioPlayer> | undefined;
    let media: HTMLAudioElement | undefined;
    let subscription: { remove: () => void } | undefined;
    let active = true;
    const finish = () => {
      if (!active) return;
      active = false;
      clearTimeout(timer);
      subscription?.remove();
      if (media && !media.ended) media.pause();
      try {
        if (player) {
          player.release();
          noteNativeAudioRelease();
        }
      } catch { /* The chime is optional when audio is unavailable. */ }
      resolve();
    };
    const timer = setTimeout(finish, 700);
    stop = finish;
    async function play() {
      try {
        if (Platform.OS === 'web') {
          media = new Audio(typeof source === 'string' ? source : Asset.fromModule(source).uri);
          media.onended = finish;
          media.onerror = finish;
          await media.play();
          return;
        }
        await runNativeAudioWork(async () => {
          if (afterNativeRelease) await waitForNativeAudioRelease();
          if (active) await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
        });
        if (!active) return;
        player = createAudioPlayer(source, { keepAudioSessionActive: true, updateInterval: 40 });
        subscription = player.addListener('playbackStatusUpdate', state => {
          if (state.didJustFinish || state.duration > 0 && state.currentTime >= state.duration - .02) finish();
        });
        player.play();
      } catch { finish(); }
    }
    void play();
  });
  return { done, stop };
}

export const LiveConversation = forwardRef<LiveConversationHandle, Props>(function LiveConversation({
  visible, conversationId, progress, preferences, onCaptions, onResult, onSaved, onOpen, onExit, onDrain, onShopChanged, reduceMotion,
}, ref) {
  const { IOS, BRAND, ui, isDark } = useTheme();
  const current = useRef<Session | null>(null);
  const interruptedHistory = useRef<string | undefined>(undefined);
  const closing = useRef(false);
  const transitioning = useRef(false);
  const level = useRef(0);
  const lastLevelAt = useRef(0);
  const microphone = useRef(new Float32Array(LIVE_WAVE_POINTS));
  const lastVoiceAt = useRef(0);
  const voiceActive = useRef(false);
  const cues = useRef<{ enter: number | string; exit: number | string }>({ enter: ENTER_CUE, exit: EXIT_CUE });
  const exitCue = useRef<ReturnType<typeof playCue> | null>(null);
  const nextGreeting = useRef<Partial<Record<LiveLanguage, number>>>({});
  const [phase, setPhase] = useState<'idle' | 'connecting' | 'reconnecting' | 'live'>('idle');
  const [muted, setMuted] = useState(false);
  const [inputReady, setInputReady] = useState(false);
  const [captureReady, setCaptureReady] = useState(false);
  const [userSpeaking, setUserSpeaking] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [listing, setListing] = useState<ProductDraft | null>(null);
  const [archiveReview, setArchiveReview] = useState('');
  const [notice, setNotice] = useState('');
  const [uploading, setUploading] = useState(false);
  const [galleryFailed, setGalleryFailed] = useState(false);
  const [picking, setPicking] = useState(false);

  function disconnect() {
    const session = current.current;
    if (!session) return;
    current.current = null;
    if (session.pendingHistory) interruptedHistory.current = session.conversationId;
    clearTimeout(session.watchdog);
    clearTimeout(session.reconnectTimer);
    clearTimeout(session.finishTimeout);
    clearTimeout(session.inputTimeout);
    clearTimeout(session.captionTimer);
    session.stopCue?.();
    session.audio?.close();
    session.socket?.close();
    level.current = 0;
    microphone.current.fill(0);
    lastVoiceAt.current = 0;
    voiceActive.current = false;
  }

  useEffect(() => {
    // A native Metro asset can take longer to load than the chime itself.
    for (const kind of ['enter', 'exit'] as const) {
      const asset = Asset.fromModule(kind === 'enter' ? ENTER_CUE : EXIT_CUE);
      void asset.downloadAsync().then(() => { if (asset.localUri) cues.current[kind] = asset.localUri; }).catch(() => {});
    }
  }, []);

  useEffect(() => {
    const subscription = AppState.addEventListener('change', state => {
      const session = current.current;
      if (!session || session.picking) return;
      if (state === 'active') {
        if (session.captureStarted) session.audio?.mute(session.muted);
        return;
      }
      // System overlays and the audio session may briefly make iOS inactive.
      if (state === 'background') {
        if (session.finish) { session.finish(); return; }
        disconnect();
        setSpeaking(false); setPhase('idle'); setUploading(false); setPicking(false);
        setNotice('Phiên đã dừng khi bạn rời màn hình.');
      }
    });
    return () => { subscription.remove(); disconnect(); exitCue.current?.stop(); progress.stopAnimation(); };
  }, [progress]);

  useEffect(() => {
    if (!visible) {
      if (!current.current?.finish) {
        disconnect();
        closing.current = false;
      }
      progress.stopAnimation();
      progress.setValue(0);
      return;
    }
    const motion = Animated.timing(progress, {
      toValue: 1, duration: reduceMotion ? 0 : 400,
      easing: Easing.bezier(.2, .72, .23, 1), useNativeDriver: USE_NATIVE_DRIVER,
    });
    motion.start();
    return () => motion.stop();
  }, [visible, reduceMotion, progress]);

  useEffect(() => {
    if (!visible || Platform.OS === 'web') return;
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => { close(); return true; });
    return () => subscription.remove();
  });

  function meter(rms: number, boost: number) {
    const now = Date.now();
    if (now - lastLevelAt.current < 57) return;
    lastLevelAt.current = now;
    level.current = Math.min(1, rms * boost);
  }

  function meterMicrophone(pcm: Uint8Array, rms: number, audible: boolean) {
    const now = Date.now();
    if (audible) {
      lastVoiceAt.current = now;
      if (!reduceMotion) readMicWave(pcm, microphone.current);
    } else {
      microphone.current.fill(0);
    }
    meter(rms, 7);
    const active = now - lastVoiceAt.current < 290;
    if (active !== voiceActive.current) {
      voiceActive.current = active;
      setUserSpeaking(active);
      if (active) setProcessing(false);
    }
  }

  function fail(message: string) {
    disconnect();
    setSpeaking(false); setPhase('idle'); setNotice(message); setPicking(false); setUploading(false);
  }

  function sendTurn(session: Session, socket: WebSocket) {
    socket.send('{"type":"turn"}');
    session.waiting = session.manualTurns;
    setProcessing(true);
  }

  function flushCaptions(session: Session, completeTurn = false) {
    clearTimeout(session.captionTimer);
    session.captionTimer = undefined;
    if (current.current !== session || !session.captions.size) return;
    const captions = [...session.captions.values()].filter(caption => caption.role === 'assistant' || caption.final || completeTurn);
    if (!captions.length) return;
    for (const caption of captions) {
      session.captions.delete(liveMessageKey(caption.turnId, caption.role));
      if (caption.role === 'user') session.visibleUserTurns.add(caption.turnId);
    }
    onCaptions(items => captions.reduce(upsertCaption, items));
  }

  function discardCaptions(session: Session, id: string | undefined, remove = true) {
    if (!id) return;
    session.closedTurns.add(id);
    session.captions.delete(liveMessageKey(id, 'user'));
    session.captions.delete(liveMessageKey(id, 'assistant'));
    session.visibleUserTurns.delete(id);
    if (remove) onCaptions(items => items.filter(item => item.turnId !== id));
  }

  async function start() {
    if (current.current || closing.current) return;
    const session: Session = { conversationId: conversationId ?? interruptedHistory.current ?? createMessageId(),
      voice: preferences.language === 'vi' ? new VoiceTurn(1370, 970) : new VoiceTurn(),
      preRoll: new MicPrefix(420), startup: new MicPrefix(8000), captured: false, language: preferences.language,
      ready: false, captureStarted: false, pendingHistory: false, muted: false, picking: false,
      skipOutput: false, outputOpen: false, manualTurns: false, waiting: false, playing: false, fallbackTurn: createMessageId(),
      captions: new Map(), closedTurns: new Set(), visibleUserTurns: new Set() };
    current.current = session;
    setMuted(false); setInputReady(false); setCaptureReady(false); setSpeaking(false); setUserSpeaking(false); setProcessing(false);
    setNotice(''); setPhase('connecting'); setUploading(false); setGalleryFailed(false); setListing(null); setArchiveReview('');
    try {
      let welcomePending = true;
      let greetingCount = 0;
      function greet() {
        const socket = session.socket;
        if (!welcomePending || session.stopCue || !session.captureStarted || !session.ready || greetingCount < 1 ||
            current.current !== session || closing.current || socket?.readyState !== WebSocket.OPEN) return;
        welcomePending = false;
        if (session.voice.hasSpeech || session.waiting || session.picking) return;
        const variant = (nextGreeting.current[session.language] ?? Math.floor(Math.random() * greetingCount)) % greetingCount;
        socket.send(JSON.stringify({ type: 'greet', variant }));
        nextGreeting.current[session.language] = (variant + 1) % greetingCount;
      }
      function forwardFrame(socket: WebSocket, frame: MicFrame, rms = pcmLevel(frame.pcm)) {
        if (session.waiting) {
          session.startup.add(frame);
          return;
        }
        const { pcm, rate } = frame;
        const signal = session.voice.observe(rms, pcm.length * 500 / rate);
        if (session.manualTurns) {
          if (signal === 'hold') {
            session.preRoll.add(frame);
            return;
          }
          if (signal === 'start') {
            welcomePending = false;
            socket.send('{"type":"speech_start"}');
            session.pendingHistory = true;
            for (const prefix of session.preRoll.drain()) sendPcm(socket, prefix.pcm, prefix.rate);
          }
        }
        if (socket.bufferedAmount > 900_000) throw new Error('live_audio_backlog');
        sendPcm(socket, pcm, rate);
        if (signal === 'end') sendTurn(session, socket);
      }
      session.audio = createLiveAudio({
        vietnamese: session.language === 'vi',
        microphone(pcm, rate) {
          const socket = session.socket;
          if (current.current !== session || session.muted || session.picking || session.stopCue || session.readingReview) return;
          if (!session.captured) {
            session.captured = true;
            clearTimeout(session.inputTimeout);
            setCaptureReady(true);
          }
          const rms = pcmLevel(pcm);
          meterMicrophone(pcm, rms, session.voice.audible(rms));
          const frame = { pcm, rate };
          if (!session.ready || socket?.readyState !== WebSocket.OPEN) {
            session.startup.add(frame);
            return;
          }
          try { forwardFrame(socket, frame, rms); }
          catch { fail('Mất kết nối Live. Bạn mở lại phiên nhé.'); }
        },
        speaking(value) {
          if (current.current !== session || closing.current) return;
          if (session.playing === value) return;
          session.playing = value;
          if (value) {
            if (Platform.OS !== 'web') {
              session.captured = false;
              setCaptureReady(false);
            }
            lastVoiceAt.current = 0;
            voiceActive.current = false;
            microphone.current.fill(0);
            setUserSpeaking(false);
            setProcessing(false);
          } else {
            session.readingReview = false;
            watchInput(session);
          }
          setSpeaking(value);
          if (!value) level.current = 0;
        },
        error: message => { if (current.current === session) fail(message); },
      });
      exitCue.current?.stop();
      const cue = playCue(cues.current.enter);
      session.stopCue = cue.stop;
      void cue.done.then(() => {
        session.stopCue = undefined;
        greet();
      });
      // Open the provider connection while audio initializes. Native capture still
      // starts after the chime so it does not record the chime or cut it short.
      let reconnects = 0;
      function attach() {
        const socket = session.socket = openSellerLiveSocket(session.conversationId, preferences);
        function reconnect() {
          if (current.current !== session || session.socket !== socket || closing.current) return;
          if ((!session.ready && reconnects === 0) || reconnects >= 2) {
            fail('Mình chưa nối lại được Live. Bạn có thể mở lại để tiếp tục.');
            return;
          }
          welcomePending = false;
          reconnects++;
          const droppedSpeech = session.voice.hasSpeech || session.waiting;
          session.socket = undefined;
          clearTimeout(session.watchdog);
          clearTimeout(session.inputTimeout);
          session.voice.reset();
          session.preRoll.drain();
          session.startup.drain();
          session.waiting = session.ready = session.outputOpen = session.skipOutput = false;
          session.readingReview = false;
          session.audio?.flush();
          setProcessing(false); setInputReady(false); setPhase('reconnecting');
          setNotice(droppedSpeech ? 'Mất kết nối giữa chừng. Khi Live nối lại, bạn nói lại câu vừa rồi nhé.' : '');
          socket.close();
          session.reconnectTimer = setTimeout(() => {
            if (current.current === session && !closing.current) attach();
          }, reconnects * 500);
        }
        session.watchdog = setTimeout(() => reconnects ? reconnect() : fail('Live kết nối quá lâu. Kiểm tra máy chủ rồi thử lại.'), 24_000);
        socket.onerror = () => {
          if (current.current !== session || session.socket !== socket) return;
          if (session.finish) session.finish(); else reconnect();
        };
        socket.onclose = () => {
          if (current.current !== session || session.socket !== socket) return;
          if (session.finish) session.finish(); else reconnect();
        };
        socket.onmessage = message => {
          if (current.current !== session || session.socket !== socket || typeof message.data !== 'string') return;
          try {
            const event = JSON.parse(message.data) as LiveEvent;
            switch (event.type) {
              case 'ready':
                clearTimeout(session.watchdog);
                session.manualTurns = event.turn_protocol === 1;
                greetingCount = typeof event.greeting_count === 'number' && Number.isInteger(event.greeting_count)
                  ? event.greeting_count : 0;
                if (session.manualTurns) setInputReady(true);
                session.ready = true; setPhase('live');
                for (const frame of session.startup.drain()) forwardFrame(socket, frame);
                greet();
                watchInput(session);
                break;
              case 'audio_received':
                clearTimeout(session.inputTimeout);
                setInputReady(true);
                break;
              case 'audio': {
                if (session.finish) break;
                session.outputOpen = true;
                if (session.skipOutput || session.picking) break;
                const pcm = toByteArray(event.data);
                if (pcm.length > 2 && pcm.length % 2 === 0) {
                  // Keep the read-back containing the approval phrase out of the mic.
                  session.readingReview ||= event.review;
                  meter(pcmLevel(pcm), 4);
                  session.audio?.play(pcm);
                }
                break;
              }
              case 'interrupted':
                session.outputOpen = false;
                session.skipOutput = false;
                session.audio?.interrupt();
                break;
              case 'audio_end':
                session.outputOpen = false;
                session.readingReview = session.playing && session.readingReview;
                if (!session.skipOutput) session.audio?.flush();
                break;
              case 'turn_end':
                session.outputOpen = false;
                session.skipOutput = false;
                session.audio?.flush();
                if (event.clear_captions) discardCaptions(session, event.turn_id ?? session.fallbackTurn);
                else flushCaptions(session, true);
                if (!event.turn_id) session.fallbackTurn = createMessageId();
                setProcessing(false);
                if (session.waiting && !session.finish) {
                  session.waiting = false;
                  for (const frame of session.startup.drain()) forwardFrame(socket, frame);
                }
                break;
              case 'turn_saved':
                reconnects = 0;
                session.pendingHistory = session.voice.hasSpeech || session.waiting;
                interruptedHistory.current = undefined;
                {
                  const id = event.turn.response.facts.live_turn_id;
                  if (typeof id === 'string') discardCaptions(session, id, false);
                  else if (event.turn.response.facts.voice) onCaptions([]);
                }
                onSaved(event.turn);
                break;
              case 'finished':
                session.pendingHistory = false;
                interruptedHistory.current = undefined;
                session.finish?.(true);
                break;
              case 'transcript': {
                if (session.skipOutput && event.role === 'assistant') break;
                if (event.role === 'user') session.pendingHistory = true;
                const id = event.turn_id ?? session.fallbackTurn;
                if (session.closedTurns.has(id)) break;
                const key = liveMessageKey(id, event.role);
                session.captions.set(key, { turnId: id, role: event.role,
                  text: event.text.trim(), final: event.final || event.unclear });
                if (event.final || event.unclear) flushCaptions(session);
                else if (event.role === 'assistant') {
                  const user = session.captions.get(liveMessageKey(id, 'user'));
                  if (user && !session.visibleUserTurns.has(id)) user.final = true;
                  session.captionTimer ??= setTimeout(() => flushCaptions(session), 100);
                }
                break;
              }
              case 'draft': setListing(event.draft); break;
              case 'archive_review': setArchiveReview(event.name); break;
              case 'action_done':
                setArchiveReview('');
                if (event.draft) setListing(event.draft);
                if (event.changed) onShopChanged?.();
                break;
              case 'shop_result': session.pendingHistory = true; onResult(event); break;
              case 'image_rejected': setNotice(event.message); break;
              case 'reconnecting':
                if (session.finish) session.finish();
                else reconnect();
                break;
              case 'ended':
              case 'error':
                if (session.finish) session.finish();
                else if (reconnects && !session.ready) reconnect();
                else fail(event.message);
                break;
            }
          } catch {
            if (session.finish) session.finish();
            else fail('Chưa phát được phản hồi Live. Bạn mở lại phiên nhé.');
          }
        };
      }
      attach();
      if (Platform.OS !== 'web') {
        void Haptics.selectionAsync().catch(() => {});
      }
      if (current.current !== session || closing.current) return;
      await session.audio.start(Platform.OS === 'web' ? undefined : cue.done);
      if (current.current !== session || closing.current) return;
      session.captureStarted = true;
      greet();
      watchInput(session);
    } catch (error) {
      if (current.current === session) fail(error instanceof Error ? error.message : 'Chưa mở được Live.');
    }
  }

  useImperativeHandle(ref, () => ({
    start() {
      if (visible || closing.current) return;
      onCaptions([]); onResult(null);
      onOpen();
      void start();
    },
    openOrder(id) { close(id); },
  }));

  function pauseMicrophone(session: Session) {
    session.audio?.mute(true);
    session.captured = false;
    setCaptureReady(false);
    if (session.manualTurns && session.voice.hasSpeech) session.waiting = true;
    session.voice.reset();
    session.preRoll.drain();
    session.startup.drain();
    clearTimeout(session.inputTimeout);
    level.current = 0;
    microphone.current.fill(0);
    lastVoiceAt.current = 0;
    voiceActive.current = false;
    setUserSpeaking(false);
    if (session.socket?.readyState === WebSocket.OPEN) session.socket.send('{"type":"mute"}');
  }

  function watchInput(session: Session) {
    clearTimeout(session.inputTimeout);
    if (!session.ready || !session.captureStarted || session.captured || session.playing) return;
    session.inputTimeout = setTimeout(() => {
      if (current.current === session && !session.captured && !session.playing && !session.muted && !session.picking && !closing.current) {
        fail('Chưa nhận được âm thanh từ micro. Kiểm tra micro rồi bấm Mở lại Live.');
      }
    }, 5000);
  }

  function toggleMicrophone() {
    const session = current.current;
    if (!session?.ready || session.picking) return;
    session.muted = !session.muted;
    setMuted(session.muted);
    if (session.muted) pauseMicrophone(session);
    else { session.audio?.mute(false); watchInput(session); }
  }

  function interrupt() {
    const session = current.current;
    if (!session) return;
    session.skipOutput = session.outputOpen;
    session.readingReview = false;
    session.audio?.interrupt();
    if (session.muted) toggleMicrophone();
  }

  async function selectPhoto(retry = false) {
    const session = current.current;
    if (!session?.ready || session.picking || closing.current) return;
    const limit = 6 - (listing?.status === 'collecting' || listing?.status === 'ready' ? listing.image_count : 0);
    if (!retry && limit < 1) { setNotice('Bản nháp đã có đủ 6 ảnh.'); return; }
    session.picking = true;
    setPicking(true); setNotice('');
    if (speaking) {
      session.skipOutput = session.outputOpen;
      session.audio?.interrupt();
    }
    if (!session.muted) pauseMicrophone(session);
    try {
      if (!retry) {
        const images = await pickProductImages(limit, 1000);
        if (current.current !== session || !images.length) return;
        session.gallery = { images, requestId: createMessageId() };
      }
      const gallery = session.gallery;
      if (!gallery) return;
      setUploading(true);
      setGalleryFailed(false);
      const { data } = await uploadProductImages(gallery.images, session.conversationId, undefined, gallery.requestId);
      if (!data.product_draft) throw new Error('missing_draft');
      session.gallery = undefined;
      const saved = data.product_draft;
      onSaved({ message: 'Đã thêm ảnh sản phẩm', response: data, created_at: new Date().toISOString() });
      if (current.current !== session || closing.current) return;
      setListing(saved);
      if (session.socket?.readyState === WebSocket.OPEN) {
        session.skipOutput = false;
        session.socket.send(JSON.stringify({ type: 'images_added', draft_id: saved.id, run_id: data.run_id }));
      }
    } catch (error) {
      if (current.current === session) {
        setGalleryFailed(Boolean(session.gallery));
        setNotice(error instanceof ApiError ? error.message : 'Mình chưa lưu được ảnh. Bạn thử lại nhé.');
      }
    } finally {
      if (current.current === session) {
        session.picking = false;
        setPicking(false);
        setUploading(false);
        // Android may return the picker result before its foreground event.
        if (AppState.currentState === 'active' || AppState.currentState === null) {
          session.audio?.mute(session.muted);
          if (!session.muted) watchInput(session);
        }
      }
    }
  }

  function close(orderId?: number) {
    if (closing.current) return;
    closing.current = true;
    const session = current.current;
    transitioning.current = true;
    const socket = session?.socket;
    if (session?.ready && socket?.readyState === WebSocket.OPEN) {
      clearTimeout(session.inputTimeout);
      session.stopCue?.();
      session.audio?.close();
      session.audio = undefined;
      onDrain(true);
      session.finish = acknowledged => {
        const recoverId = acknowledged ? undefined : session.pendingHistory ? session.conversationId : interruptedHistory.current;
        disconnect();
        if (!transitioning.current) closing.current = false;
        onDrain(false, recoverId);
      };
      session.finishTimeout = setTimeout(session.finish, 2200);
      try { socket.send('{"type":"finish"}'); }
      catch { session.finish(); }
    } else {
      disconnect();
      onDrain(false, interruptedHistory.current);
    }
    exitCue.current = playCue(cues.current.exit, true);
    Animated.timing(progress, {
      toValue: 0, duration: reduceMotion ? 0 : 170,
      easing: Easing.out(Easing.cubic), useNativeDriver: USE_NATIVE_DRIVER,
    }).start(({finished}) => {
      transitioning.current = false;
      closing.current = Boolean(current.current?.finish);
      if (!finished) return;
      setPicking(false);
      onExit(orderId);
    });
  }

  if (!visible) return null;
  const copy = LIVE_TEXT[current.current?.language ?? preferences.language];
  const listening = phase === 'live' && inputReady && captureReady && !muted && !speaking && !picking;
  const status = phase === 'reconnecting' ? copy.reconnecting :
    phase === 'connecting' ? captureReady ? copy.buffering : copy.connecting : phase === 'idle' ? copy.retry :
    uploading ? copy.uploading : picking ? copy.choosing : speaking ? copy.speaking : muted ? copy.muted :
    userSpeaking ? copy.userSpeaking : processing ? copy.processing : captureReady ? copy.listening : copy.openingMic;
  const canSendTurn = listening && Boolean(current.current?.voice.hasSpeech) && !processing;
  const meterLabel = phase === 'idle' ? copy.retry : speaking ? copy.interrupt : canSendTurn ? copy.send : status;
  const finishSpeaking = () => {
    const session = current.current;
    const socket = session?.socket;
    if (!session || session.waiting || socket?.readyState !== WebSocket.OPEN || !session.voice.finish()) return;
    try { sendTurn(session, socket); }
    catch { fail('Mất kết nối Live. Bạn mở lại phiên nhé.'); }
  };
  const glowing = phase !== 'idle' && (!muted || speaking) && !picking;
  function control(icon: React.ComponentProps<typeof SystemIcon>['name'], label: string, action: () => void, disabled = false, end = false) {
    return <Pressable accessibilityRole="button" accessibilityLabel={label} disabled={disabled}
      style={({pressed}) => [styles.control, { backgroundColor: end ? IOS.redSoft : IOS.card, borderColor: end ? 'transparent' : IOS.separator },
        pressed && styles.pressed, disabled && styles.disabled]} onPress={action}>
      <SystemIcon name={icon} size={21} color={end ? (isDark ? '#FFABA5' : '#A43428') : IOS.label} />
    </Pressable>;
  }
  return <Animated.View testID="live-composer" style={[styles.panel, {
    opacity: progress.interpolate({ inputRange: [0, .25, 1], outputRange: [0, 0, 1] }),
    transform: [{ translateY: progress.interpolate({ inputRange: [0, 1], outputRange: [22, 0] }) },
      { scale: progress.interpolate({ inputRange: [0, .72, 1], outputRange: [.91, 1.015, 1] }) }],
  }]}>
    {notice ? <Text accessibilityRole="alert" style={[ui.error, styles.notice]}>{notice}</Text> : null}
    {galleryFailed && !picking && phase === 'live' ? <Pressable accessibilityRole="button" onPress={() => void selectPhoto(true)} style={styles.textAction}>
      <Text style={[ui.secondaryText, { color: BRAND.orangeInk }]}>{copy.retryPhotos}</Text>
    </Pressable> : null}
    {archiveReview && phase === 'live' ? <View testID="live-archive-review" style={[styles.listing, { backgroundColor: IOS.card, borderColor: IOS.separator }]}>
      <Text style={[ui.caption, { color: IOS.red }]}>{copy.confirmArchive}</Text>
      <Text numberOfLines={2} style={ui.listTitle}>{archiveReview}</Text>
    </View> : listing && listing.status !== 'cancelled' ? <View testID="live-product-draft" style={[styles.listing, { backgroundColor: IOS.card, borderColor: IOS.separator }]}>
      <Text style={[ui.caption, { color: BRAND.orangeInk }]}>
        {listing.status === 'published' ? copy.published : listing.status === 'ready' ? copy.confirmPublish : copy.draft}
      </Text>
      <Text selectable numberOfLines={2} style={ui.listTitle}>{listing.name ?? copy.untitled}</Text>
      <Text style={ui.caption}>
        {listing.price_vnd === null ? copy.noPrice : money(listing.price_vnd)} · {listing.stock ?? '—'} {copy.stock} · {listing.image_count} {copy.photos}
      </Text>
    </View> : null}
    <View style={[styles.controls, { backgroundColor: IOS.card, borderColor: IOS.separator }]}>
      {control('images-outline', copy.addPhotos, () => void selectPhoto(), phase !== 'live' || picking)}
      <Animated.View style={[styles.meterSlot, {transform: [
        {translateX: progress.interpolate({ inputRange: [0, 1], outputRange: [60, 0] })},
        {scaleX: progress.interpolate({ inputRange: [0, .77, 1], outputRange: [.42, 1.035, 1] })},
      ]}]}>
      <Pressable accessibilityRole={phase === 'idle' || speaking || canSendTurn ? 'button' : undefined} accessibilityLabel={meterLabel}
        accessibilityLiveRegion="polite" onPress={phase === 'idle' ? () => void start() : speaking ? interrupt : canSendTurn ? finishSpeaking : undefined}
        style={({pressed}) => [styles.meter, pressed && styles.pressed]}>
        <LiveOrb glow={glowing} animate={glowing && !reduceMotion} level={level} microphone={microphone} />
        <Text testID="live-status" style={styles.status} numberOfLines={1}>{status}</Text>
      </Pressable>
      </Animated.View>
      {control(muted ? 'mic-off-outline' : 'mic-outline', muted ? copy.enableMic : copy.disableMic, toggleMicrophone, phase !== 'live' || picking)}
      {control('call-outline', copy.finish, () => close(), false, true)}
    </View>
  </Animated.View>;
});

const styles = StyleSheet.create({
  panel: { width: '100%', maxWidth: 620, alignSelf: 'center', gap: 7 },
  notice: { paddingHorizontal: 6, paddingBottom: 3 },
  listing: { borderWidth: 1, borderRadius: 17, paddingHorizontal: 13, paddingVertical: 9, gap: 3 },
  textAction: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 6 },
  controls: { flexDirection: 'row', alignItems: 'center', gap: 5, padding: 5, borderRadius: 23, borderWidth: 1 },
  control: { width: 44, height: 44, borderRadius: 17, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  disabled: { opacity: .42 },
  pressed: { opacity: .72 },
  meterSlot: { flex: 1, minWidth: 0 },
  meter: { minHeight: 46, paddingHorizontal: 5, paddingTop: 24, paddingBottom: 4, justifyContent: 'flex-end', alignItems: 'center', borderRadius: 24 },
  status: { color: '#F5F5FF', fontWeight: '600', fontSize: 11, lineHeight: 15, textShadowColor: '#040914', textShadowOffset: { width: 0, height: 1 }, textShadowRadius: 3 },
});
