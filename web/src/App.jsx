import { useState, useEffect, useCallback } from 'react';
import { Sidebar } from './components/Sidebar';
import { MessageList } from './components/MessageList';
import { ChatInput } from './components/ChatInput';
import { useWebSocket } from './hooks/useWebSocket';

const AGENT_NAME = 'Zegion';
const AGENT_VERSION = '1.0';

export default function App() {
  const [messages, setMessages] = useState([]);
  const [lastMode, setLastMode] = useState(null);

  const { status, isThinking, sendMessage, setOnMessage } = useWebSocket();

  // Handle incoming WebSocket messages
  useEffect(() => {
    setOnMessage((data) => {
      if (data.type === 'response') {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: data.text,
            mode: data.mode,
            mode_key: data.mode_key,
            plan: data.plan || [],
          },
        ]);
        setLastMode(data.mode_key);
      } else if (data.type === 'error') {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: `⚠️ ${data.text}`,
            mode: null,
          },
        ]);
      }
    });
  }, [setOnMessage]);

  // Send a message
  const handleSend = useCallback(
    (text) => {
      if (!text.trim() || isThinking) return;

      setMessages((prev) => [
        ...prev,
        { role: 'user', content: text },
      ]);

      sendMessage(text);
    },
    [isThinking, sendMessage]
  );

  // Suggestion chip clicked
  const handleSuggestion = useCallback(
    (text) => {
      handleSend(text);
    },
    [handleSend]
  );

  // New chat — clear local messages (backend keeps memory, just clear UI)
  const handleNewChat = useCallback(() => {
    setMessages([]);
    setLastMode(null);
  }, []);

  const getModeClass = (modeKey) => {
    if (!modeKey) return '';
    return modeKey;
  };

  return (
    <div className="app">
      <Sidebar
        status={status}
        onNewChat={handleNewChat}
        agentName={AGENT_NAME}
        agentVersion={AGENT_VERSION}
      />

      <main className="chat-area">
        {/* Header */}
        <header className="chat-header">
          <span className="chat-header-title">
            Chat dengan {AGENT_NAME}
          </span>
          <div className="chat-header-right">
            {lastMode && (
              <span className={`mode-badge ${getModeClass(lastMode)}`}>
                {lastMode === 'chat' && '💬 Chat'}
                {lastMode === 'quick' && '⚡ Quick'}
                {lastMode === 'deep' && '🔬 Deep'}
              </span>
            )}
          </div>
        </header>

        {/* Messages */}
        <MessageList
          messages={messages}
          isThinking={isThinking}
          onSuggestion={handleSuggestion}
        />

        {/* Input */}
        <ChatInput
          onSend={handleSend}
          disabled={isThinking || status !== 'ready'}
        />
      </main>
    </div>
  );
}
