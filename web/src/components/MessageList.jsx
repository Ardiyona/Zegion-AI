import { useEffect, useRef } from 'react';

function ThinkingBubble({ status }) {
  return (
    <div className="message assistant">
      <div className="message-avatar">🤖</div>
      <div className="message-body">
        <div className="thinking">
          <div className="thinking-dots">
            <span /><span /><span />
          </div>
          <span className="thinking-status">{status || 'Berpikir...'}</span>
        </div>
      </div>
    </div>
  );
}

function formatTokens(n) {
  if (!n) return '0';
  if (n >= 1000) return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k`;
  return String(n);
}

function formatSeconds(n) {
  if (!n) return '0s';
  return `${Number(n).toFixed(n >= 10 ? 1 : 2)}s`;
}

function UsageDetails({ usage }) {
  const events = usage?.events || [];
  if (!usage || events.length === 0) return null;

  return (
    <details className="usage-details">
      <summary>
        Tokens: {formatTokens(usage.total_prompt_tokens)} in / {formatTokens(usage.total_output_tokens)} out · {formatSeconds(usage.total_time_s)}
      </summary>
      <div className="usage-events">
        {events.map((event, i) => (
          <div key={i} className="usage-event">
            <span>{event.phase}</span>
            <span>{formatTokens(event.prompt_tokens)} in / {formatTokens(event.output_tokens)} out · {formatSeconds(event.duration_s)}</span>
          </div>
        ))}
      </div>
    </details>
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
            <UsageDetails usage={msg.usage} />
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

export function MessageList({ messages, isThinking, thinkingStatus, onSuggestion }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking, thinkingStatus]);

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
      {isThinking && <ThinkingBubble status={thinkingStatus} />}
      <div ref={bottomRef} />
    </div>
  );
}
