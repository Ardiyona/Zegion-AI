import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

function formatTime(ts) {
  if (!ts) return '';
  const date = new Date(ts * 1000);
  const now = new Date();
  const diffDays = Math.floor((now - date) / 86400000);

  if (diffDays === 0) return date.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
  if (diffDays === 1) return 'Kemarin';
  if (diffDays < 7) return `${diffDays} hari lalu`;
  return date.toLocaleDateString('id-ID', { day: 'numeric', month: 'short' });
}

function ConversationItem({ conv, isActive, onSelect, onDelete }) {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      className={`conv-item ${isActive ? 'active' : ''}`}
      onClick={() => onSelect(conv.id)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="conv-icon">💬</div>
      <div className="conv-body">
        <div className="conv-title">{conv.title || 'New Chat'}</div>
        <div className="conv-meta">
          <span>{conv.message_count || 0} pesan</span>
          <span>·</span>
          <span>{formatTime(conv.updated_at)}</span>
        </div>
      </div>
      {hovered && (
        <button
          className="conv-delete"
          onClick={(e) => { e.stopPropagation(); onDelete(conv.id); }}
          title="Hapus conversation"
        >
          ×
        </button>
      )}
    </div>
  );
}

const NAV_ITEMS = [
  { path: '/models', icon: '⬡', label: 'Models' },
];

export function Sidebar({
  conversations = [],
  activeConvId,
  status,
  onNewChat,
  onSelectConv,
  onDeleteConv,
  agentName = 'Zegion',
  agentVersion = '1.0',
}) {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  const statusConfig = {
    ready: { dot: '', label: 'Connected' },
    connecting: { dot: 'loading', label: 'Connecting...' },
    error: { dot: 'offline', label: 'Disconnected' },
  };
  const { dot, label } = statusConfig[status] || statusConfig.connecting;

  const today = new Date();
  const todayConvs = conversations.filter(c => {
    const d = new Date(c.updated_at * 1000);
    return d.toDateString() === today.toDateString();
  });
  const olderConvs = conversations.filter(c => {
    const d = new Date(c.updated_at * 1000);
    return d.toDateString() !== today.toDateString();
  });

  const handleSelectConv = (id) => {
    onSelectConv(id);
    navigate('/');
  };

  const handleNewChat = () => {
    onNewChat();
    navigate('/');
  };

  return (
    <aside className="sidebar">
      {/* Logo */}
      <div className="sidebar-logo">
        <div className="sidebar-logo-icon">🤖</div>
        <div className="sidebar-logo-text">
          <span className="sidebar-logo-name">{agentName}</span>
          <span className="sidebar-logo-version">v{agentVersion}</span>
        </div>
      </div>

      {/* New Chat Button */}
      <button className="sidebar-new-chat" onClick={handleNewChat}>
        ✦ &nbsp; New Chat
      </button>

      {/* Conversation List */}
      <div className="conv-list">
        {todayConvs.length > 0 && (
          <>
            <span className="sidebar-label">Hari ini</span>
            {todayConvs.map(conv => (
              <ConversationItem
                key={conv.id}
                conv={conv}
                isActive={conv.id === activeConvId && pathname === '/'}
                onSelect={handleSelectConv}
                onDelete={onDeleteConv}
              />
            ))}
          </>
        )}

        {olderConvs.length > 0 && (
          <>
            <span className="sidebar-label" style={{ marginTop: '12px' }}>Sebelumnya</span>
            {olderConvs.map(conv => (
              <ConversationItem
                key={conv.id}
                conv={conv}
                isActive={conv.id === activeConvId && pathname === '/'}
                onSelect={handleSelectConv}
                onDelete={onDeleteConv}
              />
            ))}
          </>
        )}

        {conversations.length === 0 && (
          <div style={{ padding: '12px', color: 'var(--text-muted)', fontSize: '12px', textAlign: 'center' }}>
            Belum ada percakapan
          </div>
        )}
      </div>

      {/* Nav items (Models, dll) */}
      {NAV_ITEMS.map(item => {
        const isActive = pathname === item.path;
        return (
          <button
            key={item.path}
            onClick={() => navigate(isActive ? '/' : item.path)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '10px 12px',
              borderRadius: 'var(--radius-md)',
              background: isActive ? 'var(--accent-dim)' : 'transparent',
              border: isActive ? '1px solid rgba(124,106,255,0.2)' : '1px solid transparent',
              color: isActive ? 'var(--accent-hover)' : 'var(--text-secondary)',
              fontSize: '13px',
              fontWeight: 500,
              cursor: 'pointer',
              transition: 'all var(--transition)',
              fontFamily: 'inherit',
              width: '100%',
              textAlign: 'left',
            }}
          >
            <span style={{ fontSize: '14px' }}>{item.icon}</span>
            {item.label}
          </button>
        );
      })}

      {/* Status */}
      <div className="sidebar-status">
        <span className={`status-dot ${dot}`} />
        <span className="status-text">{label}</span>
      </div>
    </aside>
  );
}
