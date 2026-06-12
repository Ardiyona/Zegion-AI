import { useState, useEffect, useRef, useCallback } from 'react';

const API_BASE = 'http://localhost:8000';

export function useChat() {
  const [conversations, setConversations] = useState([]);
  const [activeConvId, setActiveConvId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [isThinking, setIsThinking] = useState(false);
  const [wsStatus, setWsStatus] = useState('connecting');
  const wsRef = useRef(null);

  // ── Fetch conversation list ────────────────────────
  const fetchConversations = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/conversations`);
      const data = await res.json();
      setConversations(data.conversations || []);
    } catch (e) {
      console.error('[API] Failed to fetch conversations:', e);
    }
  }, []);

  // ── Fetch messages for a conversation ─────────────
  const fetchMessages = useCallback(async (convId) => {
    try {
      const res = await fetch(`${API_BASE}/conversations/${convId}/messages`);
      const data = await res.json();
      setMessages(data.messages || []);
    } catch (e) {
      console.error('[API] Failed to fetch messages:', e);
    }
  }, []);

  // ── Connect WebSocket untuk conversation tertentu ──
  const connectWs = useCallback((convId) => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setWsStatus('connecting');
    const ws = new WebSocket(`ws://localhost:8000/ws/${convId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log(`[WS] Connected → conv: ${convId.slice(0, 8)}`);
      setWsStatus('ready');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'thinking') {
          setIsThinking(true);
          return;
        }

        setIsThinking(false);

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

          // Refresh conversation list untuk update title & timestamp
          fetchConversations();
        }

        if (data.type === 'error') {
          setMessages((prev) => [
            ...prev,
            { role: 'assistant', content: `Terjadi error: ${data.text}`, created_at: Date.now() / 1000 },
          ]);
        }
      } catch (e) {
        console.error('[WS] Parse error:', e);
      }
    };

    ws.onclose = () => {
      console.log('[WS] Disconnected');
      setWsStatus('error');
      setIsThinking(false);
    };

    ws.onerror = () => {
      setWsStatus('error');
    };
  }, [fetchConversations]);

  // ── Switch conversation ────────────────────────────
  const switchConversation = useCallback(async (convId) => {
    setActiveConvId(convId);
    setMessages([]);
    setIsThinking(false);
    await fetchMessages(convId);
    connectWs(convId);
  }, [fetchMessages, connectWs]);

  // ── New conversation ───────────────────────────────
  const newConversation = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/conversations`, { method: 'POST' });
      const conv = await res.json();
      setConversations((prev) => [conv, ...prev]);
      await switchConversation(conv.id);
    } catch (e) {
      console.error('[API] Failed to create conversation:', e);
    }
  }, [switchConversation]);

  // ── Delete conversation ────────────────────────────
  const deleteConversation = useCallback(async (convId) => {
    try {
      await fetch(`${API_BASE}/conversations/${convId}`, { method: 'DELETE' });
      setConversations((prev) => prev.filter((c) => c.id !== convId));

      // Jika yang dihapus adalah active, switch ke yang lain atau buat baru
      if (convId === activeConvId) {
        const remaining = conversations.filter((c) => c.id !== convId);
        if (remaining.length > 0) {
          await switchConversation(remaining[0].id);
        } else {
          await newConversation();
        }
      }
    } catch (e) {
      console.error('[API] Failed to delete conversation:', e);
    }
  }, [activeConvId, conversations, switchConversation, newConversation]);

  // ── Send message ───────────────────────────────────
  const sendMessage = useCallback((text) => {
    if (!text.trim() || isThinking || wsStatus !== 'ready') return;
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    // Tambah ke UI dulu (optimistic)
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text, created_at: Date.now() / 1000 },
    ]);

    wsRef.current.send(JSON.stringify({ message: text }));
  }, [isThinking, wsStatus]);

  // ── Init: load conversations, auto-select latest ──
  useEffect(() => {
    const init = async () => {
      await fetchConversations();
    };
    init();
  }, [fetchConversations]);

  // Auto-select conversation pertama saat list loaded
  useEffect(() => {
    if (conversations.length > 0 && !activeConvId) {
      switchConversation(conversations[0].id);
    }
  }, [conversations, activeConvId, switchConversation]);

  // Cleanup WS saat unmount
  useEffect(() => {
    return () => {
      wsRef.current?.close();
    };
  }, []);

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
    fetchConversations,
  };
}
