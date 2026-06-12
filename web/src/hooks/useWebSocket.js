import { useState, useEffect, useRef, useCallback } from 'react';

const WS_URL = 'ws://localhost:8000/ws';

export function useWebSocket() {
  const [status, setStatus] = useState('connecting'); // connecting | ready | error
  const [isThinking, setIsThinking] = useState(false);
  const wsRef = useRef(null);
  const onMessageRef = useRef(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus('connecting');
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[WS] Connected');
      setStatus('ready');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'thinking') {
          setIsThinking(true);
          return;
        }

        setIsThinking(false);

        if (onMessageRef.current) {
          onMessageRef.current(data);
        }
      } catch (e) {
        console.error('[WS] Parse error:', e);
      }
    };

    ws.onclose = () => {
      console.log('[WS] Disconnected, reconnecting in 3s...');
      setStatus('error');
      setIsThinking(false);
      setTimeout(connect, 3000);
    };

    ws.onerror = (err) => {
      console.error('[WS] Error:', err);
      setStatus('error');
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, [connect]);

  const sendMessage = useCallback((text) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      console.warn('[WS] Not connected');
      return false;
    }
    wsRef.current.send(JSON.stringify({ message: text }));
    return true;
  }, []);

  const setOnMessage = useCallback((handler) => {
    onMessageRef.current = handler;
  }, []);

  return { status, isThinking, sendMessage, setOnMessage };
}
