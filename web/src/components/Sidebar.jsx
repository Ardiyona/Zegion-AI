export function Sidebar({ status, onNewChat, agentName = 'Zegion', agentVersion = '1.0' }) {
  const statusConfig = {
    ready: { dot: '', label: 'Connected' },
    connecting: { dot: 'loading', label: 'Connecting...' },
    error: { dot: 'offline', label: 'Disconnected' },
  };

  const { dot, label } = statusConfig[status] || statusConfig.connecting;

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-icon">🤖</div>
        <div className="sidebar-logo-text">
          <span className="sidebar-logo-name">{agentName}</span>
          <span className="sidebar-logo-version">v{agentVersion}</span>
        </div>
      </div>

      <button className="sidebar-new-chat" onClick={onNewChat}>
        ✦ &nbsp; New Chat
      </button>

      <span className="sidebar-label">Commands</span>
      {['/chat', '/quick', '/deep'].map((cmd) => (
        <div
          key={cmd}
          style={{
            padding: '8px 12px',
            borderRadius: '8px',
            color: 'var(--text-muted)',
            fontSize: '12px',
            fontFamily: 'JetBrains Mono, monospace',
          }}
        >
          {cmd}
        </div>
      ))}

      <div className="sidebar-status" style={{ marginTop: 'auto' }}>
        <span className={`status-dot ${dot}`} />
        <span className="status-text">{label}</span>
      </div>
    </aside>
  );
}
