import { useEffect, useRef } from 'react';

function ThinkingBubble() {
  return (
    <div className="message assistant">
      <div className="message-avatar">🤖</div>
      <div className="message-body">
        <div className="thinking">
          <div className="thinking-dots">
            <span /><span /><span />
          </div>
          <span>Berpikir...</span>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ msg }) {
  const isUser = msg.role === 'user';

  const getModeClass = (modeKey) => {
    if (!modeKey) return '';
    if (modeKey === 'chat') return 'chat';
    if (modeKey === 'quick') return 'quick';
    if (modeKey === 'deep') return 'deep';
    return '';
  };

  return (
    <div className={`message ${isUser ? 'user' : 'assistant'}`}>
      <div className="message-avatar">{isUser ? '👤' : '🤖'}</div>
      <div className="message-body">
        <div className="message-bubble">{msg.content}</div>
        {msg.mode && (
          <div className="message-meta">
            <span className={`mode-badge ${getModeClass(msg.mode_key)}`}>
              {msg.mode}
            </span>
            {msg.plan?.length > 0 && (
              <span className="plan-chip">
                📋 {msg.plan.filter(p => p.action !== 'RESPOND').length} steps
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function WelcomeScreen({ onSuggestion }) {
  const suggestions = [
    'Siapa kamu?',
    'Lihat task ClickUp saya',
    'Buatkan file hello.py',
    'Lihat struktur project',
  ];

  return (
    <div className="welcome">
      <div className="welcome-icon">🤖</div>
      <h2>Halo! Saya Zegion</h2>
      <p>AI assistant lokal yang berjalan di komputer Anda. Tanya apa saja!</p>
      <div className="welcome-suggestions">
        {suggestions.map((s) => (
          <button key={s} className="suggestion-chip" onClick={() => onSuggestion(s)}>
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

export function MessageList({ messages, isThinking, onSuggestion }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  if (messages.length === 0 && !isThinking) {
    return (
      <div className="messages-container">
        <WelcomeScreen onSuggestion={onSuggestion} />
      </div>
    );
  }

  return (
    <div className="messages-container">
      {messages.map((msg, i) => (
        <MessageBubble key={i} msg={msg} />
      ))}
      {isThinking && <ThinkingBubble />}
      <div ref={bottomRef} />
    </div>
  );
}
