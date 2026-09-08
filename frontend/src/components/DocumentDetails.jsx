import { useState, useEffect } from 'react';
import { Activity, Check, GitMerge, AlertTriangle, Info, Play, Loader, RefreshCw, XCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { API_BASE_URL } from '../api';

export default function DocumentDetails({ documentId, onClose }) {
  const [doc, setDoc] = useState(null);
  const [relationships, setRelationships] = useState([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState(null); // { stage, done, total }

  const fetchDetails = async () => {
    try {
      setLoading(true);
      const [docRes, relRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/documents/${documentId}`),
        fetch(`${API_BASE_URL}/api/documents/${documentId}/relationships`)
      ]);

      if (!docRes.ok) throw new Error('Failed to load document');

      setDoc(await docRes.json());
      setRelationships(await relRes.json());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (documentId) {
      fetchDetails();
    }
  }, [documentId]);

  // Poll /progress while the doc is still being ingested
  useEffect(() => {
    if (!doc || doc.status !== 'processing') {
      setProgress(null);
      return;
    }
    const id = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/documents/${documentId}/progress`);
        const data = await res.json();
        setProgress(data);
        // Also refresh the document itself to catch status change
        const docRes = await fetch(`${API_BASE_URL}/api/documents/${documentId}`);
        if (docRes.ok) {
          const updated = await docRes.json();
          setDoc(updated);
          if (updated.status !== 'processing') {
            clearInterval(id);
            setProgress(null);
          }
        }
      } catch (_) { }
    }, 2000);
    return () => clearInterval(id);
  }, [doc?.status, documentId]);

  const handleAnalyze = async () => {
    setIsAnalyzing(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/documents/${documentId}/analyze`, {
        method: 'POST'
      });
      if (!res.ok) throw new Error('Analysis failed to start');

      // Poll relationships + backend analysis status every 2.5s; stop when backend finishes
      let elapsed = 0;
      const MAX_WAIT_MS = 300000; // 5 min ceiling

      const interval = setInterval(async () => {
        elapsed += 2500;
        try {
          const [relRes, statusRes] = await Promise.all([
            fetch(`${API_BASE_URL}/api/documents/${documentId}/relationships`),
            fetch(`${API_BASE_URL}/api/documents/${documentId}/analysis_status`)
          ]);
          if (relRes.ok) {
            const newRels = await relRes.json();
            setRelationships(newRels);
          }

          if (statusRes.ok) {
            const statusData = await statusRes.json();
            // Give backend at least 2.5s to register analysis start
            if (elapsed >= 2500 && !statusData.is_analyzing) {
              clearInterval(interval);
              setIsAnalyzing(false);
            }
          } else if (elapsed >= MAX_WAIT_MS) {
            clearInterval(interval);
            setIsAnalyzing(false);
          }
        } catch (_) { }
      }, 2500);

    } catch (err) {
      alert(err.message);
      setIsAnalyzing(false);
    }
  };

  if (loading) {
    return (
      <div className="dossier-panel p-8 flex flex-col items-center justify-center min-h-[400px] gap-4">
        <Loader className="w-8 h-8 animate-spin text-[var(--color-accent)]" />
        <span className="text-xs font-mono text-gray-500 uppercase tracking-widest">Loading document…</span>
      </div>
    );
  }

  if (error || !doc) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="dossier-panel p-8 text-center text-red-500 relative z-10 font-mono font-bold tracking-widest uppercase"
      >
        <XCircle className="w-12 h-12 mx-auto mb-3 opacity-50" />
        <p>{error || "Document not found"}</p>
        <button onClick={onClose} className="mt-6 btn-secondary">Close Dossier</button>
      </motion.div>
    );
  }

  const corroborations = relationships.filter(r => r.relationship_type === 'CORROBORATES');
  const contradictions = relationships.filter(r => r.relationship_type === 'CONTRADICTS');
  const contextuallyDiffers = relationships.filter(r => r.relationship_type === 'CONTEXTUALLY_DIFFERS');

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.1 } }
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      transition={{ type: "spring", stiffness: 400, damping: 30 }}
      className="dossier-panel p-0 flex flex-col max-h-[80vh] relative z-10"
    >
      {/* Header */}
      <div className="p-6 border-b border-[var(--color-border)] bg-[var(--color-surface)] flex justify-between items-start md:items-center flex-col md:flex-row gap-4 sticky top-0 z-20">
        <div className="flex-1 min-w-0 pr-4">
          <h2 className="text-3xl font-serif text-white mb-2 uppercase tracking-widest break-words leading-tight" title={doc.filename}>{doc.filename}</h2>
          <div className="flex flex-wrap items-center gap-y-2 text-xs font-mono text-gray-500 uppercase tracking-widest font-bold mt-2">
            <span className="mr-6">Status: <span className={doc.status === 'processing' ? 'text-yellow-400 animate-pulse' : 'text-[var(--color-accent)]'}>{doc.status}</span></span>
            <span className="border-l border-[var(--color-border)] pl-6 mr-6">Pages: {doc.page_count}</span>
            <span className="border-l border-[var(--color-border)] pl-6">{new Intl.DateTimeFormat('en-IN', {
              timeZone: 'Asia/Kolkata',
              year: 'numeric',
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit'
            }).format(new Date(doc.created_at))}</span>
          </div>
          {/* Live progress bar during ingestion */}
          {doc.status === 'processing' && progress && progress.total > 0 && (
            <div className="mt-3">
              <div className="flex justify-between text-[10px] font-mono text-gray-500 uppercase mb-1">
                <span>{progress.stage === 'embedding' ? '⟳ Embedding facts…' : `⟳ Extracting chunk ${progress.done} / ${progress.total}`}</span>
                <span>{Math.round((progress.done / progress.total) * 100)}%</span>
              </div>
              <div className="h-1 bg-[var(--color-border)] w-full">
                <div
                  className="h-1 bg-[var(--color-accent)] transition-all duration-500"
                  style={{ width: `${Math.round((progress.done / progress.total) * 100)}%` }}
                />
              </div>
            </div>
          )}
          {doc.status === 'processing' && (!progress || progress.total === 0) && (
            <div className="mt-3 flex items-center gap-2 text-[10px] font-mono text-yellow-400 uppercase">
              <Loader className="w-3 h-3 animate-spin" />
              <span>Starting extraction…</span>
            </div>
          )}
        </div>

        <div className="flex space-x-4 shrink-0">
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={fetchDetails}
            className="p-3 bg-transparent border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-5 h-5 text-gray-300" />
          </motion.button>

          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleAnalyze}
            disabled={isAnalyzing || doc.status !== 'done'}
            className="btn-primary flex items-center space-x-3"
          >
            {isAnalyzing ? (
              <Loader className="w-5 h-5 animate-spin" />
            ) : (
              <Play className="w-5 h-5 fill-current" />
            )}
            <span>{isAnalyzing ? 'Analyzing...' : 'Analyze Connections'}</span>
          </motion.button>

          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={onClose}
            className="p-3 bg-transparent border border-[var(--color-border)] hover:bg-red-950/50 hover:border-red-500 hover:text-red-500 transition-colors"
            title="Close"
          >
            <XCircle className="w-5 h-5 text-gray-400" />
          </motion.button>
        </div>
      </div>

      {/* Scrollable Content */}
      <div className="p-8 overflow-y-auto custom-scrollbar bg-[var(--color-bg-black)]">

        <AnimatePresence mode="wait">
          {relationships.length === 0 ? (
            <motion.div
              key="empty"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              className="text-center py-20 border-2 border-dashed border-[var(--color-border)] m-4"
            >
              <Activity className="w-16 h-16 mx-auto mb-6 text-[var(--color-border)] opacity-50" />
              {isAnalyzing ? (
                <>
                  <h3 className="text-2xl font-serif text-yellow-400 uppercase tracking-widest mb-4 animate-pulse">Analyzing Connections…</h3>
                  <p className="text-gray-500 max-w-md mx-auto font-mono text-sm uppercase tracking-wider leading-relaxed">
                    Cross-checking facts against other documents. This may take 15–60 seconds.
                  </p>
                </>
              ) : (
                <>
                  <h3 className="text-2xl font-serif text-gray-400 uppercase tracking-widest mb-4">No Connections Mapped</h3>
                  <p className="text-gray-500 max-w-md mx-auto font-mono text-sm uppercase tracking-wider leading-relaxed">
                    Execute 'Analyze Connections' to cross-check extracted data points against the global intelligence matrix.
                  </p>
                </>
              )}
            </motion.div>
          ) : (
            <motion.div
              key="content"
              variants={containerVariants}
              initial="hidden"
              animate="visible"
              className="space-y-12"
            >
              {/* Corroborations */}
              {corroborations.length > 0 && (
                <section>
                  <h3 className="text-xl font-serif uppercase tracking-widest text-emerald-500 mb-6 flex items-center space-x-3 border-b border-[var(--color-border)] pb-2">
                    <Check className="w-6 h-6" />
                    <span>Verified Corroborations [{corroborations.length}]</span>
                  </h3>
                  <div className="space-y-6">
                    {corroborations.map(rel => (
                      <RelationshipCard key={rel.id} rel={rel} type="corroborate" />
                    ))}
                  </div>
                </section>
              )}

              {/* Contradictions */}
              {contradictions.length > 0 && (
                <section>
                  <h3 className="text-xl font-serif uppercase tracking-widest text-red-500 mb-6 flex items-center space-x-3 border-b border-[var(--color-border)] pb-2">
                    <AlertTriangle className="w-6 h-6" />
                    <span>Critical Contradictions [{contradictions.length}]</span>
                  </h3>
                  <div className="space-y-6">
                    {contradictions.map(rel => (
                      <RelationshipCard key={rel.id} rel={rel} type="contradict" />
                    ))}
                  </div>
                </section>
              )}

              {/* Contextually Differs */}
              {contextuallyDiffers.length > 0 && (
                <section>
                  <h3 className="text-xl font-serif uppercase tracking-widest text-yellow-500 mb-6 flex items-center space-x-3 border-b border-[var(--color-border)] pb-2">
                    <GitMerge className="w-6 h-6" />
                    <span>Contextual Divergences [{contextuallyDiffers.length}]</span>
                  </h3>
                  <div className="space-y-6">
                    {contextuallyDiffers.map(rel => (
                      <RelationshipCard key={rel.id} rel={rel} type="differ" />
                    ))}
                  </div>
                </section>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

function RelationshipCard({ rel, type }) {
  const factA = rel.fact_a || {};
  const factB = rel.fact_b || {};

  const typeStyles = {
    corroborate: "border-emerald-500/50 hover:border-emerald-500 hover:shadow-[4px_4px_0px_0px_rgba(16,185,129,0.3)]",
    contradict: "border-red-500/50 hover:border-red-500 hover:shadow-[4px_4px_0px_0px_rgba(239,68,68,0.3)]",
    differ: "border-yellow-500/50 hover:border-yellow-500 hover:shadow-[4px_4px_0px_0px_rgba(234,179,8,0.3)]"
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className={`bg-[var(--color-surface)] border-2 ${typeStyles[type]} transition-all duration-300 font-mono`}
    >
      <div className="flex flex-col md:flex-row p-6 gap-6">
        <div className="flex-1">
          <div className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-3 border-b border-[var(--color-border)] pb-1">Source Record</div>
          <p className="text-gray-300 font-bold mb-2 uppercase tracking-wide">{factA.subject} <span className="text-[var(--color-accent)] mx-2">&gt;&gt;</span> {factA.predicate}</p>
          <div className="flex justify-between items-end mt-4">
            <span className="text-xl font-bold text-white tracking-widest">{factA.value}</span>
            <span className="text-[10px] text-[var(--color-accent)] border border-[var(--color-accent)] px-2 py-1 uppercase font-bold">{factA.time_label || 'NO TIME METADATA'}</span>
          </div>
        </div>

        <div className="flex items-center justify-center border-l border-r border-[var(--color-border)] px-6">
          <GitMerge className="w-8 h-8 text-[var(--color-border-focus)] rotate-90 md:rotate-0" />
        </div>

        <div className="flex-1">
          <div className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-3 border-b border-[var(--color-border)] pb-1">Matched Record</div>
          <p className="text-gray-300 font-bold mb-2 uppercase tracking-wide">{factB.subject} <span className="text-[var(--color-accent)] mx-2">&gt;&gt;</span> {factB.predicate}</p>
          <div className="flex justify-between items-end mt-4">
            <span className="text-xl font-bold text-white tracking-widest">{factB.value}</span>
            <span className="text-[10px] text-[var(--color-accent)] border border-[var(--color-accent)] px-2 py-1 uppercase font-bold">{factB.time_label || 'NO TIME METADATA'}</span>
          </div>
        </div>
      </div>

      <div className="bg-black border-t border-[var(--color-border)] p-4 text-xs text-gray-400 flex items-start space-x-4">
        <div className="bg-[var(--color-accent)] text-black font-bold px-2 py-1 uppercase tracking-widest shrink-0">AI Logic</div>
        <p className="uppercase tracking-widest leading-relaxed mt-0.5">{rel.reason}</p>
      </div>
    </motion.div>
  );
}
