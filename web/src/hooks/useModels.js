import { useState, useEffect, useCallback, useRef } from 'react';
import { CURATED_MODELS } from '../models';

const API = 'http://localhost:8000';

const curatedNames = new Set(CURATED_MODELS.map(m => m.name));

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
  const [hardwareLoaded, setHardwareLoaded] = useState(false);
  const [installedModels, setInstalledModels] = useState([]);
  const [activeModel, setActiveModelState] = useState('');
  const [downloadProgress, setDownloadProgress] = useState({});
  const [isDownloading, setIsDownloading] = useState(new Set());
  const abortRefs = useRef({});
  const speedRefs = useRef({});

  const fetchHardware = useCallback(async () => {
    try {
      const r = await fetch(`${API}/system/hardware`);
      const data = await r.json();
      setHardware(data);
      setHardwareLoaded(true);
    } catch {
      setHardwareLoaded(true); // failed but no longer loading — show incompatible rather than skeleton forever
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

  const downloadModel = useCallback(async (name, onComplete, onStorageExceeded) => {
    setIsDownloading(prev => new Set(prev).add(name));
    setDownloadProgress(prev => ({ ...prev, [name]: { status: 'Preparing...', percent: 0 } }));

    const controller = new AbortController();
    abortRefs.current[name] = controller;
    speedRefs.current[name] = { lastBytes: -1, lastTime: Date.now(), samples: [] };

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

            if (chunk.error) {
              setDownloadProgress(prev => ({
                ...prev,
                [name]: { status: `Error: ${chunk.error}`, percent: 0, isError: true },
              }));
              return;
            }

            let percent = 0;
            let bytesDown = 0;
            let bytesTotal = 0;
            let speedBps = 0;
            let eta = null;

            if (chunk.total && chunk.completed) {
              bytesDown = chunk.completed;
              bytesTotal = chunk.total;
              percent = Math.round((bytesDown / bytesTotal) * 100);

              const sp = speedRefs.current[name];
              if (sp) {
                // First chunk with bytes — check storage, anchor baseline
                if (sp.lastBytes === -1) {
                  const freeBytes = hardware.disk_free_gb * 1024 ** 3;
                  if (freeBytes > 0 && bytesTotal > freeBytes) {
                    controller.abort();
                    onStorageExceeded?.(name, bytesTotal / 1024 ** 3, hardware.disk_free_gb);
                    return;
                  }
                  sp.lastBytes = bytesDown;
                  sp.lastTime = Date.now();
                }

                const now = Date.now();
                const dt = (now - sp.lastTime) / 1000;
                const db = bytesDown - sp.lastBytes;

                if (dt >= 0.5 && db > 0) {
                  const sample = db / dt;
                  sp.samples.push(sample);
                  if (sp.samples.length > 5) sp.samples.shift();
                  speedBps = sp.samples.reduce((a, b) => a + b, 0) / sp.samples.length;
                  sp.lastBytes = bytesDown;
                  sp.lastTime = now;

                  const remaining = bytesTotal - bytesDown;
                  eta = speedBps > 0 ? Math.round(remaining / speedBps) : null;
                } else if (sp.samples.length > 0) {
                  speedBps = sp.samples.reduce((a, b) => a + b, 0) / sp.samples.length;
                  const remaining = bytesTotal - bytesDown;
                  eta = speedBps > 0 ? Math.round(remaining / speedBps) : null;
                }
              }
            }

            setDownloadProgress(prev => ({
              ...prev,
              [name]: {
                status: chunk.status || 'Downloading...',
                percent,
                bytesDown,
                bytesTotal,
                speedBps,
                eta,
              },
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
      onComplete?.();
    } catch (err) {
      if (err.name === 'AbortError') {
        // Delete partial file from Ollama cache so storage isn't wasted
        try {
          await fetch(`${API}/models/${encodeURIComponent(name)}`, { method: 'DELETE' });
        } catch {
          // best-effort — ignore if Ollama unreachable
        }
        setDownloadProgress(prev => {
          const next = { ...prev };
          delete next[name];
          return next;
        });
      } else {
        setDownloadProgress(prev => ({ ...prev, [name]: { status: 'Error', percent: 0 } }));
      }
    } finally {
      delete abortRefs.current[name];
      delete speedRefs.current[name];
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
      setActiveModelState(prev => (prev === name ? '' : prev));
    } catch {
      // ignore
    }
  }, [fetchInstalled]);

  const cpuOnly = hardware.vram_gb === 0;

  const models = CURATED_MODELS.map(m => ({
    ...m,
    compatibility: hardwareLoaded ? getCompatibility(m, hardware) : 'loading',
    installed: installedModels.includes(m.name),
    active: m.name === activeModel,
    downloading: isDownloading.has(m.name),
    progress: downloadProgress[m.name] || null,
  }));

  const extraInstalled = installedModels.filter(name =>
    !curatedNames.has(name) && !/embed|rerank/i.test(name)
  );

  const cancelDownload = useCallback((name) => {
    abortRefs.current[name]?.abort();
  }, []);

  return {
    hardware,
    hardwareLoaded,
    cpuOnly,
    models,
    installedModels,
    extraInstalled,
    activeModel,
    downloadProgress,
    isDownloading,
    setActiveModel,
    downloadModel,
    cancelDownload,
    deleteModel,
    refresh,
  };
}
