import { useState, useEffect } from 'react';
import UploadSection from './components/UploadSection';
import DocumentList from './components/DocumentList';
import DocumentDetails from './components/DocumentDetails';
import { Database, Zap, FileSearch, X, Activity } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { API_BASE_URL } from './api';
import './index.css';

function SystemStatusModal({ isOpen, onClose }) {
  const [statusData, setStatusData] = useState(null);

  useEffect(() => {
    if (isOpen) {
      fetch(`${API_BASE_URL}/api/status`)
        .then(res => res.json())
        .then(data => setStatusData(data))
        .catch(err => console.error(err));
    }
  }, [isOpen]);

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-4"
        >
          <motion.div 
            initial={{ scale: 0.95, y: 10 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.95, y: 10 }}
            className="dossier-panel p-8 w-full max-w-md relative"
          >
            <button 
              onClick={onClose}
              className="absolute top-4 right-4 text-gray-500 hover:text-[var(--color-accent)] transition-colors"
            >
              <X className="w-6 h-6" />
            </button>
            
            <div className="flex items-center space-x-4 mb-8 border-b border-[var(--color-border)] pb-4">
              <Activity className="w-8 h-8 text-[var(--color-accent)]" />
              <h2 className="text-2xl font-serif text-white uppercase tracking-widest">System Status</h2>
            </div>

            {statusData ? (
              <div className="space-y-4 font-mono text-sm">
                <div className="flex justify-between items-center border border-[var(--color-border)] p-4 bg-black">
                  <span className="text-gray-400 uppercase tracking-wider">Backend API</span>
                  <span className="text-emerald-500 font-bold flex items-center gap-2">
                    <span className="w-2 h-2 rounded-none bg-emerald-500 animate-pulse"></span>
                    ONLINE
                  </span>
                </div>
                <div className="flex justify-between items-center border border-[var(--color-border)] p-4 bg-black">
                  <span className="text-gray-400 uppercase tracking-wider">Documents Indexed</span>
                  <span className="text-white font-bold">{statusData.documents}</span>
                </div>
                <div className="flex justify-between items-center border border-[var(--color-border)] p-4 bg-black">
                  <span className="text-gray-400 uppercase tracking-wider">Extracted Facts</span>
                  <span className="text-[var(--color-accent)] font-bold">{statusData.facts}</span>
                </div>
                <div className="flex justify-between items-center border border-[var(--color-border)] p-4 bg-black">
                  <span className="text-gray-400 uppercase tracking-wider">Vector Embeddings</span>
                  <span className="text-white font-bold">{statusData.chroma_embeddings}</span>
                </div>
              </div>
            ) : (
              <div className="flex justify-center items-center py-12">
                <div className="w-10 h-10 border-4 border-[var(--color-border)] border-t-[var(--color-accent)] animate-spin"></div>
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function App() {
  const [documents, setDocuments] = useState([]);
  const [selectedDocId, setSelectedDocId] = useState(null);
  const [isStatusOpen, setIsStatusOpen] = useState(false);

  const fetchDocuments = async () => {
    try {
      const res = await fetch('http://127.0.0.1:8000/api/documents');
      if (res.ok) {
        const data = await res.json();
        setDocuments(data);
      }
    } catch (err) {
      console.error("Failed to fetch documents:", err);
    }
  };

  useEffect(() => {
    fetchDocuments();
    const interval = setInterval(fetchDocuments, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleUploadComplete = (docId) => {
    fetchDocuments();
    setSelectedDocId(docId);
  };

  const handleDeleteDocument = async (docId, filename) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/documents/${docId}`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        throw new Error('Failed to delete document');
      }
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
      if (selectedDocId === docId) {
        setSelectedDocId(null);
      }
    } catch (err) {
      console.error("Failed to delete document:", err);
    }
  };

  const scrollToKnowledgeBase = () => {
    document.getElementById('knowledge-base')?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className="min-h-screen text-[#f5f5f5] relative font-mono selection:bg-[var(--color-accent)] selection:text-black">
      <div className="crosshair-bg" />
      
      {/* Navbar */}
      <nav className="border-b border-[var(--color-border)] bg-[var(--color-bg-black)] sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-20">
            <motion.div 
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              className="flex items-center space-x-4"
            >
              <div className="bg-[var(--color-accent)] p-3 shadow-[4px_4px_0px_0px_rgba(255,255,255,0.1)]">
                <Database className="w-6 h-6 text-black" />
              </div>
              <div>
                <h1 className="text-3xl font-serif text-white tracking-widest uppercase">Super Join</h1>
                <p className="text-xs text-[var(--color-accent)] tracking-[0.2em] uppercase font-bold mt-1">Semantic Reconciliation</p>
              </div>
            </motion.div>
            
            <motion.div 
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              className="hidden md:flex items-center space-x-6 text-sm font-bold tracking-wider text-gray-400 uppercase"
            >
              <div 
                className="flex items-center space-x-2 hover:text-white transition-colors cursor-pointer border border-transparent hover:border-[var(--color-border)] px-4 py-2"
                onClick={scrollToKnowledgeBase}
              >
                <FileSearch className="w-4 h-4" />
                <span>Knowledge Base</span>
              </div>
              <div 
                className="flex items-center space-x-2 hover:text-white transition-colors cursor-pointer border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:shadow-[2px_2px_0px_0px_var(--color-accent)]"
                onClick={() => setIsStatusOpen(true)}
              >
                <Zap className="w-4 h-4 text-[var(--color-accent)]" />
                <span>Status</span>
              </div>
            </motion.div>
          </div>
        </div>
      </nav>

      {/* Main Layout */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 relative z-10">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
          
          {/* Left Column (Upload + List) */}
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1, type: 'spring', stiffness: 100 }}
            className="lg:col-span-4 space-y-8"
          >
            <UploadSection onUploadComplete={handleUploadComplete} />
            <div id="knowledge-base">
              <DocumentList 
                documents={documents} 
                selectedId={selectedDocId} 
                onSelect={setSelectedDocId} 
                onDelete={handleDeleteDocument}
              />
            </div>
          </motion.div>
          
          {/* Right Column (Details + Analysis) */}
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, type: 'spring', stiffness: 100 }}
            className="lg:col-span-8"
          >
            {selectedDocId ? (
              <DocumentDetails 
                documentId={selectedDocId} 
                onClose={() => setSelectedDocId(null)} 
              />
            ) : (
              <div className="dossier-panel h-full min-h-[600px] flex flex-col items-center justify-center p-12 text-center bg-[var(--color-bg-black)]">
                <Database className="w-24 h-24 text-[var(--color-border)] mb-8" />
                <h2 className="text-3xl font-serif text-white uppercase tracking-widest mb-4">No Dossier Selected</h2>
                <p className="text-gray-500 max-w-md mx-auto text-sm leading-relaxed uppercase tracking-wider">
                  Select a record from the database to initiate cross-document analysis.
                </p>
              </div>
            )}
          </motion.div>
          
        </div>
      </main>

      <SystemStatusModal 
        isOpen={isStatusOpen} 
        onClose={() => setIsStatusOpen(false)} 
      />
    </div>
  );
}

export default App;
