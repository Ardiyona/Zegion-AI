import { useState } from 'react';
import { FAMILY_COLORS, estimateVram } from '../models';

const COMPAT_CONFIG = {
  great:        { label: '✓ Great fit',   bg: 'rgba(74,222,128,0.12)',  color: '#4ade80', border: 'rgba(74,222,128,0.3)'  },
  ok:           { label: '✓ Compatible',  bg: 'rgba(96,165,250,0.12)',  color: '#60a5fa', border: 'rgba(96,165,250,0.3)'  },
  low:          { label: '⚠ Partial',     bg: 'rgba(251,191,36,0.12)',  color: '#fbbf24', border: 'rgba(251,191,36,0.3)'  },
  incompatible: { label: '✗ Too large',   bg: 'rgba(248,113,113,0.12)', color: '#f87171', border: 'rgba(248,113,113,0.3)' },
};

const statPill = {
  padding: '2px 8px', borderRadius: '8px', fontSize: '11px',
  background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)',
  color: 'var(--text-muted)', fontFamily: 'JetBrains Mono, monospace',
};

const btn        = 'mm-btn';
const btnPrimary = 'mm-btn mm-btn-primary';
const btnDanger  = 'mm-btn mm-btn-danger';
const btnAccent  = 'mm-btn mm-btn-accent';
const btnCancel  = 'mm-btn mm-btn-cancel';
const btnGhost   = 'mm-btn mm-btn-ghost';
const btnNeutral = 'mm-btn mm-btn-neutral';

const FILTER_TABS = ['All', 'Installed', 'Compatible'];

// ── Shared sub-components ────────────────────────────────────────────────────

function HardwareBar({ hardware }) {
  const { disk_free_gb, disk_total_gb, disk_drive, vram_gb, ram_gb, gpu_name } = hardware;
  const diskUsed = disk_total_gb - disk_free_gb;
  const diskPct = disk_total_gb ? Math.round((diskUsed / disk_total_gb) * 100) : 0;
  const diskColor = diskPct > 90 ? '#f87171' : diskPct > 75 ? '#fbbf24' : '#4ade80';

  return (
    <div style={{
      borderRadius: '10px', overflow: 'hidden',
      border: '1px solid var(--border-subtle)',
      background: 'var(--bg-elevated)',
      fontSize: '12px',
    }}>
      {/* Row 1 — GPU / VRAM / RAM */}
      <div style={{
        display: 'flex', gap: '20px', alignItems: 'center',
        padding: '10px 16px', flexWrap: 'wrap',
      }}>
        <span style={{ color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.07em', fontSize: '10px', flexShrink: 0 }}>
          Hardware
        </span>
        <span style={{ color: 'var(--text-secondary)' }}>🖥 {gpu_name}</span>
        {vram_gb > 0
          ? <span style={{ color: 'var(--text-secondary)' }}>VRAM <strong style={{ color: 'var(--text-primary)' }}>{vram_gb} GB</strong></span>
          : <span style={{ color: '#fbbf24', fontWeight: 600 }}>CPU-only</span>
        }
        <span style={{ color: 'var(--text-secondary)' }}>RAM <strong style={{ color: 'var(--text-primary)' }}>{ram_gb} GB</strong></span>
      </div>

      {/* Row 2 — Disk storage */}
      {disk_total_gb > 0 && (
        <div style={{
          borderTop: '1px solid var(--border-subtle)',
          padding: '10px 16px',
          display: 'flex', flexDirection: 'column', gap: '6px',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.07em', fontSize: '10px' }}>
              💾 Storage ({disk_drive})
            </span>
            <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
              <strong style={{ color: diskColor }}>{disk_free_gb} GB</strong>
              <span style={{ color: 'var(--text-muted)' }}> free of {disk_total_gb} GB</span>
            </span>
          </div>
          <div style={{ height: '5px', borderRadius: '3px', background: 'var(--bg-surface)', overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: '3px',
              background: diskColor,
              width: `${diskPct}%`, transition: 'width 0.4s',
            }} />
          </div>
        </div>
      )}
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
  if (compat === 'loading') {
    return (
      <span style={{
        padding: '3px 10px', borderRadius: '12px', fontSize: '11px', fontWeight: 600,
        background: 'var(--bg-elevated)', color: 'var(--text-muted)',
        border: '1px solid var(--border-subtle)', opacity: 0.6,
      }}>— checking</span>
    );
  }
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

function fmtBytes(bytes) {
  if (!bytes) return '';
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(2)} GB`;
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(1)} MB`;
  return `${(bytes / 1e3).toFixed(0)} KB`;
}

function fmtSpeed(bps) {
  if (!bps) return '';
  if (bps >= 1e9) return `${(bps / 1e9).toFixed(1)} GB/s`;
  if (bps >= 1e6) return `${(bps / 1e6).toFixed(1)} MB/s`;
  return `${(bps / 1e3).toFixed(0)} KB/s`;
}

function fmtEta(sec) {
  if (sec == null || sec <= 0) return '';
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function ProgressBar({ percent, status, isError, bytesDown, bytesTotal, speedBps, eta }) {
  const hasBytes = bytesTotal > 0;

  return (
    <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '5px' }}>
      {/* Bar */}
      <div style={{
        height: '5px', borderRadius: '3px', background: 'var(--bg-surface)',
        overflow: 'hidden',
      }}>
        <div style={{
          height: '100%', borderRadius: '3px',
          background: isError
            ? 'var(--error)'
            : 'linear-gradient(90deg, var(--accent), #a78bff)',
          width: isError ? '100%' : `${percent}%`,
          transition: 'width 0.4s ease',
        }} />
      </div>

      {/* Stats row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px' }}>
        {/* Left: status + bytes */}
        <span style={{
          fontSize: '11px',
          color: isError ? 'var(--error)' : 'var(--text-muted)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          flex: 1,
        }}>
          {isError ? status : hasBytes
            ? `${fmtBytes(bytesDown)} / ${fmtBytes(bytesTotal)}`
            : status}
        </span>

        {/* Right: speed · ETA · percent */}
        {!isError && (
          <div style={{ display: 'flex', gap: '8px', fontSize: '11px', color: 'var(--text-muted)', whiteSpace: 'nowrap', flexShrink: 0 }}>
            {speedBps > 0 && (
              <span style={{ color: 'var(--accent-hover)' }}>{fmtSpeed(speedBps)}</span>
            )}
            {eta != null && eta > 0 && (
              <span>~{fmtEta(eta)}</span>
            )}
            <span style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>{percent}%</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Storage warning dialog ───────────────────────────────────────────────────

function StorageWarningDialog({ modelName, required, available, onClose }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--bg-elevated)', border: '1px solid rgba(248,113,113,0.35)',
          borderRadius: '16px', padding: '28px 32px', maxWidth: '380px', width: '90%',
          display: 'flex', flexDirection: 'column', gap: '16px',
          boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '20px' }}>🚫</span>
          <span style={{ fontWeight: 700, fontSize: '15px', color: 'var(--text-primary)' }}>
            Not enough disk space
          </span>
        </div>
        <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          <strong style={{ color: 'var(--text-primary)', fontFamily: 'JetBrains Mono, monospace' }}>{modelName}</strong> requires{' '}
          <strong style={{ color: '#f87171' }}>{required} GB</strong> but only{' '}
          <strong style={{ color: '#fbbf24' }}>{available.toFixed(1)} GB</strong> is available.
        </p>
        <p style={{ margin: 0, fontSize: '12px', color: 'var(--text-muted)', lineHeight: 1.5 }}>
          Free up space or choose a smaller model before downloading.
        </p>
        <button
          onClick={onClose}
          className={btnNeutral}
          style={{ alignSelf: 'flex-end', padding: '8px 20px' }}
        >
          Got it
        </button>
      </div>
    </div>
  );
}

// ── Curated model card ───────────────────────────────────────────────────────

function ModelCard({ model, onSetActive, onDownload, onDelete, onCancel, cpuOnly, diskFreeGb }) {
  const { active: isActive, installed: isInstalled, downloading: isDownloading } = model;
  const [showStorageWarn, setShowStorageWarn] = useState(false);

  function handleDownload() {
    if (diskFreeGb > 0 && model.size_gb > diskFreeGb) {
      setShowStorageWarn(true);
      return;
    }
    onDownload(model.name);
  }

  return (
    <div style={{
      background: isActive ? 'rgba(124,106,255,0.07)' : 'var(--bg-elevated)',
      border: `1px solid ${isActive ? 'rgba(124,106,255,0.35)' : 'var(--border-subtle)'}`,
      borderRadius: '14px', padding: '16px',
      display: 'flex', flexDirection: 'column', gap: '10px',
      transition: 'border-color 0.2s, background 0.2s', position: 'relative',
    }}>
      {isActive && (
        <div style={{
          position: 'absolute', top: 0, left: '20px', right: '20px', height: '2px',
          background: 'linear-gradient(90deg, transparent, var(--accent), transparent)',
          borderRadius: '0 0 2px 2px',
        }} />
      )}

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
              }}>ACTIVE</span>
            )}
          </div>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: 0, lineHeight: 1.4 }}>{model.desc}</p>
        </div>
        <CompatBadge compat={model.compatibility} />
      </div>

      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        <span style={statPill}>{model.params}</span>
        <span style={statPill}>{model.size_gb} GB disk</span>
        {cpuOnly
          ? <span style={statPill}>needs {model.ram_required_gb} GB RAM</span>
          : <span style={statPill}>{model.vram_required_gb > 0 ? `${model.vram_required_gb} GB VRAM` : 'CPU-friendly'}</span>
        }
      </div>

      {isDownloading && model.progress ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <ProgressBar
            percent={model.progress.percent}
            status={model.progress.status}
            isError={model.progress.isError}
            bytesDown={model.progress.bytesDown}
            bytesTotal={model.progress.bytesTotal}
            speedBps={model.progress.speedBps}
            eta={model.progress.eta}
          />
          <button onClick={() => onCancel(model.name)} className={btnCancel}>
            ✕ Cancel
          </button>
        </div>
      ) : isInstalled ? (
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {!isActive && <button onClick={() => onSetActive(model.name)} className={btnPrimary}>Set Active</button>}
          {!isActive && <button onClick={() => onDelete(model.name)} className={btnDanger}>Delete</button>}
          {isActive && <span style={{ fontSize: '12px', color: 'var(--text-muted)', padding: '6px 0' }}>Currently active for all conversations</span>}
        </div>
      ) : (
        <button onClick={handleDownload} className={btnAccent} disabled={isDownloading}>
          ↓ Download ({model.size_gb} GB)
        </button>
      )}

      {showStorageWarn && (
        <StorageWarningDialog
          modelName={model.name}
          required={model.size_gb}
          available={diskFreeGb}
          onClose={() => setShowStorageWarn(false)}
        />
      )}
    </div>
  );
}

// ── Extra installed card (non-curated) ──────────────────────────────────────

function ExtraInstalledCard({ name, hardware, activeModel, onSetActive, onDelete }) {
  const isActive = name === activeModel;
  const vramEst = estimateVram(name);
  const ramEst = Math.round(vramEst * 2);

  const compat = (() => {
    const vram = hardware.vram_gb;
    const ram = hardware.ram_gb;
    if (vram === 0) {
      if (ram >= ramEst * 1.5) return 'great';
      if (ram >= ramEst) return 'ok';
      return 'incompatible';
    }
    if (vram >= vramEst * 1.2) return 'great';
    if (vram >= vramEst) return 'ok';
    if (vram >= vramEst * 0.7) return 'low';
    return 'incompatible';
  })();

  return (
    <div style={{
      background: isActive ? 'rgba(124,106,255,0.07)' : 'var(--bg-elevated)',
      border: `1px solid ${isActive ? 'rgba(124,106,255,0.35)' : 'var(--border-subtle)'}`,
      borderRadius: '14px', padding: '16px',
      display: 'flex', flexDirection: 'column', gap: '10px',
      position: 'relative',
    }}>
      {isActive && (
        <div style={{
          position: 'absolute', top: 0, left: '20px', right: '20px', height: '2px',
          background: 'linear-gradient(90deg, transparent, var(--accent), transparent)',
          borderRadius: '0 0 2px 2px',
        }} />
      )}

      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '8px' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '4px' }}>
            <span style={{ fontWeight: 600, fontSize: '13px', color: isActive ? 'var(--accent-hover)' : 'var(--text-primary)', fontFamily: 'JetBrains Mono, monospace' }}>
              {name}
            </span>
            <span style={{
              padding: '2px 8px', borderRadius: '12px', fontSize: '10px', fontWeight: 600,
              background: 'rgba(99,179,237,0.12)', color: '#63b3ed', border: '1px solid rgba(99,179,237,0.3)',
              letterSpacing: '0.04em',
            }}>Custom</span>
            {isActive && (
              <span style={{
                padding: '2px 8px', borderRadius: '12px', fontSize: '10px', fontWeight: 700,
                background: 'rgba(124,106,255,0.2)', color: 'var(--accent-hover)',
                border: '1px solid rgba(124,106,255,0.4)', letterSpacing: '0.06em',
              }}>ACTIVE</span>
            )}
          </div>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: 0 }}>Installed via Ollama CLI or custom download</p>
        </div>
        <CompatBadge compat={compat} />
      </div>

      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        <span style={statPill}>~{vramEst} GB VRAM est.</span>
      </div>

      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        {!isActive && <button onClick={() => onSetActive(name)} className={btnPrimary}>Set Active</button>}
        {!isActive && <button onClick={() => onDelete(name)} className={btnDanger}>Delete</button>}
        {isActive && <span style={{ fontSize: '12px', color: 'var(--text-muted)', padding: '6px 0' }}>Currently active for all conversations</span>}
      </div>
    </div>
  );
}

// ── Custom download section ──────────────────────────────────────────────────

function CustomDownloadSection({ downloadModel, cancelDownload, downloadProgress, isDownloading, onComplete, diskFreeGb }) {
  const [input, setInput] = useState('');
  const [storageWarn, setStorageWarn] = useState(null); // { required, available }

  const trimmed = input.trim();
  const isValid = trimmed.length > 0 && /[a-zA-Z]/.test(trimmed);
  const isActive = isDownloading.has(trimmed) && trimmed.length > 0;
  const progress = trimmed ? downloadProgress[trimmed] : null;

  const handleDownload = () => {
    if (!isValid || isActive) return;
    downloadModel(
      trimmed,
      () => setInput(''),
      (_name, required, available) => setStorageWarn({ required, available }),
    );
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleDownload();
  };

  return (
    <div style={{
      background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
      borderRadius: '14px', padding: '16px',
      display: 'flex', flexDirection: 'column', gap: '10px',
    }}>
      <span style={{
        fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)',
        textTransform: 'uppercase', letterSpacing: '0.08em',
      }}>
        Custom Model
      </span>

      <div style={{ display: 'flex', gap: '8px' }}>
        <input
          type="text"
          placeholder="e.g. llama3.1:70b"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isActive}
          style={{
            flex: 1,
            background: 'var(--bg-input)', border: '1px solid var(--border)',
            borderRadius: '8px', padding: '8px 12px', fontSize: '13px',
            color: 'var(--text-primary)', fontFamily: 'JetBrains Mono, monospace',
            outline: 'none', opacity: isActive ? 0.5 : 1,
          }}
        />
        {isActive ? (
          <button
            onClick={() => cancelDownload(trimmed)}
            className={btnCancel}
            style={{ whiteSpace: 'nowrap' }}
          >
            ✕ Cancel
          </button>
        ) : (
          <button
            onClick={handleDownload}
            disabled={!isValid}
            className={isValid ? btnAccent : `${btn} mm-btn-ghost`}
            style={{ whiteSpace: 'nowrap', width: 'auto' }}
          >
            ↓ Download
          </button>
        )}
      </div>

      {progress ? (
        <ProgressBar
          percent={progress.percent}
          status={progress.status}
          isError={progress.isError}
          bytesDown={progress.bytesDown}
          bytesTotal={progress.bytesTotal}
          speedBps={progress.speedBps}
          eta={progress.eta}
        />
      ) : (
        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          Any model name from ollama.com/library
        </span>
      )}

      {storageWarn && (
        <StorageWarningDialog
          modelName={trimmed}
          required={Math.round(storageWarn.required * 10) / 10}
          available={storageWarn.available}
          onClose={() => setStorageWarn(null)}
        />
      )}
    </div>
  );
}

// ── Section label ────────────────────────────────────────────────────────────

function SectionLabel({ children }) {
  return (
    <div style={{
      gridColumn: '1 / -1',
      fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)',
      textTransform: 'uppercase', letterSpacing: '0.08em',
      paddingTop: '8px',
    }}>
      {children}
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────

export function ModelManager({
  hardware, hardwareLoaded, cpuOnly,
  models, extraInstalled = [], activeModel,
  setActiveModel, downloadModel, cancelDownload, deleteModel, refresh,
  downloadProgress, isDownloading,
}) {
  const [search, setSearch] = useState('');
  const [filterTab, setFilterTab] = useState('All');

  const filteredCurated = models.filter(m => {
    const matchSearch = !search ||
      m.name.toLowerCase().includes(search.toLowerCase()) ||
      m.family.toLowerCase().includes(search.toLowerCase()) ||
      m.desc.toLowerCase().includes(search.toLowerCase());
    if (!matchSearch) return false;
    if (filterTab === 'Installed') return m.installed;
    if (filterTab === 'Compatible') return m.compatibility === 'great' || m.compatibility === 'ok';
    return true;
  });

  const installedCount = models.filter(m => m.installed).length + extraInstalled.length;

  const filteredExtra = extraInstalled.filter(name => {
    const matchSearch = !search || name.toLowerCase().includes(search.toLowerCase());
    if (!matchSearch) return false;
    if (filterTab === 'Compatible') {
      const vramEst = estimateVram(name);
      const vram = hardware.vram_gb;
      const ram = hardware.ram_gb;
      const ramEst = Math.round(vramEst * 2);
      if (vram === 0) return ram >= ramEst;
      return vram >= vramEst * 0.7;
    }
    // 'Installed' tab — all extra are installed by definition
    return true;
  });

  const showExtra = filteredExtra.length > 0;

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
            <h2 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>Model Manager</h2>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '2px 0 0' }}>Browse, download, and manage Ollama models</p>
          </div>
          <button onClick={refresh} className={btnGhost}>
            ↻ Refresh
          </button>
        </div>
        <HardwareBar hardware={hardware} />
        {hardwareLoaded && cpuOnly && (
          <div style={{
            display: 'flex', alignItems: 'flex-start', gap: '10px',
            padding: '10px 14px', borderRadius: '10px',
            background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.25)',
            fontSize: '12px',
          }}>
            <span style={{ fontSize: '16px', lineHeight: 1 }}>💡</span>
            <div>
              <span style={{ color: '#fbbf24', fontWeight: 600 }}>CPU-only mode detected. </span>
              <span style={{ color: 'var(--text-secondary)' }}>
                No dedicated GPU found — models run on RAM. Compatibility badges show RAM requirements.
                Models under 8B params work well for everyday chat.
              </span>
            </div>
          </div>
        )}
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
              className={`mm-tab${filterTab === tab ? ' active' : ''}`}
            >
              {tab}
              {tab === 'Installed' && ` (${installedCount})`}
            </button>
          ))}
        </div>
        <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: 'auto' }}>
          {filteredCurated.length + filteredExtra.length} model{filteredCurated.length + filteredExtra.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>

        {/* Custom download — always visible */}
        <CustomDownloadSection
          downloadModel={downloadModel}
          cancelDownload={cancelDownload}
          downloadProgress={downloadProgress}
          isDownloading={isDownloading}
          diskFreeGb={hardware.disk_free_gb}
        />

        {/* Extra installed (non-curated) */}
        {showExtra && (
          <div>
            <div style={{
              fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)',
              textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '10px',
            }}>
              Custom Models
            </div>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
              gap: '12px',
            }}>
              {filteredExtra.map(name => (
                <ExtraInstalledCard
                  key={name}
                  name={name}
                  hardware={hardware}
                  activeModel={activeModel}
                  onSetActive={setActiveModel}
                  onDelete={deleteModel}
                />
              ))}
            </div>
          </div>
        )}

        {/* Curated grid */}
        <div>
          {(showExtra || true) && (
            <div style={{
              fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)',
              textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '10px',
            }}>
              Curated Models
            </div>
          )}
          {filteredCurated.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-muted)', fontSize: '14px' }}>
              No models match your filter.
            </div>
          ) : (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
              gap: '12px',
            }}>
              {filteredCurated.map(m => (
                <ModelCard
                  key={m.name}
                  model={m}
                  cpuOnly={cpuOnly}
                  diskFreeGb={hardware.disk_free_gb}
                  onSetActive={setActiveModel}
                  onDownload={downloadModel}
                  onCancel={cancelDownload}
                  onDelete={deleteModel}
                />
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
