import { useState, useRef, useEffect } from 'react';

export function ChatInput({ onSend, disabled }) {
  const [text, setText] = useState('');
  const textareaRef = useRef(null);

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
  }, [text]);

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="input-area">
      <div className="input-wrapper">
        <textarea
          ref={textareaRef}
          id="chat-input"
          className="chat-textarea"
          placeholder="Ketik pesan... (Enter kirim, Shift+Enter baris baru)"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
        />
        <button
          id="send-button"
          className="send-button"
          onClick={handleSend}
          disabled={!text.trim() || disabled}
          title="Kirim pesan"
        >
          ↑
        </button>
      </div>
      <p className="input-hint">
        /chat · /quick · /deep &nbsp;·&nbsp; Shift+Enter untuk baris baru
      </p>
    </div>
  );
}
