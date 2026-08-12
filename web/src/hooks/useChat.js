import { useState, useEffect, useRef, useCallback } from 'react';
import { apiFetch, wsUrl } from '../api';

const POLL_INTERVAL = 3000;

export function useChat() {
  const [conversations, setConversations] = useState([]);
  const [activeConvId, setActiveConvId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [isThinking, setIsThinking] = useState(false);
  const [wsStatus, setWsStatus] = useState('connecting');
  const [pendingNewChat, setPendingNewChat] = useState(false);

  const wsRef = useRef(null);
  const activeConvIdRef = useRef(null);
  const pollTimerRef = useRef(null);
  const isThinkingRef = useRef(false);
  const cancelledConvsRef = useRef(new Set());
  const pendingNewChatRef = useRef(false);
  const pendingMessageRef = useRef(null);
  const messagesRef = useRef([]);

  useEffect(() => { activeConvIdRef.current = activeConvId; }, [activeConvId]);
  useEffect(() => { isThinkingRef.current = isThinking; }, [isThinking]);
  useEffect(() => { pendingNewChatRef.current = pendingNewChat; }, [pendingNewChat]);
  useEffect(() => { messagesRef.current = messages; }, [messages]);

  // ── Fetch conversation list ────────────────────────
  const fetchConversations = useCallback(async () => {
    try {
      const res = await apiFetch(`/conversations`);
      const data = await res.json();
      setConversations(data.conversations || []);
    } catch (e) {
      console.error('[API] fetchConversations failed:', e);
    }
  }, []);

  // ── Fetch messages ─────────────────────────────────
  const fetchMessages = useCallback(async (convId) => {
    try {
      const res = await apiFetch(`/conversations/${convId}/messages`);
      const data = await res.json();
      return data.messages || [];
    } catch (e) {
      console.error('[API] fetchMessages failed:', e);
      return [];
    }
  }, []);

  // ── Stop polling ───────────────────────────────────
  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  // ── Start polling (WS disconnect fallback) ─────────
  const startPolling = useCallback((convId) => {
    stopPolling();
    pollTimerRef.current = setInterval(async () => {
      if (activeConvIdRef.current !== convId) { stopPolling(); return; }
      const msgs = await fetchMessages(convId);
      const lastMsg = msgs[msgs.length - 1];
      if (lastMsg?.role === 'assistant') {
        stopPolling();
        setIsThinking(false);
        fetchConversations();
        setMessages((prev) => {
          const lastPrev = prev[prev.length - 1];
          return lastPrev?.role === 'assistant' ? prev : msgs;
        });
      }
    }, POLL_INTERVAL);
  }, [stopPolling, fetchMessages, fetchConversations]);

  const hasPendingMessage = useCallback((msgs) => {
    if (!msgs || msgs.length === 0) return false;
    return msgs[msgs.length - 1]?.role === 'user';
  }, []);

  // ── Silent cleanup: delete empty conversation, reset to pending ──
  const cleanupEmptyConversation = useCallback(async (convId) => {
    try {
      await apiFetch(`/conversations/${convId}`, { method: 'DELETE' });
    } catch {}
    setConversations((prev) => prev.filter((c) => c.id !== convId));
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    setActiveConvId(null);
    activeConvIdRef.current = null;
    setMessages([]);
    setIsThinking(false);
    setPendingNewChat(true);
    pendingNewChatRef.current = true;
    setWsStatus('ready');
  }, []);

  // ── Connect WebSocket ──────────────────────────────
  const connectWs = useCallback((convId) => {
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }

    setWsStatus('connecting');
    const ws = new WebSocket(wsUrl(`/ws/${convId}`));
    wsRef.current = ws;

    ws.onopen = async () => {
      console.log(`[WS] Connected → ${convId.slice(0, 8)}`);
      setWsStatus('ready');

      // Pending message from lazy new chat — send immediately, skip history fetch
      if (pendingMessageRef.current) {
        const msg = pendingMessageRef.current;
        pendingMessageRef.current = null;
        ws.send(JSON.stringify({ message: msg }));
        return;
      }

      const msgs = await fetchMessages(convId);
      setMessages(msgs);
      if (hasPendingMessage(msgs)) {
        setIsThinking(true);
        startPolling(convId);
      } else {
        setIsThinking(false);
        stopPolling();
      }
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'thinking') {
          setIsThinking(true);
          return;
        }

        const currentConvId = activeConvIdRef.current;
        if (cancelledConvsRef.current.has(currentConvId)) {
          if (data.type === 'response' || data.type === 'cancelled') {
            cancelledConvsRef.current.delete(currentConvId);
          }
          return;
        }

        if (data.type === 'cancelled') {
          setIsThinking(false);
          stopPolling();
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            return last?.role === 'user' ? prev.slice(0, -1) : prev;
          });
          // Auto-delete conversation if now empty
          setTimeout(() => {
            if (messagesRef.current.length === 0 && activeConvIdRef.current === currentConvId) {
              cleanupEmptyConversation(currentConvId);
            }
          }, 0);
          return;
        }

        setIsThinking(false);
        stopPolling();

        if (data.type === 'response') {
          setMessages((prev) => [...prev, {
            role: 'assistant',
            content: data.text,
            mode: data.mode,
            mode_key: data.mode_key,
            plan: data.plan || [],
            usage: data.usage || {},
            created_at: Date.now() / 1000,
          }]);
          fetchConversations();
        }

        if (data.type === 'error') {
          setMessages((prev) => [...prev, {
            role: 'assistant',
            content: `Terjadi error: ${data.text}`,
            created_at: Date.now() / 1000,
          }]);
        }
      } catch (e) {
        console.error('[WS] Parse error:', e);
      }
    };

    ws.onclose = () => {
      console.log(`[WS] Disconnected → ${convId.slice(0, 8)}`);
      setWsStatus('error');
    };

    ws.onerror = () => { setWsStatus('error'); };
  }, [fetchMessages, fetchConversations, hasPendingMessage, startPolling, stopPolling, cleanupEmptyConversation]);

  // ── Switch conversation ────────────────────────────
  const switchConversation = useCallback(async (convId) => {
    if (convId === activeConvIdRef.current && !pendingNewChatRef.current) return;

    stopPolling();
    setPendingNewChat(false);
    pendingNewChatRef.current = false;
    pendingMessageRef.current = null;
    setActiveConvId(convId);
    activeConvIdRef.current = convId;
    setMessages([]);
    setIsThinking(false);

    const msgs = await fetchMessages(convId);
    setMessages(msgs);
    connectWs(convId);
  }, [fetchMessages, connectWs, stopPolling]);

  // ── New conversation — lazy, no API call until first message sent ──
  const newConversation = useCallback(() => {
    stopPolling();
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    setActiveConvId(null);
    activeConvIdRef.current = null;
    setMessages([]);
    setIsThinking(false);
    setPendingNewChat(true);
    pendingNewChatRef.current = true;
    pendingMessageRef.current = null;
    setWsStatus('ready');
  }, [stopPolling]);

  // ── Delete conversation ────────────────────────────
  const deleteConversation = useCallback(async (convId) => {
    try {
      await apiFetch(`/conversations/${convId}`, { method: 'DELETE' });
      const updated = conversations.filter((c) => c.id !== convId);
      setConversations(updated);

      if (convId === activeConvIdRef.current) {
        if (updated.length > 0) {
          await switchConversation(updated[0].id);
        } else {
          newConversation();
        }
      }
    } catch (e) {
      console.error('[API] deleteConversation failed:', e);
    }
  }, [conversations, switchConversation, newConversation]);

  // ── Stop execution ─────────────────────────────────
  const stopExecution = useCallback(async () => {
    const convId = activeConvIdRef.current;
    if (!convId) return;

    cancelledConvsRef.current.add(convId);
    setIsThinking(false);
    stopPolling();
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      return last?.role === 'user' ? prev.slice(0, -1) : prev;
    });

    // Auto-delete conversation if it becomes empty after cancel
    setTimeout(() => {
      if (messagesRef.current.length === 0 && activeConvIdRef.current === convId) {
        cleanupEmptyConversation(convId);
      }
    }, 0);

    try {
      await apiFetch(`/stop/${convId}`, { method: 'POST' });
    } catch (e) {
      console.error('[API] stopExecution failed:', e);
    }
  }, [stopPolling, cleanupEmptyConversation]);

  // ── Send message ───────────────────────────────────
  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || isThinkingRef.current) return;

    // Lazy conversation creation on first message
    if (pendingNewChatRef.current) {
      pendingMessageRef.current = text;
      setMessages([{ role: 'user', content: text, created_at: Date.now() / 1000 }]);
      setIsThinking(true);
      try {
        const res = await apiFetch(`/conversations`, { method: 'POST' });
        const conv = await res.json();
        setConversations((prev) => [conv, ...prev]);
        setActiveConvId(conv.id);
        activeConvIdRef.current = conv.id;
        setPendingNewChat(false);
        pendingNewChatRef.current = false;
        connectWs(conv.id); // onopen sends pendingMessageRef
      } catch (e) {
        console.error('[API] create conversation failed:', e);
        setIsThinking(false);
        setMessages([]);
        pendingMessageRef.current = null;
      }
      return;
    }

    if (wsStatus !== 'ready') return;
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text, created_at: Date.now() / 1000 },
    ]);
    wsRef.current.send(JSON.stringify({ message: text }));
  }, [wsStatus, connectWs]);

  // ── Init ───────────────────────────────────────────
  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  // Auto-select first conversation or enter pending mode
  useEffect(() => {
    if (activeConvIdRef.current || pendingNewChatRef.current) return;
    if (conversations.length > 0) {
      switchConversation(conversations[0].id);
    } else {
      setPendingNewChat(true);
      pendingNewChatRef.current = true;
      setWsStatus('ready');
    }
  }, [conversations, switchConversation]);

  // Cleanup
  useEffect(() => {
    return () => {
      wsRef.current?.close();
      stopPolling();
    };
  }, [stopPolling]);

  return {
    conversations,
    activeConvId,
    messages,
    isThinking,
    wsStatus,
    pendingNewChat,
    sendMessage,
    stopExecution,
    newConversation,
    switchConversation,
    deleteConversation,
  };
}
