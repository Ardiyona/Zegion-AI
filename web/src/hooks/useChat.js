import { useState, useEffect, useRef, useCallback } from 'react';

const API_BASE = 'http://localhost:8000';
const POLL_INTERVAL = 3000; // 3 detik

export function useChat() {
  const [conversations, setConversations] = useState([]);
  const [activeConvId, setActiveConvId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [isThinking, setIsThinking] = useState(false);
  const [wsStatus, setWsStatus] = useState('connecting');

  const wsRef = useRef(null);
  const activeConvIdRef = useRef(null); // ref agar closure WS bisa baca nilai terbaru
  const pollTimerRef = useRef(null);
  const isThinkingRef = useRef(false);

  // Sinkronkan ref dengan state
  useEffect(() => { activeConvIdRef.current = activeConvId; }, [activeConvId]);
  useEffect(() => { isThinkingRef.current = isThinking; }, [isThinking]);

  // ── Fetch conversation list ────────────────────────
  const fetchConversations = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/conversations`);
      const data = await res.json();
      setConversations(data.conversations || []);
    } catch (e) {
      console.error('[API] fetchConversations failed:', e);
    }
  }, []);

  // ── Fetch messages (return messages untuk dicek) ───
  const fetchMessages = useCallback(async (convId) => {
    try {
      const res = await fetch(`${API_BASE}/conversations/${convId}/messages`);
      const data = await res.json();
      const msgs = data.messages || [];
      setMessages(msgs);
      return msgs;
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

  // ── Start polling untuk conversation dengan pesan pending ──
  const startPolling = useCallback((convId) => {
    stopPolling();

    pollTimerRef.current = setInterval(async () => {
      // Hanya poll jika masih di conversation yang sama
      if (activeConvIdRef.current !== convId) {
        stopPolling();
        return;
      }

      const msgs = await fetchMessages(convId);
      const lastMsg = msgs[msgs.length - 1];

      // Jika sudah ada response dari assistant → stop poll
      if (lastMsg && lastMsg.role === 'assistant') {
        stopPolling();
        setIsThinking(false);
        fetchConversations(); // Refresh title di sidebar
      }
    }, POLL_INTERVAL);
  }, [stopPolling, fetchMessages, fetchConversations]);

  // ── Cek apakah ada pesan pending (user tanpa response) ──
  const hasPendingMessage = useCallback((msgs) => {
    if (!msgs || msgs.length === 0) return false;
    const last = msgs[msgs.length - 1];
    return last?.role === 'user';
  }, []);

  // ── Connect WebSocket ──────────────────────────────
  const connectWs = useCallback((convId) => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setWsStatus('connecting');
    const ws = new WebSocket(`ws://localhost:8000/ws/${convId}`);
    wsRef.current = ws;

    ws.onopen = async () => {
      console.log(`[WS] Connected → ${convId.slice(0, 8)}`);
      setWsStatus('ready');

      // Refresh messages saat WS connect — tangkap response yang tersimpan
      // saat WS sebelumnya terputus
      const msgs = await fetchMessages(convId);

      if (hasPendingMessage(msgs)) {
        // Response belum ada → mulai polling
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

        setIsThinking(false);
        stopPolling();

        if (data.type === 'response') {
          const newMsg = {
            role: 'assistant',
            content: data.text,
            mode: data.mode,
            mode_key: data.mode_key,
            plan: data.plan || [],
            created_at: Date.now() / 1000,
          };
          setMessages((prev) => [...prev, newMsg]);
          fetchConversations();
        }

        if (data.type === 'error') {
          setMessages((prev) => [
            ...prev,
            {
              role: 'assistant',
              content: `Terjadi error: ${data.text}`,
              created_at: Date.now() / 1000,
            },
          ]);
        }
      } catch (e) {
        console.error('[WS] Parse error:', e);
      }
    };

    ws.onclose = () => {
      console.log(`[WS] Disconnected → ${convId.slice(0, 8)}`);
      setWsStatus('error');
    };

    ws.onerror = () => {
      setWsStatus('error');
    };
  }, [fetchMessages, fetchConversations, hasPendingMessage, startPolling, stopPolling]);

  // ── Switch conversation ────────────────────────────
  const switchConversation = useCallback(async (convId) => {
    if (convId === activeConvIdRef.current) return;

    stopPolling();
    setActiveConvId(convId);
    setMessages([]);
    setIsThinking(false);

    // Fetch messages dulu sebelum connect WS
    // (onopen juga akan fetch lagi untuk tangkap response pending)
    await fetchMessages(convId);
    connectWs(convId);
  }, [fetchMessages, connectWs, stopPolling]);

  // ── New conversation ───────────────────────────────
  const newConversation = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/conversations`, { method: 'POST' });
      const conv = await res.json();
      setConversations((prev) => [conv, ...prev]);
      await switchConversation(conv.id);
    } catch (e) {
      console.error('[API] newConversation failed:', e);
    }
  }, [switchConversation]);

  // ── Delete conversation ────────────────────────────
  const deleteConversation = useCallback(async (convId) => {
    try {
      await fetch(`${API_BASE}/conversations/${convId}`, { method: 'DELETE' });

      const updated = conversations.filter((c) => c.id !== convId);
      setConversations(updated);

      if (convId === activeConvIdRef.current) {
        if (updated.length > 0) {
          await switchConversation(updated[0].id);
        } else {
          await newConversation();
        }
      }
    } catch (e) {
      console.error('[API] deleteConversation failed:', e);
    }
  }, [conversations, switchConversation, newConversation]);

  // ── Send message ───────────────────────────────────
  const sendMessage = useCallback((text) => {
    if (!text.trim() || isThinkingRef.current || wsStatus !== 'ready') return;
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    // Optimistic UI
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text, created_at: Date.now() / 1000 },
    ]);

    wsRef.current.send(JSON.stringify({ message: text }));
  }, [wsStatus]);

  // ── Init ───────────────────────────────────────────
  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  // Auto-select conversation pertama saat list loaded
  useEffect(() => {
    if (conversations.length > 0 && !activeConvIdRef.current) {
      switchConversation(conversations[0].id);
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
    sendMessage,
    newConversation,
    switchConversation,
    deleteConversation,
  };
}
