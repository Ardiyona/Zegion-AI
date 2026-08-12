import { Routes, Route, Navigate } from 'react-router-dom';
import { useChat } from './hooks/useChat';
import { useModels } from './hooks/useModels';
import { Sidebar } from './components/Sidebar';
import { MessageList } from './components/MessageList';
import { ChatInput } from './components/ChatInput';
import { ModelManager } from './components/ModelManager';
import { Settings } from './components/Settings';

const AGENT_NAME = 'Zegion';
const AGENT_VERSION = '1.0';

function ChatPage({ chat, activeModel }) {
  const { conversations, activeConvId, messages, isThinking, wsStatus, pendingNewChat, sendMessage, stopExecution } = chat;
  const activeConv = conversations.find(c => c.id === activeConvId);
  const lastMsg = messages.filter(m => m.role === 'assistant').slice(-1)[0];
  const lastModeKey = lastMsg?.mode_key;

  return (
    <main className="chat-area">
      <header className="chat-header">
        <span className="chat-header-title">{pendingNewChat ? 'New Chat' : (activeConv?.title || 'New Chat')}</span>
        <div className="chat-header-right">
          {activeModel && (
            <span className="model-pill">{activeModel}</span>
          )}
          {lastModeKey && (
            <span className={`mode-badge ${lastModeKey}`}>
              {lastModeKey === 'chat' && '💬 Chat'}
              {lastModeKey === 'quick' && '⚡ Quick'}
              {lastModeKey === 'deep' && '🔬 Deep'}
            </span>
          )}
        </div>
      </header>
      <MessageList
        messages={messages}
        isThinking={isThinking}
        onSuggestion={sendMessage}
      />
      <ChatInput
        onSend={sendMessage}
        onStop={stopExecution}
        isThinking={isThinking}
        disabled={isThinking || wsStatus !== 'ready'}
      />
    </main>
  );
}

export default function App() {
  const chat = useChat();
  const modelsState = useModels();

  return (
    <div className="app">
      <Sidebar
        conversations={chat.conversations}
        activeConvId={chat.activeConvId}
        status={chat.wsStatus}
        onNewChat={chat.newConversation}
        onSelectConv={chat.switchConversation}
        onDeleteConv={chat.deleteConversation}
        agentName={AGENT_NAME}
        agentVersion={AGENT_VERSION}
      />

      <Routes>
        <Route path="/" element={<ChatPage chat={chat} activeModel={modelsState.activeModel} />} />
        <Route path="/models" element={<ModelManager {...modelsState} />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}
