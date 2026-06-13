import { useState } from 'react';
import { useModels } from '../hooks/useModels';
import { FAMILY_COLORS } from '../models';

const COMPAT_CONFIG = {
  great:        { label: '✓ Great fit',   bg: 'rgba(74,222,128,0.12)',  color: '#4ade80', border: 'rgba(74,222,128,0.3)'  },
  ok:           { label: '✓ Compatible',  bg: 'rgba(96,165,250,0.12)',  color: '#60a5fa', border: 'rgba(96,165,250,0.3)'  },
  low:          { label: '⚠ Partial',     bg: 'rgba(251,191,36,0.12)',  color: '#fbbf24', border: 'rgba(251,191,36,0.3)'  },
  incompatible: { label: '✗ Too large',   bg: 'rgba(248,113,113,0.12)', color: '#f87171', border: 'rgba(248,113,113,0.3)' },
};

function HardwareBar({ hardware }) {
  return (
    <div style={{
      display: 'flex', gap: '16px', alignItems: 'center',
      padding: '8px 16px', borderRadius: '10px',
      background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
      fontSize: '12px', color: 'var(--text-secondary)', flexWrap: 'wrap',
    }}>
      <span style={{ color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: '10px' }}>Hardware</span>
      <span>🖥 {hardware.gpu_name}</span>
      {hardware.vram_gb > 0 && <span>VRAM: <strong style={{ color: 'var(--text-primary)' }}>{hardware.vram_gb} GB</strong></span>}
      <span>RAM: <strong style={{ color: 'var(--text-primary)' }}>{hardware.ram_gb} GB</strong></span>
      {hardware.vram_gb === 0 && <span style={{ color: 'var(--mode-quick)', fontSize: '11px' }}>CPU-only mode</span>}
    </div>
  );
}

function FamilyBadge({ family }) {
  const c = FAMILY_COLORS[family] || { bg: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: 'var(--border)' };
  return (
    <span style={{
      padding: '2px 8px', borderRadius: '12px', fontSize: '10px', fontWeight: 600,
      background: c.bg, color: c.color, border: `1px solid ${c.border}`,
      letterSpacing: '0.04em',
    }}>
      {family}
    </span>
  );
}

function CompatBadge({ compat }) {
  const c = COMPAT_CONFIG[compat] || COMPAT_CONFIG.incompatible;
  return (
    <span style={{
      padding: '3px 10px', borderRadius: '12px', fontSize: '11px', fontWeight: 600,
      background: c.bg, color: c.color, border: `1px solid ${c.border}`,
    }}>
      {c.label}
    </span>
  );
}

function ProgressBar({ percent, status }) {
  return (
    <div style={{ width: '100%' }}>
      <div style={{
        height: '4px', borderRadius: '2px', background: 'var(--bg-elevated)',
        overflow: 'hidden', marginBottom: '4px',
      }}>
        <div style={{
          height: '100%', borderRadius: '2px',
          background: 'linear-gradient(90deg, var(--accent), #a78bff)',
          width: `${percent}%`, transition: 'width 0.3s ease',
        }} />
      </div>
      <div style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '80%' }}>{status}</span>
        <span>{percent}%</span>
      </div>
    </div>
  );
}

function ModelCard({ model, onSetActive, onDownload, onDelete }) {
  const isActive = model.active;
  const isInstalled = model.installed;
  const isDownloading = model.downloading;

  return (
    <div style={{
      background: isActive ? 'rgba(124,106,255,0.07)' : 'var(--bg-elevated)',
      border: `1px solid ${isActive ? 'rgba(124,106,255,0.35)' : 'var(--border-subtle)'}`,
      borderRadius: '14px',
      padding: '16px',
      display: 'flex',
      flexDirection: 'column',
      gap: '10px',
      transition: 'border-color 0.2s, background 0.2s',
      position: 'relative',
    }}>
      {/* Active glow line */}
      {isActive && (
        <div style={{
          position: 'absolute', top: 0, left: '20px', right: '20px', height: '2px',
          background: 'linear-gradient(90deg, transparent, var(--accent), transparent)',
          borderRadius: '0 0 2px 2px',
        }} />
      )}

      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '8px' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '4px' }}>
            <span style={{ fontWeight: 600, fontSize: '13px', color: isActive ? 'var(--accent-hover)' : 'var(--text-primary)', fontFamily: 'JetBrains Mono, monospace' }}>
              {model.name}
            </span>
            <FamilyBadge family={model.family} />
            {isActive && (
              <span style={{
                padding: '2px 8px', borderRadius: '12px', fontSize: '10px', fontWeight: 700,
                background: 'rgba(124,106,255,0.2)', color: 'var(--accent-hover)',
                border: '1px solid rgba(124,106,255,0.4)', letterSpacing: '0.06em',
              }}>
                ACTIVE
              </span>
            )}
          </div>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: 0, lineHeight: 1.4 }}>
            {model.desc}
          </p>
        </div>
        <CompatBadge compat={model.compatibility} />
      </div>

      {/* Stats row */}
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        <span style={statPill}>{model.params}</span>
        <span style={statPill}>{model.size_gb} GB disk</span>
        <span style={statPill}>{model.vram_required_gb > 0 ? `${model.vram_required_gb} GB VRAM` : 'CPU-friendly'}</span>
      </div>

      {/* Action area */}
      {isDownloading && model.progress ? (
        <ProgressBar percent={model.progress.percent} status={model.progress.status} />
      ) : isInstalled ? (
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {!isActive && (
            <button
              onClick={() => onSetActive(model.name)}
              style={btnPrimary}
            >
              Set Active
            </button>
          )}
          {!isActive && (
            <button
              onClick={() => onDelete(model.name)}
              style={btnDanger}
            >
              Delete
            </button>
          )}
          {isActive && (
            <span style={{ fontSize: '12px', color: 'var(--text-muted)', padding: '6px 0' }}>
              Currently active for all conversations
            </span>
          )}
        </div>
      ) : (
        <button
          onClick={() => onDownload(model.name)}
          style={btnAccent}
          disabled={isDownloading}
        >
          ↓ Download ({model.size_gb} GB)
        </button>
      )}
    </div>
  );
}

const statPill = {
  padding: '2px 8px', borderRadius: '8px', fontSize: '11px',
  background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)',
  color: 'var(--text-muted)', fontFamily: 'JetBrains Mono, monospace',
};

const btnBase = {
  padding: '6px 14px', borderRadius: '8px', fontSize: '12px', fontWeight: 500,
  border: 'none', cursor: 'pointer', fontFamily: 'Inter, sans-serif',
  transition: 'all 0.15s ease',
};

const btnPrimary = { ...btnBase, background: 'var(--accent-dim)', color: 'var(--accent-hover)', border: '1px solid rgba(124,106,255,0.25)' };
const btnDanger  = { ...btnBase, background: 'rgba(248,113,113,0.1)', color: '#f87171', border: '1px solid rgba(248,113,113,0.25)' };
const btnAccent  = { ...btnBase, background: 'var(--accent)', color: 'white', width: '100%' };

const FILTER_TABS = ['All', 'Installed', 'Compatible'];

export function ModelManager() {
  const { hardware, models, activeModel, setActiveModel, downloadModel, deleteModel, refresh } = useModels();
  const [search, setSearch] = useState('');
  const [filterTab, setFilterTab] = useState('All');

  const filtered = models.filter(m => {
    const matchSearch = m.name.toLowerCase().includes(search.toLowerCase()) ||
                        m.family.toLowerCase().includes(search.toLowerCase()) ||
                        m.desc.toLowerCase().includes(search.toLowerCase());
    if (!matchSearch) return false;
    if (filterTab === 'Installed') return m.installed;
    if (filterTab === 'Compatible') return m.compatibility === 'great' || m.compatibility === 'ok';
    return true;
  });

  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0,
      background: 'var(--bg-base)', overflow: 'hidden',
    }}>
      {/* Header */}
      <header style={{
        padding: '16px 24px', borderBottom: '1px solid var(--border-subtle)',
        background: 'var(--bg-surface)', display: 'flex', flexDirection: 'column', gap: '12px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <h2 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
              Model Manager
            </h2>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '2px 0 0' }}>
              Browse, download, and manage Ollama models
            </p>
          </div>
          <button
            onClick={refresh}
            style={{ ...btnBase, background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)', fontSize: '12px' }}
          >
            ↻ Refresh
          </button>
        </div>
        <HardwareBar hardware={hardware} />
        {activeModel && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            padding: '8px 14px', borderRadius: '10px',
            background: 'rgba(124,106,255,0.08)', border: '1px solid rgba(124,106,255,0.2)',
            fontSize: '12px',
          }}>
            <span style={{ color: 'var(--text-muted)' }}>Active model:</span>
            <span style={{ color: 'var(--accent-hover)', fontWeight: 600, fontFamily: 'JetBrains Mono, monospace' }}>{activeModel}</span>
            <span style={{ color: 'var(--text-muted)', marginLeft: 'auto', fontSize: '11px' }}>applies to all conversations</span>
          </div>
        )}
      </header>

      {/* Filter row */}
      <div style={{
        padding: '12px 24px', borderBottom: '1px solid var(--border-subtle)',
        background: 'var(--bg-surface)', display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap',
      }}>
        <input
          type="text"
          placeholder="Search models..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            flex: '1', minWidth: '160px', maxWidth: '280px',
            background: 'var(--bg-input)', border: '1px solid var(--border)',
            borderRadius: '8px', padding: '7px 12px', fontSize: '13px',
            color: 'var(--text-primary)', fontFamily: 'Inter, sans-serif', outline: 'none',
          }}
        />
        <div style={{ display: 'flex', gap: '4px' }}>
          {FILTER_TABS.map(tab => (
            <button
              key={tab}
              onClick={() => setFilterTab(tab)}
              style={{
                padding: '6px 14px', borderRadius: '8px', fontSize: '12px', fontWeight: 500,
                border: '1px solid', fontFamily: 'Inter, sans-serif', cursor: 'pointer',
                transition: 'all 0.15s',
                background: filterTab === tab ? 'var(--accent-dim)' : 'var(--bg-elevated)',
                color: filterTab === tab ? 'var(--accent-hover)' : 'var(--text-secondary)',
                borderColor: filterTab === tab ? 'rgba(124,106,255,0.3)' : 'var(--border-subtle)',
              }}
            >
              {tab}
              {tab === 'Installed' && ` (${models.filter(m => m.installed).length})`}
            </button>
          ))}
        </div>
        <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: 'auto' }}>
          {filtered.length} model{filtered.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Model grid */}
      <div style={{
        flex: 1, overflowY: 'auto', padding: '20px 24px',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
        gap: '12px',
        alignContent: 'start',
      }}>
        {filtered.length === 0 ? (
          <div style={{
            gridColumn: '1 / -1', textAlign: 'center', padding: '60px 0',
            color: 'var(--text-muted)', fontSize: '14px',
          }}>
            No models match your filter.
          </div>
        ) : (
          filtered.map(m => (
            <ModelCard
              key={m.name}
              model={m}
              onSetActive={setActiveModel}
              onDownload={downloadModel}
              onDelete={deleteModel}
            />
          ))
        )}
      </div>
    </div>
  );
}
