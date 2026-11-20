import { ProtectedImage } from '../../components/ui/ProtectedImage';
import { dockContentInset } from '../../components/layout/dockGeometry';
import { SystemIcon } from '../../components/ui/SystemIcon';
import { InterfaceIcon } from '../../components/ui/InterfaceIcon';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { forwardRef, useCallback, useEffect, useLayoutEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Animated, Platform, Pressable, ScrollView, ScrollViewInstance, Share, Text, TextInput, TextInputInstance, useWindowDimensions, View } from 'react-native';
import { cancelChatRequest, createMessageId, isTerminalChatError, recoverChatRequest } from '../../api/chatRequests';
import { API_URL, ApiError } from '../../api/client';
import { inExtension, isShopeeExtension } from '../../integrations/extension';
import { decidePriceProposal, decideProductDraft, decideProductEdit, deleteConversation, pinConversation, getConversation, getConversations, sendSellerMessage, uploadProductImages } from '../../api/sellerPilot';
import { ChatData, ConversationSummary, PriceProposal, ProductDraft, ProductEditProposal } from '../../api/types';
import { ProductEditCard } from './ProductEditCard';
import { ProductDraftCard } from './ProductDraftCard';
import { BrandLogo } from '../../components/ui/BrandLogo';
import { useTheme } from '../../theme/ThemeProvider';
import { money } from '../dashboard/DashboardScreen';
import { MessageText } from './MessageText';
import { ChatReportCard } from './ChatReportCard';
import { TypingIndicator } from './TypingIndicator';
import { Message, assistantMessage, latestProductCards, restoreMessages, uploadedImageUris } from './chatMessages';
import { HistoryRow } from './HistoryRow';
import { MessageEntrance } from './MessageEntrance';
import { ChatHistoryDrawer } from './ChatHistoryDrawer';
import { OrderEditor } from '../dashboard/OrderEditor';
import { OrderChatAction } from './OrderChatAction';
import { useAuth } from '../auth/AuthProvider';
import { LiveConversation, type LiveCaption, type LiveConversationHandle, type LiveShopResult } from './live/LiveConversation';
import { LiveOrb } from './live/LiveOrb';
import { useLivePreferences } from './live/preferences';
import { liveMessageKey } from './live/timeline';
import { encodeProductImage, pickProductImages, type PendingImage } from './productImages';

export type AssistantHandle = { newConversation: () => void; openHistory: () => void; ask: (message: string) => void };
type PendingChat = { id: string; conversationId: string; text: string; phase: 'uploading' | 'sending' | 'cancelling'; uploadId?: string };
const MAX_PRODUCT_IMAGES = 6;
const INPUT_MIN_HEIGHT = 46;
const INPUT_MAX_HEIGHT = 128;
const INPUT_LINE_HEIGHT = 23;
const INPUT_VERTICAL_PADDING = 21;
const STORAGE_BASE = 'sellerpilot:conversation:' + (inExtension() ? location.origin + ':' + new URLSearchParams(location.search).get('scope') : API_URL);
const PROMPTS = [
  { icon: 'trend', title: 'Hôm nay shop thế nào?', message: 'Hôm nay shop có bao nhiêu đơn và giá trị đơn hàng bao nhiêu?' },
  { icon: 'inventory', title: 'Kiểm tra hàng sắp hết', message: 'Những sản phẩm nào sắp hết hàng?' },
  { icon: 'search', title: 'Tìm sản phẩm trong shop', message: 'Shop đang có những sản phẩm nào?' },
  { icon: 'plan', title: 'Lập kế hoạch cho shop', message: 'Phân tích số liệu 7 ngày qua và lập kế hoạch kinh doanh 7 ngày tới. Chọn sản phẩm ưu tiên, lịch hành động, ý tưởng video TikTok và cách đo kết quả.' },
] as const;
const readableError = (e: unknown) => e instanceof ApiError
  ? e.code === 'active_product_draft' ? 'Máy chủ đang dùng luồng nhận ảnh cũ. Cần khởi động lại backend để nhận ảnh bổ sung; ảnh và lời nhắn của bạn vẫn được giữ.' : e.message
  : 'Chưa kết nối được SellerPilot. Kiểm tra Wi-Fi và máy đang chạy backend, rồi thử lại.';
const fallbackLabel = (reason: ChatData['fallback_reason']) => reason === 'invalid_response'
  ? 'Phản hồi AI chưa hợp lệ' : reason === 'provider_timeout' ? 'AI phản hồi quá lâu'
  : reason === 'provider_rate_limited' ? 'AI đang giới hạn lượt gọi'
  : reason === 'free_tier_restricted' ? 'OpenCode từ chối quyền miễn phí'
  : reason === 'free_model_unavailable' ? 'Model miễn phí chưa sẵn sàng'
  : reason === 'provider_rejected' ? 'Dịch vụ AI từ chối yêu cầu' : 'Chế độ cơ bản';

export const AssistantChat = forwardRef<AssistantHandle, { onShopChanged?: () => void; onToast?: (message: string) => void; keyboardVisible?: boolean; reduceMotion?: boolean; active?: boolean }>(function AssistantChat({ onShopChanged, onToast, keyboardVisible = false, reduceMotion = false, active = true }, ref) {
  const { ui, IOS, BRAND, desktop } = useTheme();
  const auth = useAuth();
  const STORAGE = STORAGE_BASE + (auth?.user ? ':' + auth.user.shop.slug + ':' + auth.user.user.id : '');
  const { height: windowHeight, width: windowWidth, fontScale } = useWindowDimensions();
  const compact = windowHeight < 740 || keyboardVisible;
  const insets = useSafeAreaInsets();
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [pendingImages, setPendingImages] = useState<PendingImage[]>([]);
  const [inputHeight, setInputHeight] = useState(INPUT_MIN_HEIGHT);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectingImages, setSelectingImages] = useState(false);
  const imageSelection = useRef(false);
  const [restoring, setRestoring] = useState(false);
  const [error, setError] = useState('');
  const [failedMessage, setFailedMessage] = useState('');
  const [historyOpen, setHistoryOpen] = useState(false);
  const [liveOpen, setLiveOpen] = useState(false);
  const [liveCaptions, setLiveCaptions] = useState<LiveCaption[]>([]);
  const livePreferences = useLivePreferences();
  const [liveResults, setLiveResults] = useState<LiveShopResult[]>([]);
  const live = useRef<LiveConversationHandle>(null);
  const liveGeneration = useRef(0);
  const liveProgress = useRef(new Animated.Value(0)).current;
  const composerOpacity = useMemo(() => liveProgress.interpolate({ inputRange: [0, .65, 1], outputRange: [1, 0, 0] }), [liveProgress]);
  const [orderId, setOrderId] = useState<number | null>(null);
  const [history, setHistory] = useState<ConversationSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState('');
  const [revealedHistoryId, setRevealedHistoryId] = useState<string | null>(null);
  const [historyBusy, setHistoryBusy] = useState<string | null>(null);
  const historyActionLock = useRef(false);
  const [decision, setDecision] = useState<number | null>(null);
  const [productDecision, setProductDecision] = useState<number | null>(null);
  const [decisionErrors, setDecisionErrors] = useState<Record<number, string>>({});
  const [productErrors, setProductErrors] = useState<Record<number, string>>({});
  const [editBusy, setEditBusy] = useState<number | null>(null);
  const [editErrors, setEditErrors] = useState<Record<number, string>>({});
  const [composerAreaHeight, setComposerAreaHeight] = useState(0);
  const scroll = useRef<ScrollViewInstance>(null), input = useRef<TextInputInstance>(null);
  const request = useRef<AbortController | null>(null), historyRequest = useRef<AbortController | null>(null);
  const generation = useRef(0), lock = useRef(false), decisionLock = useRef(false), nearBottom = useRef(true);
  const stopping = useRef(false);
  const dragging = useRef(false), userScrollUntil = useRef(0);
  const lastScroll = useRef({ y: 0, content: 0, viewport: 0 });
  const scrollFrame = useRef<number | null>(null);
  const immediateScroll = useRef(false);
  const reportAnchor = useRef<string | null>(null), threadTop = useRef(0);
  const readingReport = useRef(false);
  const holdReport = useCallback(() => {
    readingReport.current = true;
    reportAnchor.current = null;
    nearBottom.current = false;
  }, []);
  const pendingChat = useRef<PendingChat | null>(null);
  const draftHydrated = useRef(false);
  const conversationRef = useRef<string | null>(null);
  const [showLatest, setShowLatest] = useState(false);
  useEffect(() => { if (!active) setLiveOpen(false); }, [active]);
  const setMeasuredInputHeight = (measuredHeight: number) => {
    const nextHeight = Math.max(
      INPUT_MIN_HEIGHT,
      Math.min(INPUT_MAX_HEIGHT, Math.ceil(measuredHeight)),
    );
    setInputHeight(current => Math.abs(current - nextHeight) > 1 ? nextHeight : current);
  };
  const resizeComposerFromLines = (lineCount: number) => {
    setMeasuredInputHeight(Math.max(1, lineCount) * INPUT_LINE_HEIGHT * Math.max(1, fontScale) + INPUT_VERTICAL_PADDING);
  };
  useLayoutEffect(() => {
    if (Platform.OS !== 'web') return;
    const node = input.current as unknown as HTMLTextAreaElement | null;
    if (!node || typeof node.scrollHeight !== 'number') return;
    // Measure the actual textarea before paint. A hidden Text's delayed layout
    // event can otherwise leave the input expanded after the draft gets shorter.
    const {minHeight, maxHeight} = node.style;
    const scrollTop = node.scrollTop;
    // Zero avoids the textarea's default two-row intrinsic height on deletion.
    node.style.height = '0'; node.style.minHeight = '0'; node.style.maxHeight = 'none';
    const height = Math.max(INPUT_MIN_HEIGHT, Math.min(INPUT_MAX_HEIGHT, node.scrollHeight));
    node.style.height = height + 'px'; node.style.minHeight = minHeight; node.style.maxHeight = maxHeight;
    node.style.overflowY = height >= INPUT_MAX_HEIGHT ? 'auto' : 'hidden';
    node.scrollTop = node.selectionEnd === node.value.length ? node.scrollHeight : scrollTop;
    setMeasuredInputHeight(height);
  }, [draft, windowWidth, fontScale, desktop]);
  const followBottom = (animated = true) => {
    if (!nearBottom.current || reportAnchor.current) return;
    if (!animated) immediateScroll.current = true;
    if (scrollFrame.current !== null) return;
    scrollFrame.current = requestAnimationFrame(() => {
      scrollFrame.current = null;
      const smooth = !immediateScroll.current && !reduceMotion;
      immediateScroll.current = false;
      if (nearBottom.current && !reportAnchor.current) scroll.current?.scrollToEnd({ animated: smooth });
    });
  };
  const goBottom = () => { reportAnchor.current = null; readingReport.current = false; userScrollUntil.current = 0; nearBottom.current = true; setShowLatest(false); followBottom(); };
  const remember = (id: string | null) => {
    if (id !== conversationRef.current) reportAnchor.current = null;
    conversationRef.current = id; setConversationId(id);
    void (id ? AsyncStorage.setItem(STORAGE, id) : AsyncStorage.removeItem(STORAGE)).catch(() => {});
  };
  async function clearPending(entry: PendingChat) {
    if (pendingChat.current?.id !== entry.id) return;
    await AsyncStorage.removeItem(STORAGE + ':pending');
    if (pendingChat.current?.id === entry.id) pendingChat.current = null;
  }
  function appendAnswer(data: ChatData) {
    setMessages(items => {
      if (items.some(item => item.response?.run_id === data.run_id)) return items;
      readingReport.current = false;
      if (data.report && nearBottom.current) reportAnchor.current = data.run_id + ':a';
      return [...items, assistantMessage(data)];
    });
    if (data.product_draft?.status === 'published') onShopChanged?.();
  }
  function focusReport(id: string, top: number) {
    if (reportAnchor.current !== id) return;
    readingReport.current = true;
    nearBottom.current = false;
    requestAnimationFrame(() => {
      if (reportAnchor.current !== id) return;
      reportAnchor.current = null;
      scroll.current?.scrollTo({ y: Math.max(0, threadTop.current + top), animated: !reduceMotion });
      setShowLatest(false);
    });
  }
  const stop = async (showResult = true): Promise<boolean> => {
    if (stopping.current) return false;
    generation.current += 1; request.current?.abort(); request.current = null;
    const entry = pendingChat.current;
    if (!entry) { lock.current = false; setBusy(false); setRestoring(false); return true; }
    stopping.current = true;
    lock.current = true; setBusy(true); setRestoring(false); setError('Đang dừng phản hồi…');
    entry.phase = 'cancelling';
    try {
      await AsyncStorage.setItem(STORAGE + ':pending', JSON.stringify(entry));
      let { data } = await cancelChatRequest(entry.id);
      if (entry.uploadId) {
        const upload = await cancelChatRequest(entry.uploadId);
        if (data.status !== 'completed' && upload.data.status === 'completed') data = upload.data;
      }
      if (data.status === 'completed' && data.response && showResult) appendAnswer(data.response.data);
      await clearPending(entry); setFailedMessage('');
      setError(data.status === 'completed' ? '' : 'Đã dừng phản hồi.');
      return true;
    } catch {
      setFailedMessage(entry.text);
      setError('Chưa xác nhận được việc dừng trên máy chủ. Bấm thử lại khi có kết nối.');
      return false;
    } finally { stopping.current = false; lock.current = false; setBusy(false); }
  };
  const newConversation = async () => {
    if (!await stop(false)) return;
    draftHydrated.current = true;
    reportAnchor.current = null;
    remember(null); setMessages([]); setLiveCaptions([]); setLiveResults([]); setDraft(''); setPendingImages([]); setError(''); setFailedMessage('');
    setHistoryOpen(false); setLiveOpen(false); setDecisionErrors({}); nearBottom.current = true;
    setProductErrors({});
    void AsyncStorage.removeItem(STORAGE + ':draft').catch(() => {});
  };
  async function loadConversation(id: string) {
    if (!await stop(false)) return;
    const version = generation.current;
    const controller = new AbortController(); request.current = controller; lock.current = true;
    setRestoring(true); setError(''); setHistoryError('');
    try {
      const { data } = await getConversation(id, controller.signal);
      if (generation.current !== version) return;
      setMessages(restoreMessages(data.turns));
      setLiveCaptions([]); setLiveResults([]);
      remember(data.id); setHistoryOpen(false); setFailedMessage(''); nearBottom.current = true;
    } catch (e) {
      if (controller.signal.aborted || version !== generation.current) return;
      if (e instanceof ApiError && [404, 410].includes(e.status) && conversationRef.current === id) {
        remember(null); setMessages([]); setFailedMessage('');
      }
      setHistoryError(readableError(e)); setError('Chưa mở được hội thoại. Bạn có thể thử lại trong Lịch sử.');
    } finally {
      if (generation.current === version) { lock.current = false; setRestoring(false); }
    }
  }
  async function loadHistory() {
    historyRequest.current?.abort(); const controller = new AbortController(); historyRequest.current = controller;
    setHistoryLoading(true); setHistoryError('');
    try { const { data } = await getConversations(controller.signal); if (!controller.signal.aborted) setHistory(data.items); }
    catch (e) { if (!controller.signal.aborted) setHistoryError(readableError(e)); }
    finally { if (!controller.signal.aborted) setHistoryLoading(false); }
  }
  const openHistory = () => { setLiveOpen(false); setRevealedHistoryId(null); setHistoryOpen(true); void loadHistory(); };
  async function togglePin(item: ConversationSummary) {
    if (historyActionLock.current) return;
    historyActionLock.current = true; setHistoryBusy(item.id); setHistoryError('');
    try {
      await pinConversation(item.id, !item.is_pinned);
      setRevealedHistoryId(null);
      await loadHistory();
    } catch (error) { setHistoryError(readableError(error)); }
    finally { historyActionLock.current = false; setHistoryBusy(null); }
  }
  async function removeHistory(item: ConversationSummary) {
    if (historyActionLock.current) return;
    historyActionLock.current = true; setHistoryBusy(item.id); setHistoryError('');
    try {
      if (conversationRef.current === item.id && !await stop(false)) {
        setHistoryError('Chưa dừng được tin nhắn đang xử lý. Bạn thử lại nhé.'); return;
      }
      await deleteConversation(item.id);
      if (conversationRef.current === item.id) {
        remember(null); setMessages([]); setDraft(''); setPendingImages([]); setError('');
        setFailedMessage(''); setDecisionErrors({}); setProductErrors({}); nearBottom.current = true;
        await AsyncStorage.multiRemove([STORAGE + ':draft', STORAGE + ':pending']).catch(() => {});
      }
      setRevealedHistoryId(null);
      setHistory(items => items.filter(row => row.id !== item.id));
    } catch (error) { setHistoryError(readableError(error)); }
    finally { historyActionLock.current = false; setHistoryBusy(null); }
  }
  function confirmDelete(item: ConversationSummary) {
    if (Platform.OS === 'web') {
      if (window.confirm('Xóa cuộc trò chuyện này? Không thể khôi phục.')) void removeHistory(item);
    } else Alert.alert('Xóa cuộc trò chuyện?', 'Không thể khôi phục lịch sử này.', [
      { text: 'Hủy', style: 'cancel' }, { text: 'Xóa', style: 'destructive', onPress: () => void removeHistory(item) },
    ]);
  }
  async function send(value = draft, retry = false) {
    const text = value.trim();
    if (lock.current || decisionLock.current || imageSelection.current) return;
    if (retry && pendingChat.current?.phase === 'uploading') {
      const entry = pendingChat.current, version = generation.current;
      lock.current = true; setBusy(true);
      try {
        const recovered = await recoverChatRequest(entry.uploadId!);
        if (generation.current !== version) return;
        if (!recovered) {
          await cancelChatRequest(entry.uploadId!);
          await clearPending(entry);
          setFailedMessage(''); setError('Ảnh chưa tải xong. Bạn chọn hoặc gửi lại ảnh nhé.');
          return;
        }
        entry.phase = 'sending';
        await AsyncStorage.setItem(STORAGE + ':pending', JSON.stringify(entry));
        if (generation.current !== version) return;
        setPendingImages([]);
        setMessages(items => items.some(item => item.id === 'local:' + entry.id) ? items : [...items, {
          id: 'local:' + entry.id, role: 'user', text: entry.text,
          imageUris: uploadedImageUris(recovered.data),
        }]);
      } catch (e) {
        if (generation.current !== version) return;
        if (isTerminalChatError(e)) {
          await clearPending(entry);
          setFailedMessage(''); // Retained attachments can now be sent as a fresh upload.
          if (e.code === 'conversation_deleted') { remember(null); setMessages([]); }
        } else setFailedMessage(entry.text);
        setError(readableError(e)); return;
      } finally { if (generation.current === version) { lock.current = false; setBusy(false); } }
      return send(entry.text, true);
    }
    if (pendingChat.current && (!retry || pendingChat.current.text !== text)) {
      setError('Tin nhắn trước chưa rõ kết quả. Bấm Thử lại hoặc dừng yêu cầu trước khi gửi tiếp.');
      return;
    }
    if (!retry && pendingImages.length) {
      await sendProductImages(pendingImages, text);
      return;
    }
    if (!text) return;
    if (retry && pendingChat.current?.phase === 'cancelling') { await stop(); return; }
    lock.current = true; setBusy(true);
    draftHydrated.current = true;
    if (!retry) setDraft('');
    setError(''); setFailedMessage('');
    const version = generation.current, controller = new AbortController(); request.current = controller;
    const entry: PendingChat = pendingChat.current || {
      id: createMessageId(), conversationId: conversationRef.current || createMessageId(), text, phase: 'sending',
    };
    pendingChat.current = entry;
    const userId = 'local:' + entry.id;
    setMessages(items => items.some(item => item.id === userId) ||
      (retry && items.at(-2)?.text === text && items.at(-1)?.role === 'assistant')
      ? items : [...items, { id: userId, role: 'user', text }]);
    reportAnchor.current = null;
    userScrollUntil.current = 0; nearBottom.current = true; setShowLatest(false);
    try {
      // Persist identity before sending, including the first turn of a new chat.
      await AsyncStorage.multiSet([[STORAGE, entry.conversationId], [STORAGE + ':pending', JSON.stringify(entry)]]);
      if (generation.current !== version) return;
      remember(entry.conversationId);
      const { data } = await sendSellerMessage(text, controller.signal, entry.conversationId, entry.id, retry);
      if (generation.current !== version) return;
      appendAnswer(data);
      await clearPending(entry);
    } catch (e) {
      if (version !== generation.current || controller.signal.aborted) return;
      if (e instanceof ApiError && e.code === 'conversation_deleted') {
        await clearPending(entry); remember(null); setMessages([]); setFailedMessage(''); setError(e.message); return;
      }
      if (isTerminalChatError(e)) {
        await clearPending(entry);
      }
      setFailedMessage(text); setError(readableError(e));
    } finally { if (version === generation.current) { lock.current = false; setBusy(false); request.current = null; } }
  }
  useImperativeHandle(ref, () => ({ newConversation, openHistory, ask: (text) => {
    if (lock.current) { setDraft(text); onToast?.('Đã điền câu hỏi. Bạn có thể gửi khi phản hồi hiện tại hoàn tất.'); }
    else void send(text);
  } }));
  useEffect(() => {
    const version = generation.current;
    setRestoring(true);
    void AsyncStorage.multiGet([STORAGE, STORAGE + ':draft', STORAGE + ':pending']).then(async entries => {
      if (generation.current !== version || lock.current) return;
      draftHydrated.current = true;
      const savedDraft = entries[1]?.[1], savedId = entries[0]?.[1];
      if (savedDraft) setDraft(savedDraft);
      const raw = entries[2]?.[1];
      let pending: PendingChat | null = null;
      try {
        const value = raw ? JSON.parse(raw) as PendingChat : null;
        const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
        if (value && uuid.test(value.id) && uuid.test(value.conversationId) && typeof value.text === 'string'
          && ['uploading', 'sending', 'cancelling'].includes(value.phase)
          && (value.phase !== 'uploading' || typeof value.uploadId === 'string' && uuid.test(value.uploadId))) pending = value;
      } catch { /* An invalid local record must never be submitted. */ }
      if (!pending) {
        setRestoring(false);
        if (savedId) await loadConversation(savedId);
        return;
      }
      pendingChat.current = pending;
      remember(pending.conversationId);
      try {
        const { data } = await getConversation(pending.conversationId);
        if (generation.current !== version) return;
        setMessages(restoreMessages(data.turns));
      } catch { /* A first turn may not have committed yet; join it below. */ }
      if (generation.current !== version) return;
      setRestoring(false);
      if (pending.phase === 'cancelling') await stop();
      else await send(pending.text, true);
    }).catch(() => { draftHydrated.current = true; setRestoring(false); setError('Chưa khôi phục được tin nhắn đang chờ. Bạn mở lại ứng dụng để thử lại.'); });
    return () => { generation.current++; request.current?.abort(); historyRequest.current?.abort(); };
  }, []);
  useEffect(() => {
    if (!draftHydrated.current) return;
    const timer = setTimeout(() => { void AsyncStorage.setItem(STORAGE + ':draft', draft).catch(() => {}); }, 400);
    return () => clearTimeout(timer);
  }, [draft]);
  useEffect(() => { if (!draft) setInputHeight(INPUT_MIN_HEIGHT); }, [draft]);
  useEffect(() => {
    followBottom(false);
  }, [inputHeight, pendingImages.length, keyboardVisible]);
  useEffect(() => {
    // Content growth emits scroll events too. Only a real drag/wheel changes
    // following intent; otherwise a long answer incorrectly marks us "scrolled up".
    if (Platform.OS !== 'web') return;
    // The native contract returns a numeric handle; React Native Web returns
    // the DOM node. Narrow the web-only adapter instead of using legacy refs.
    const node = scroll.current?.getScrollableNode() as unknown as HTMLElement | undefined;
    const intent = () => {
      userScrollUntil.current = Date.now() + 1500;
      // A queued animation must yield immediately, before the throttled scroll
      // event arrives; otherwise it can undo the seller's wheel/touch movement.
      nearBottom.current = false;
      readingReport.current = false;
      reportAnchor.current = null;
    };
    node?.addEventListener('wheel', intent, { passive: true });
    node?.addEventListener('touchmove', intent, { passive: true });
    return () => {
      node?.removeEventListener('wheel', intent);
      node?.removeEventListener('touchmove', intent);
    };
  }, []);
  useEffect(() => {
    followBottom();
  }, [messages, busy, restoring]);
  useEffect(() => () => {
    reportAnchor.current = null;
    if (scrollFrame.current !== null) cancelAnimationFrame(scrollFrame.current);
  }, []);
  async function decide(proposal: PriceProposal, choice: 'confirm' | 'reject') {
    if (decisionLock.current || lock.current || restoring) return;
    const version = generation.current;
    decisionLock.current = true; setDecision(proposal.id); setDecisionErrors(errors => ({ ...errors, [proposal.id]: '' }));
    try {
      const { data } = await decidePriceProposal(proposal.id, choice);
      if (data.status === 'approved') onShopChanged?.();
      if (version !== generation.current) return;
      setMessages(items => items.map(item => item.response?.proposal?.id === data.id
        ? { ...item, response: { ...item.response, proposal: data } } : item));
      onToast?.(data.status === 'approved' ? 'Đã cập nhật giá trên shop.' : data.status === 'rejected' ? 'Đã bỏ qua đề xuất. Giá giữ nguyên.' : 'Giá đã thay đổi. Hãy tạo đề xuất mới.');
    } catch (e) {
      onShopChanged?.(); // A lost reply may follow a successful server-side write.
      if (version !== generation.current) return;
      if (e instanceof ApiError && e.status === 409) setMessages(items => items.map(item => item.response?.proposal?.id === proposal.id
        ? { ...item, response: { ...item.response, proposal: { ...item.response.proposal, status: 'conflict' } } } : item));
      setDecisionErrors(errors => ({ ...errors, [proposal.id]: readableError(e) }));
    }
    finally { decisionLock.current = false; setDecision(null); }
  }
  async function decideEdit(proposal: ProductEditProposal, choice: 'confirm' | 'reject') {
    if (decisionLock.current || lock.current || restoring) return;
    const version = generation.current;
    decisionLock.current = true; setEditBusy(proposal.id);
    setEditErrors(errors => ({ ...errors, [proposal.id]: '' }));
    try {
      const { data } = await decideProductEdit(proposal.id, choice);
      if (data.status === 'approved') onShopChanged?.();
      if (version !== generation.current) return;
      setMessages(items => items.map(item => item.response?.product_edit_proposal?.id === data.id
        ? { ...item, response: { ...item.response, product_edit_proposal: data } } : item));
      if (data.status === 'approved') onToast?.('Đã cập nhật sản phẩm trên shop.');
    } catch (e) {
      onShopChanged?.();
      if (version !== generation.current) return;
      if (e instanceof ApiError && e.status === 409) setMessages(items => items.map(item => item.response?.product_edit_proposal?.id === proposal.id
        ? { ...item, response: { ...item.response, product_edit_proposal: { ...item.response.product_edit_proposal, status: 'conflict' } } } : item));
      setEditErrors(errors => ({ ...errors, [proposal.id]: readableError(e) }));
    } finally { decisionLock.current = false; setEditBusy(null); }
  }
  async function pickProductImage() {
    if (lock.current || decisionLock.current || imageSelection.current) return;
    const version = generation.current;
    setError('');
    const remaining = MAX_PRODUCT_IMAGES - pendingImages.length;
    if (remaining <= 0) {
      setError(`Mỗi sản phẩm chọn tối đa ${MAX_PRODUCT_IMAGES} ảnh.`);
      return;
    }
    imageSelection.current = true; setSelectingImages(true);
    input.current?.blur();
    try {
      const normalizedImages = await pickProductImages(remaining);
      if (version !== generation.current || !normalizedImages.length) return;
      setPendingImages(current => [...current, ...normalizedImages].slice(0, MAX_PRODUCT_IMAGES));
    } catch {
      if (version === generation.current) setError('Chưa xử lý được ảnh. Bạn thử chọn lại giúp mình nhé.');
    } finally { imageSelection.current = false; setSelectingImages(false); }
  }
  async function sendProductImages(uploadAssets: PendingImage[], text: string) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setFailedMessage('');
    setError(''); setPendingImages([]); setDraft('');
    const version = generation.current, controller = new AbortController(); request.current = controller;
    const listingRequest = text || 'Tạo bản nháp sản phẩm từ các ảnh này. Tự viết tiêu đề và mô tả, hỏi lại nếu chưa rõ sản phẩm.';
    const entry: PendingChat = { id: createMessageId(), uploadId: createMessageId(),
      conversationId: conversationRef.current || createMessageId(), text: listingRequest, phase: 'uploading' };
    pendingChat.current = entry;
    const userId = 'local:' + entry.id;
    userScrollUntil.current = 0; nearBottom.current = true; setShowLatest(false);
    let uploaded: ChatData | null = null;
    let preparedAssets = uploadAssets;
    try {
      // Fast Refresh can preserve an attachment selected by an older app build.
      // Re-read attachments here so every image uses the reliable JSON route.
      if (preparedAssets.some(asset => !asset.base64)) {
        preparedAssets = await Promise.all(preparedAssets.map(encodeProductImage));
        if (generation.current !== version) return;
      }
      await AsyncStorage.multiSet([[STORAGE, entry.conversationId], [STORAGE + ':pending', JSON.stringify(entry)]]);
      if (generation.current !== version) return;
      remember(entry.conversationId);
      uploaded = (await uploadProductImages(preparedAssets, entry.conversationId, controller.signal, entry.uploadId)).data;
      if (generation.current !== version) return;
      remember(uploaded.conversation_id);
      setMessages(items => [...items, {
        id: userId,
        role: 'user',
        text: text || `Đã gửi ${preparedAssets.length} ảnh sản phẩm`,
        imageUris: preparedAssets.map(asset => asset.uri),
      }]);
      entry.phase = 'sending';
      await AsyncStorage.setItem(STORAGE + ':pending', JSON.stringify(entry));
      if (generation.current !== version) return;
      const response = (await sendSellerMessage(listingRequest, controller.signal, entry.conversationId, entry.id)).data;
      if (generation.current !== version) return;
      appendAnswer(response);
      await clearPending(entry);
    } catch (e) {
      if (version !== generation.current || controller.signal.aborted) return;
      const terminal = isTerminalChatError(e);
      if (terminal) await clearPending(entry);
      if (terminal && e.code === 'conversation_deleted') { remember(null); setMessages([]); }
      if (uploaded) {
        setMessages(items => [...items, assistantMessage(uploaded!)]);
        setFailedMessage(entry.text);
      } else {
        setPendingImages(preparedAssets);
        setDraft(text); setFailedMessage(terminal ? '' : entry.text);
      }
      setError(readableError(e));
    } finally {
      if (version === generation.current) { lock.current = false; setBusy(false); request.current = null; }
    }
  }
  async function decideDraft(productDraft: ProductDraft, choice: 'publish' | 'cancel') {
    if (decisionLock.current || lock.current || restoring) return;
    const version = generation.current, decidedConversation = conversationRef.current;
    decisionLock.current = true; setProductDecision(productDraft.id);
    setProductErrors(errors => ({ ...errors, [productDraft.id]: '' }));
    try {
      const { data } = await decideProductDraft(productDraft.id, choice);
      if (data.status === 'published') onShopChanged?.();
      if (version !== generation.current || conversationRef.current !== decidedConversation) return;
      setMessages(items => {
        const index = items.findLastIndex(item => item.response?.product_draft?.id === data.id);
        return items.map((item, itemIndex) => itemIndex === index && item.response
          ? { ...item, response: { ...item.response, product_draft: data } } : item);
      });
      const targetConvoId = conversationRef.current || conversationId;
      if (targetConvoId) {
        try {
          const convo = await getConversation(targetConvoId);
          if (version === generation.current && conversationRef.current === decidedConversation && convo?.data?.turns?.length) setMessages(restoreMessages(convo.data.turns));
        } catch { /* ignore */ }
      }
      if (version !== generation.current || conversationRef.current !== decidedConversation) return;
      onToast?.(data.status === 'filled' ? 'Đã điền form. Kiểm tra các mục trên trang người bán trước khi lưu.' : data.status === 'published' ? 'Đã đăng sản phẩm lên UTech Official.' : 'Đã hủy bản nháp sản phẩm.');
    } catch (e) {
      onShopChanged?.();
      if (version !== generation.current || conversationRef.current !== decidedConversation) return;
      setProductErrors(errors => ({ ...errors, [productDraft.id]: readableError(e) }));
    } finally {
      decisionLock.current = false; setProductDecision(null);
    }
  }
  async function share(text: string) {
    try {
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(text); onToast?.('Đã sao chép câu trả lời.');
      } else await Share.share({ message: text });
    } catch { onToast?.('Chưa thể chia sẻ. Bạn có thể nhấn giữ để chọn văn bản.'); }
  }
  const last = messages[messages.length - 1];
  const decisionPending = decision !== null || productDecision !== null || editBusy !== null;
  const actionsDisabled = busy || restoring || decisionPending || selectingImages || liveOpen;
  const liveAvailable = Boolean(active && auth?.user && !inExtension() && livePreferences?.ready);
  const showLiveButton = liveAvailable && !draft.trim() && !pendingImages.length && !busy;
  const threadMessages = liveCaptions.length ? [...messages, ...liveCaptions.flatMap<Message>(caption => {
    const id = liveMessageKey(caption.turnId, caption.role);
    if (caption.role === 'assistant' && !liveCaptions.some(item => item.turnId === caption.turnId && item.role === 'user')) return [];
    return messages.some(message => message.id === id) ? [] : [
      { id, text: caption.text, role: caption.role, livePending: true },
    ];
  })] : messages;
  const hasThread = threadMessages.length > 0 || liveResults.length > 0;
  const savedReportIds = new Set(messages.flatMap(message => {
    const results = message.response?.facts.live_results;
    return Array.isArray(results) ? (results as LiveShopResult[]).map(result => result.id) : [];
  }));
  const showOrderFromChat = (id: number) => {
    if (liveOpen) live.current?.openOrder(id);
    else { input.current?.blur(); setOrderId(id); }
  };
  const liveReportRow = (result: LiveShopResult, fallbackKey: string) => (
    <View key={result.id || fallbackKey} style={ui.assistantMessageRow} testID="live-shop-result">
      <View style={ui.assistantContent}>
        {result.report ? <ChatReportCard report={result.report} language={result.language} snapshotKey={result.id} onInteract={holdReport} />
          : result.language !== 'en' ? <View style={ui.assistantBubble}><MessageText text={result.answer} /></View> : null}
        {result.order_id ? <OrderChatAction action={{ id: result.order_id }} onOpen={showOrderFromChat} language={result.language} /> : null}
      </View>
    </View>
  );
  const productCardMessageIds = useMemo(() => latestProductCards(messages), [messages]);
  const proposalLabel = { approved: 'Đã cập nhật trên shop', rejected: 'Đã bỏ qua · Giá giữ nguyên', conflict: 'Giá đã thay đổi · Cần tạo đề xuất mới', pending: 'Chờ xác nhận' };

  return <View style={ui.chat}>
    <ScrollView ref={scroll} testID="chat-scroll" style={{ flex: 1 }} automaticallyAdjustKeyboardInsets={false} contentInsetAdjustmentBehavior="never" showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled" keyboardDismissMode="interactive"
      contentContainerStyle={[ui.chatScroll, !hasThread && ui.chatEmpty]}
      onLayout={() => { if (hasThread) followBottom(false); }}
      onScrollBeginDrag={() => {
        dragging.current = true;
        nearBottom.current = false;
        reportAnchor.current = null;
      }}
      onScrollEndDrag={() => { dragging.current = false; userScrollUntil.current = Date.now() + 1500; }}
      onMomentumScrollEnd={() => { dragging.current = false; userScrollUntil.current = 0; }}
      onScroll={event => {
        const { contentOffset, contentSize, layoutMeasurement } = event.nativeEvent;
        const previous = lastScroll.current;
        lastScroll.current = { y: contentOffset.y, content: contentSize.height, viewport: layoutMeasurement.height };
        // Browser wheel/trackpad scrolling doesn't always emit drag events.
        const liveWebScroll = Platform.OS === 'web' && liveOpen && contentSize.height >= previous.content
          && layoutMeasurement.height === previous.viewport && (contentOffset.y < previous.y - 2 || !nearBottom.current && contentOffset.y > previous.y);
        if (!liveWebScroll && !dragging.current && Date.now() > userScrollUntil.current) return;
        readingReport.current = false;
        nearBottom.current = contentSize.height - contentOffset.y - layoutMeasurement.height < 100;
        setShowLatest(!nearBottom.current);
      }} scrollEventThrottle={32}
      onContentSizeChange={() => {
        if (!hasThread) scroll.current?.scrollTo({ y: 0, animated: false });
        else if (nearBottom.current) followBottom(!liveOpen && !dragging.current);
        else if (!readingReport.current) setShowLatest(true);
      }}>
      {!hasThread && liveOpen ? <Animated.View style={[ui.welcome, {
        opacity: liveProgress.interpolate({ inputRange: [0, .25, 1], outputRange: [0, 0, 1] }),
        transform: [{ scale: liveProgress.interpolate({ inputRange: [0, 1], outputRange: [.84, 1] }) }],
      }]}>
        <View style={{ width: 94, height: 94, borderRadius: 47, overflow: 'hidden', alignItems: 'center', justifyContent: 'center' }}>
          <LiveOrb round animate={!reduceMotion} />
          <SystemIcon name="pulse-outline" size={27} color="#F4F6FF" />
        </View>
        <Text accessibilityRole="header" style={[ui.listTitle, { marginTop: 14 }]}>SellerPilot Live</Text>
      </Animated.View> : null}
      {!hasThread && !restoring && !liveOpen ? <>
        <View style={ui.welcome}><BrandLogo size={desktop ? 40 : keyboardVisible ? 40 : 56} /><Text accessibilityRole="header" style={[ui.welcomeTitle, { marginTop: desktop ? 16 : compact ? 16 : 24 }, !desktop && compact && { fontSize: 28, lineHeight: 36 }, keyboardVisible && { fontSize: 23, lineHeight: 30, letterSpacing: -.6 }]}>Mình giúp gì{ '\n' }cho shop hôm nay?</Text></View>
        {!keyboardVisible ? <View style={[ui.promptGrid, compact && { marginTop: 22 }]}>{PROMPTS.map(prompt => <Pressable key={prompt.title} accessibilityRole="button" accessibilityLabel={prompt.title} onPress={() => void send(prompt.message)} style={({ pressed }) => [ui.prompt, !desktop && compact && { minHeight: 84, padding: 12, gap: 8 }, pressed && { opacity: .65 }]}><InterfaceIcon name={prompt.icon} size={desktop ? 18 : compact ? 20 : 22} color={BRAND.navy} /><Text style={ui.promptText}>{prompt.title}</Text></Pressable>)}</View> : null}
      </> : null}
      {restoring ? <View style={ui.thinking}><ActivityIndicator color={BRAND.navy} /><Text style={ui.thinkingText}>Đang mở hội thoại…</Text></View> : <View style={ui.thread} onLayout={event => { threadTop.current = event.nativeEvent.layout.y; }}>{[
        ...threadMessages.flatMap(message => {
          const results = Array.isArray(message.response?.facts.live_results) ? message.response.facts.live_results as LiveShopResult[] : [];
          return [message.role === 'user'
        ? <MessageEntrance key={message.id} style={ui.userMessageRow} animate={!message.livePending && message.id === last?.id} reduceMotion={reduceMotion}><View testID="user-message" style={[ui.userBubble, Boolean(message.imageUris?.length) && ui.userBubbleMedia]}>{message.imageUris?.length === 1 ? <ProtectedImage testID="user-image-single" source={{ uri: message.imageUris[0] }} style={ui.userImageSingle} resizeMode="cover" /> : message.imageUris?.length ? <ScrollView testID="user-image-gallery" horizontal style={ui.userImageScroller} showsHorizontalScrollIndicator={false} contentContainerStyle={ui.userImageRow}>{message.imageUris.map((uri, index) => <ProtectedImage key={uri + index} source={{ uri }} style={ui.userImageMultiple} resizeMode="cover" />)}</ScrollView> : null}<Text selectable style={[ui.userText, Boolean(message.imageUris?.length) && ui.userTextWithMedia]}>{message.text}</Text></View></MessageEntrance>
        : <MessageEntrance key={message.id} style={ui.assistantMessageRow} animate={!message.livePending && !message.response?.facts.voice && message.id === last?.id} reduceMotion={reduceMotion} onLayout={message.response?.report && !message.response.facts.voice ? event => focusReport(message.id, event.nativeEvent.layout.y) : undefined}><View style={ui.assistantContent}><View style={[ui.row, { gap: 7, marginBottom: 8 }]}><BrandLogo size={20} /><Text style={ui.assistantName}>SellerPilot</Text></View><View style={ui.assistantBubble}><MessageText text={message.text} /></View>
          {message.response?.product_edit_proposal ? <ProductEditCard proposal={message.response.product_edit_proposal} busy={actionsDisabled} error={editErrors[message.response.product_edit_proposal.id]} onDecide={choice => void decideEdit(message.response!.product_edit_proposal!, choice)} /> : null}
          {message.response?.report && !isShopeeExtension() && !results.some(result => result.report
            && result.report.title === message.response?.report?.title
            && result.report.subtitle === message.response.report.subtitle) ? <ChatReportCard report={message.response.report} onInteract={holdReport} /> : null}
          {!isShopeeExtension() && !results.some(result => result.order_id) ?
            <OrderChatAction action={message.response?.facts.order_action} onOpen={showOrderFromChat} /> : null}
          {message.response?.proposal ? <View style={ui.proposal}>
            <View style={ui.proposalBody}><Text style={ui.proposalKicker}>{proposalLabel[message.response.proposal.status]}</Text><Text style={ui.listTitle}>{message.response.proposal.product_name}</Text><Text style={ui.caption}>SKU {message.response.proposal.sku}</Text><View style={ui.priceRow}><Text style={ui.oldPrice}>{money(message.response.proposal.old_price_vnd)}</Text><SystemIcon name="arrow-forward" size={17} color={IOS.secondary} /><Text style={ui.newPrice}>{money(message.response.proposal.new_price_vnd)}</Text></View>
              {decisionErrors[message.response.proposal.id] ? <Text style={ui.error}>{decisionErrors[message.response.proposal.id]}</Text> : null}</View>
            {message.response.proposal.status === 'pending' ? <View style={ui.proposalActions}><Pressable accessibilityRole="button" disabled={actionsDisabled} onPress={() => void decide(message.response!.proposal!, 'reject')} style={[ui.secondaryButton, { flex: 1, paddingHorizontal: 8 }]}><Text style={ui.secondaryText}>Bỏ qua</Text></Pressable><Pressable accessibilityRole="button" accessibilityLabel={'Xác nhận đổi giá SKU ' + message.response.proposal.sku} disabled={actionsDisabled} onPress={() => void decide(message.response!.proposal!, 'confirm')} style={[ui.primaryButton, { flex: 1.6, paddingHorizontal: 8 }, actionsDisabled && { opacity: .55 }]}>{decision === message.response.proposal.id ? <ActivityIndicator color="#FFF" size="small" /> : <SystemIcon name="checkmark" size={18} color="#FFF" />}<Text style={ui.primaryText}>Xác nhận đổi giá</Text></Pressable></View> : null}
          </View> : null}
          {productCardMessageIds.has(message.id) && message.response?.product_draft ? <ProductDraftCard draft={message.response.product_draft} busy={actionsDisabled} saving={productDecision === message.response.product_draft.id} error={productErrors[message.response.product_draft.id]} browser={isShopeeExtension()} onDecide={choice => void decideDraft(message.response!.product_draft!, choice)} /> : null}
          <View style={[ui.messageActions, message.livePending && { minHeight: 44 }]}>
            {!message.livePending ? <Pressable accessibilityRole="button" accessibilityLabel={Platform.OS === 'web' ? 'Sao chép câu trả lời' : 'Chia sẻ câu trả lời'} onPress={() => void share(message.text)} style={ui.messageAction}><SystemIcon name={Platform.OS === 'web' ? 'copy-outline' : 'share-outline'} size={17} color={IOS.secondary} /></Pressable> : null}
            {message.response?.mode === 'fallback' ? <Text style={ui.sourceText}>{fallbackLabel(message.response.fallback_reason)}</Text> : null}
          </View>
        </View></MessageEntrance>, ...results.map((result, index) => liveReportRow(result, message.id + ':report:' + index))];
        }),
        ...liveResults.flatMap((result, index) => result.id && savedReportIds.has(result.id)
          ? [] : [liveReportRow(result, 'live:report:' + index)]),
      ]}
      </View>}
      {busy ? <TypingIndicator active={active} /> : null}
      {error ? <View accessibilityLiveRegion="polite" style={ui.errorCard}><Text style={ui.error}>{error}</Text>{failedMessage ? <Pressable accessibilityRole="button" accessibilityLabel="Thử lại" disabled={busy} onPress={() => void send(failedMessage, true)} style={ui.secondaryButton}><SystemIcon name="refresh" color={BRAND.navy} size={17} /><Text style={ui.secondaryText}>Thử lại</Text></Pressable> : null}{pendingChat.current && !busy ? <Pressable accessibilityRole="button" accessibilityLabel="Dừng yêu cầu" onPress={() => void stop()} style={ui.secondaryButton}><Text style={ui.secondaryText}>Dừng yêu cầu</Text></Pressable> : null}</View> : null}
      {!liveOpen && !busy && !restoring && !keyboardVisible && last?.response?.suggestions?.length ? <ScrollView testID="chat-follow-ups" horizontal showsHorizontalScrollIndicator={false} keyboardShouldPersistTaps="handled" style={{ flexGrow: 0, height: Math.ceil(48 * fontScale + 28), maxHeight: Math.ceil(48 * fontScale + 28), marginTop: 12 }} contentContainerStyle={{ gap: 8, paddingBottom: 2, alignItems: 'center' }}>{last.response.suggestions.slice(0, 3).map(suggestion => <Pressable key={suggestion} accessibilityRole="button" onPress={() => void send(suggestion)} style={[ui.followUp, { minHeight: 44, maxWidth: 260, paddingVertical: 10 }]}><Text numberOfLines={2} style={[ui.followUpText, { flex: 0, flexShrink: 1 }]}>{suggestion}</Text><SystemIcon name="arrow-up-outline" size={15} color={BRAND.navy} /></Pressable>)}</ScrollView> : null}
    </ScrollView>
    {showLatest && hasThread ? <Pressable accessibilityRole="button" accessibilityLabel="Cuộn đến tin nhắn mới nhất" onPress={goBottom} style={[ui.circleButton, { position: 'absolute', right: 22, bottom: Math.max(12, composerAreaHeight + 12) }]}><SystemIcon name="arrow-down" size={20} color={BRAND.navy} /></Pressable> : null}
    <View testID="chat-composer" onLayout={event => { const height = Math.ceil(event.nativeEvent.layout.height); setComposerAreaHeight(current => Math.abs(current - height) > 1 ? height : current); }} style={[ui.composerArea, { paddingBottom: desktop || keyboardVisible ? 8 : dockContentInset(insets.bottom), flexShrink: 0 }]}>
      <View>
      <Animated.View pointerEvents={liveOpen ? 'none' : 'auto'} accessibilityElementsHidden={liveOpen} aria-hidden={liveOpen}
        importantForAccessibility={liveOpen ? 'no-hide-descendants' : 'auto'}
        style={liveOpen ? { position: 'absolute', bottom: 0, left: 0, right: 0, opacity: composerOpacity } : undefined}>
      {pendingImages.length ? <ScrollView testID="attachment-strip" horizontal style={ui.attachmentScroller} showsHorizontalScrollIndicator={false} keyboardShouldPersistTaps="handled" contentContainerStyle={ui.attachmentRow}>{pendingImages.map((pendingImage, index) => <View key={pendingImage.uri + index} style={ui.attachmentPreview}><ProtectedImage source={{ uri: pendingImage.uri }} style={ui.attachmentImage} resizeMode="cover" /><Pressable accessibilityRole="button" accessibilityLabel={`Bỏ ảnh số ${index + 1}`} hitSlop={10} onPress={() => setPendingImages(items => items.filter((_item, itemIndex) => itemIndex !== index))} style={ui.attachmentRemove}><SystemIcon name="close" size={17} color="#FFF" /></Pressable></View>)}{pendingImages.length < MAX_PRODUCT_IMAGES ? <Pressable accessibilityRole="button" accessibilityLabel="Thêm ảnh sản phẩm" onPress={() => void pickProductImage()} style={ui.attachmentAdd}><SystemIcon name="add" size={25} color={BRAND.navy} /><Text style={ui.attachmentCount}>{pendingImages.length}/{MAX_PRODUCT_IMAGES}</Text></Pressable> : null}</ScrollView> : null}
      <View style={ui.composer}><Pressable accessibilityRole="button" accessibilityLabel="Mở thư viện ảnh" disabled={actionsDisabled}
        onPress={() => void pickProductImage()} style={ui.composerPlus}><SystemIcon name="add" size={27} color={BRAND.navy} /></Pressable>
        <View style={ui.composerInputFrame}><TextInput ref={input} accessibilityLabel="Nhắn cho SellerPilot" placeholder={pendingImages.length ? 'Thêm yêu cầu…' : 'Hỏi SellerPilot…'} placeholderTextColor={IOS.secondary} value={draft} onChangeText={value => { setDraft(value); if (!value) setInputHeight(INPUT_MIN_HEIGHT); }} multiline maxLength={4000} scrollEnabled={inputHeight >= INPUT_MAX_HEIGHT - 1} returnKeyType="default" blurOnSubmit={false} onFocus={() => setTimeout(() => { if (nearBottom.current) scroll.current?.scrollToEnd({ animated: false }); }, 80)} style={[ui.composerInput, { height: inputHeight }]} editable={!restoring} />
          {Platform.OS !== 'web' ? <Text pointerEvents="none" accessible={false} aria-hidden onTextLayout={event => resizeComposerFromLines(event.nativeEvent.lines.length)} style={ui.composerMeasure}>{draft + '\u200B'}</Text> : null}</View>
        {showLiveButton ? <Pressable accessibilityRole="button" accessibilityLabel="Trò chuyện Live" disabled={actionsDisabled || Boolean(pendingChat.current)} onPress={() => { input.current?.blur(); live.current?.start(); }} style={({pressed}) => [ui.send, pressed && { transform: [{ scale: .95 }] }]}>
          <LiveOrb round />
          <SystemIcon name="pulse-outline" size={21} color="#FFF" />
        </Pressable> :
          <Pressable accessibilityRole="button" accessibilityLabel={busy ? 'Dừng chờ phản hồi' : 'Gửi tin nhắn'} disabled={!busy && ((!draft.trim() && !pendingImages.length) || restoring || decisionPending || selectingImages)} onPress={() => { if (busy) { void stop(); } else void send(); }} style={({ pressed }) => [ui.send, !busy && ((!draft.trim() && !pendingImages.length) || restoring) && ui.sendDisabled, pressed && { opacity: .7 }]}><SystemIcon name={busy ? 'stop' : 'arrow-up'} size={23} color={busy || draft.trim() || pendingImages.length ? '#FFF' : IOS.tertiary} /></Pressable>}
      </View>
      </Animated.View>
      {liveAvailable && livePreferences ? <LiveConversation ref={live} visible={liveOpen} conversationId={conversationId} progress={liveProgress}
        preferences={livePreferences.value} reduceMotion={reduceMotion}
        onCaptions={setLiveCaptions} onResult={result => setLiveResults(items => result ? [...items, result] : [])} onShopChanged={onShopChanged}
        onSaved={turn => {
          if (generation.current !== liveGeneration.current) return;
          if (turn.response.conversation_id && conversationRef.current !== turn.response.conversation_id) remember(turn.response.conversation_id);
          setMessages(items => items.some(item => item.response?.run_id === turn.response.run_id) ? items : [...items, ...restoreMessages([turn])]);
          const results = turn.response.facts.live_results;
          if (Array.isArray(results)) {
            const ids = new Set((results as LiveShopResult[]).map(result => result.id));
            setLiveResults(items => items.filter(result => !ids.has(result.id)));
          }
        }}
        onOpen={() => { liveGeneration.current = generation.current; setLiveOpen(true); goBottom(); }}
        onExit={(orderId, recoverId) => {
          setLiveOpen(false);
          if (recoverId && (recoverId !== conversationRef.current || liveCaptions.length || liveResults.length)) {
            const version = liveGeneration.current;
            void getConversation(recoverId).then(({data}) => {
              if (generation.current !== version || lock.current || (conversationRef.current && conversationRef.current !== data.id)) return;
              remember(data.id);
              setMessages(restoreMessages(data.turns)); setLiveCaptions([]); setLiveResults([]);
            }).catch(() => {});
          }
          if (orderId) setOrderId(orderId);
        }} /> : null}
      </View>
    </View>
    <ChatHistoryDrawer visible={historyOpen} onClose={() => setHistoryOpen(false)} reduceMotion={reduceMotion}><View style={ui.sheetHeader}><Text style={ui.sheetTitle}>Lịch sử</Text><Pressable accessibilityRole="button" accessibilityLabel="Đóng lịch sử trò chuyện" onPress={() => setHistoryOpen(false)} style={ui.circleButton}><SystemIcon name="close" color={IOS.label} size={22} /></Pressable></View><ScrollView contentContainerStyle={ui.sheetScroll} keyboardShouldPersistTaps="handled"><Pressable accessibilityRole="button" accessibilityLabel="Cuộc trò chuyện mới" onPress={newConversation} style={[ui.primaryButton, { marginBottom: 20 }]}><SystemIcon name="add" color="#FFF" size={20} /><Text style={ui.primaryText}>Cuộc trò chuyện mới</Text></Pressable>
      {historyLoading ? <ActivityIndicator color={BRAND.navy} /> : null}
      {historyError ? <View style={ui.errorCard}><Text style={ui.error}>{historyError}</Text><Pressable accessibilityRole="button" onPress={() => void loadHistory()} style={ui.secondaryButton}><Text style={ui.secondaryText}>Thử lại</Text></Pressable></View> : null}
      {!historyLoading && !historyError && !history.length ? <Text style={[ui.loadingText, { marginVertical: 30 }]}>Chưa có cuộc trò chuyện</Text> : null}
      {history.map((item, index) => <View key={item.id}>
        {index === 0 || Boolean(item.is_pinned) !== Boolean(history[index - 1]?.is_pinned) ? <Text style={[ui.caption, { marginTop: 12, marginBottom: 7 }]}>{item.is_pinned ? 'Đã ghim' : 'Gần đây'}</Text> : null}
        <HistoryRow item={item} selected={item.id === conversationId} revealed={revealedHistoryId === item.id}
          disabled={restoring || historyBusy !== null} busy={historyBusy === item.id} onReveal={setRevealedHistoryId}
          onOpen={() => void loadConversation(item.id)} onPin={() => void togglePin(item)} onDelete={() => confirmDelete(item)} />
      </View>)}
    </ScrollView></ChatHistoryDrawer>
    <OrderEditor id={orderId} initialView="tracking" onClose={() => setOrderId(null)} onUpdated={updated => { onShopChanged?.(); onToast?.('Đã cập nhật đơn #' + updated.id); }} />

  </View>;
});
