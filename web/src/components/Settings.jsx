import { useState } from 'react';
import { apiFetch } from '../api';

const API = 'http://localhost:8000';

export function Settings() {
  const [status, setStatus] = useState(null); // null | 'loading' | 'success' | 'error'
  const [confirm, setConfirm] = useState(false);

  const handleReset = async () => {
    setStatus('loading');
    try {
      const res = await apiFetch('/system/global-profile', { method: 'DELETE' });
      const data = await res.json();
      setStatus(data.deleted ? 'success' : 'empty');
    } catch {
      setStatus('error');
    } finally {
      setConfirm(false);
    }
  };

  return (
    <main style={{ flex: 1, padding: '32px', overflowY: 'auto' }}>
      <h2 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>
        Settings
      </h2>
      <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '32px' }}>
        Konfigurasi dan maintenance Zegion AI
      </p>

      {/* Section: Memory */}
      <section style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-md)',
        padding: '20px',
        maxWidth: '520px',
      }}>
        <div style={{ marginBottom: '16px' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>
            Global Memory
          </h3>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', lineHeight: 1.6 }}>
            Zegion mengumpulkan fakta tentang kamu dari percakapan (role, preferensi, tech stack, dll)
            dan menggunakannya sebagai konteks. Reset ini menghapus semua data tersebut — berguna
            kalau memory sudah tidak akurat atau menyebabkan halusinasi.
          </p>
        </div>

        {!confirm ? (
          <button
            className="mm-btn mm-btn-danger"
            onClick={() => { setStatus(null); setConfirm(true); }}
          >
            Reset Global Memory
          </button>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <p style={{ fontSize: '12px', color: 'var(--error)', fontWeight: 500 }}>
              Yakin? Semua user profile yang terakumulasi akan dihapus permanen.
            </p>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                className="mm-btn mm-btn-danger"
                onClick={handleReset}
                disabled={status === 'loading'}
              >
                {status === 'loading' ? 'Menghapus...' : 'Ya, hapus sekarang'}
              </button>
              <button
                className="mm-btn mm-btn-ghost"
                onClick={() => setConfirm(false)}
                disabled={status === 'loading'}
              >
                Batal
              </button>
            </div>
          </div>
        )}

        {status === 'success' && (
          <p style={{ marginTop: '12px', fontSize: '12px', color: 'var(--success)' }}>
            ✓ Global memory berhasil direset.
          </p>
        )}
        {status === 'empty' && (
          <p style={{ marginTop: '12px', fontSize: '12px', color: 'var(--text-muted)' }}>
            Global memory sudah kosong, tidak ada yang perlu dihapus.
          </p>
        )}
        {status === 'error' && (
          <p style={{ marginTop: '12px', fontSize: '12px', color: 'var(--error)' }}>
            Gagal menghubungi server. Pastikan API berjalan.
          </p>
        )}
      </section>
    </main>
  );
}
