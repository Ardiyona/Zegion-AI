import { useState, useEffect, useCallback, useRef } from 'react';
import { CURATED_MODELS } from '../models';

const API = 'http://localhost:8000';

function getCompatibility(model, hardware) {
  const vram = hardware.vram_gb;
  const ram = hardware.ram_gb;
  const req = model.vram_required_gb;
  const reqRam = model.ram_required_gb;

  if (vram === 0) {
    if (ram >= reqRam * 1.5) return 'great';
    if (ram >= reqRam) return 'ok';
    return 'incompatible';
  }
  if (vram >= req * 1.2) return 'great';
  if (vram >= req) return 'ok';
  if (vram >= req * 0.7) return 'low';
  return 'incompatible';
}

export function useModels() {
  const [hardware, setHardware] = useState({ ram_gb: 0, vram_gb: 0, gpu_name: 'Loading...' });
  const [installedModels, setInstalledModels] = useState([]);
  const [activeModel, setActiveModelState] = useState('');
  const [downloadProgress, setDownloadProgress] = useState({});
  const [isDownloading, setIsDownloading] = useState(new Set());
  const abortRefs = useRef({});

  const fetchHardware = useCallback(async () => {
    try {
      const r = await fetch(`${API}/system/hardware`);
      const data = await r.json();
      setHardware(data);
    } catch {
      // Ollama or server not running — keep defaults
    }
  }, []);

  const fetchInstalled = useCallback(async () => {
    try {
      const r = await fetch(`${API}/models/installed`);
      const data = await r.json();
      setInstalledModels(data.models || []);
    } catch {
      setInstalledModels([]);
    }
  }, []);

  const fetchActive = useCallback(async () => {
    try {
      const r = await fetch(`${API}/models/active`);
      const data = await r.json();
      setActiveModelState(data.model || '');
    } catch {
      // keep current
    }
  }, []);

  const refresh = useCallback(() => {
    fetchHardware();
    fetchInstalled();
    fetchActive();
  }, [fetchHardware, fetchInstalled, fetchActive]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const setActiveModel = useCallback(async (name) => {
    try {
      await fetch(`${API}/models/active`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: name }),
      });
      setActiveModelState(name);
    } catch {
      // ignore
    }
  }, []);

  const downloadModel = useCallback(async (name) => {
    setIsDownloading(prev => new Set(prev).add(name));
    setDownloadProgress(prev => ({ ...prev, [name]: { status: 'Preparing...', percent: 0 } }));

    const controller = new AbortController();
    abortRefs.current[name] = controller;

    try {
      const res = await fetch(`${API}/models/pull`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: name }),
        signal: controller.signal,
      });

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;
          try {
            const chunk = JSON.parse(raw);
            if (chunk.status === 'done') break;

            let percent = 0;
            if (chunk.total && chunk.completed) {
              percent = Math.round((chunk.completed / chunk.total) * 100);
            }
            setDownloadProgress(prev => ({
              ...prev,
              [name]: { status: chunk.status || 'Downloading...', percent },
            }));
          } catch {
            // malformed chunk — skip
          }
        }
      }

      await fetchInstalled();
      setDownloadProgress(prev => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
    } catch (err) {
      if (err.name !== 'AbortError') {
        setDownloadProgress(prev => ({ ...prev, [name]: { status: 'Error', percent: 0 } }));
      } else {
        setDownloadProgress(prev => {
          const next = { ...prev };
          delete next[name];
          return next;
        });
      }
    } finally {
      delete abortRefs.current[name];
      setIsDownloading(prev => {
        const next = new Set(prev);
        next.delete(name);
        return next;
      });
    }
  }, [fetchInstalled]);

  const deleteModel = useCallback(async (name) => {
    try {
      await fetch(`${API}/models/${encodeURIComponent(name)}`, { method: 'DELETE' });
      await fetchInstalled();
      // If deleted model was active, clear active
      setActiveModelState(prev => (prev === name ? '' : prev));
    } catch {
      // ignore
    }
  }, [fetchInstalled]);

  const models = CURATED_MODELS.map(m => ({
    ...m,
    compatibility: getCompatibility(m, hardware),
    installed: installedModels.includes(m.name),
    active: m.name === activeModel,
    downloading: isDownloading.has(m.name),
    progress: downloadProgress[m.name] || null,
  }));

  return {
    hardware,
    models,
    installedModels,
    activeModel,
    downloadProgress,
    isDownloading,
    setActiveModel,
    downloadModel,
    deleteModel,
    refresh,
  };
}
