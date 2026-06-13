import { useState } from 'react';
import { useChat } from './hooks/useChat';
import { Sidebar } from './components/Sidebar';
import { MessageList } from './components/MessageList';
import { ChatInput } from './components/ChatInput';
import { ModelManager } from './components/ModelManager';

const AGENT_NAME = 'Zegion';
const AGENT_VERSION = '1.0';

export default function App() {
  const [view, setView] = useState('chat');

  const {
    conversations,
    activeConvId,
    messages,
    isThinking,
    wsStatus,
    sendMessage,
    stopExecution,
    newConversation,
    switchConversation,
    deleteConversation,
  } = useChat();

  const handleSuggestion = (text) => sendMessage(text);

  const activeConv = conversations.find(c => c.id === activeConvId);
  const lastMsg = messages.filter(m => m.role === 'assistant').slice(-1)[0];
  const lastModeKey = lastMsg?.mode_key;

  const getModeClass = (key) => key || '';

  return (
    <div className="app">
      <Sidebar
        conversations={conversations}
        activeConvId={activeConvId}
        status={wsStatus}
        onNewChat={newConversation}
        onSelectConv={(id) => { switchConversation(id); setView('chat'); }}
        onDeleteConv={deleteConversation}
        agentName={AGENT_NAME}
        agentVersion={AGENT_VERSION}
        view={view}
        onViewChange={setView}
      />

      {view === 'models' ? (
        <ModelManager />
      ) : (
        <main className="chat-area">
          {/* Header */}
          <header className="chat-header">
            <span className="chat-header-title">
              {activeConv?.title || 'New Chat'}
            </span>
            <div className="chat-header-right">
              {lastModeKey && (
                <span className={`mode-badge ${getModeClass(lastModeKey)}`}>
                  {lastModeKey === 'chat' && '💬 Chat'}
                  {lastModeKey === 'quick' && '⚡ Quick'}
                  {lastModeKey === 'deep' && '🔬 Deep'}
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
            onSend={sendMessage}
            onStop={stopExecution}
            isThinking={isThinking}
            disabled={isThinking || wsStatus !== 'ready'}
          />
        </main>
      )}
    </div>
  );
}
