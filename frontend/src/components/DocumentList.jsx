import { useState } from 'react';
import { FileText, Clock, CheckCircle, AlertCircle, Loader, Trash2, Check, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.05
    }
  }
};

const itemVariants = {
  hidden: { opacity: 0, x: -20 },
  visible: { 
    opacity: 1, 
    x: 0,
    transition: { type: "spring", stiffness: 400, damping: 30 }
  },
  exit: {
    opacity: 0,
    x: -20,
    transition: { duration: 0.2 }
  }
};

export default function DocumentList({ documents, selectedId, onSelect, onDelete }) {
  const [deletingId, setDeletingId] = useState(null);

  if (documents.length === 0) {
    return (
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="dossier-panel p-8 text-center text-gray-500 relative z-10 overflow-hidden"
      >
        <FileText className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p className="uppercase tracking-widest font-bold">No documents indexed.</p>
      </motion.div>
    );
  }

  return (
    <div className="dossier-panel p-6 relative z-10">
      <div className="flex justify-between items-center mb-6 border-b border-[var(--color-border)] pb-4">
        <h2 className="text-2xl font-serif uppercase tracking-widest text-white flex items-center space-x-3">
          <FileText className="w-6 h-6 text-[var(--color-accent)]" />
          <span>Knowledge Base</span>
        </h2>
        <span className="text-xs font-mono uppercase tracking-widest text-gray-400 border border-[var(--color-border)] px-2.5 py-1 bg-black">
          {documents.length} {documents.length === 1 ? 'Doc' : 'Docs'}
        </span>
      </div>
      
      <motion.div 
        className="space-y-4"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        <AnimatePresence>
          {documents.map((doc) => {
            const isSelected = doc.id === selectedId;
            const isProcessing = doc.status === 'processing';
            const isDone = doc.status === 'done';
            const isError = doc.status === 'error';
            
            return (
              <motion.div
                variants={itemVariants}
                initial="hidden"
                animate="visible"
                exit="exit"
                key={doc.id}
                onClick={() => onSelect(doc.id)}
                className={`w-full text-left p-4 rounded-none transition-all duration-200 border-l-4 relative overflow-hidden cursor-pointer ${
                  isSelected 
                    ? 'bg-[var(--color-surface-hover)] border-l-[var(--color-accent)] border-y border-y-[var(--color-border)] border-r border-r-[var(--color-border)] shadow-[4px_4px_0px_0px_var(--color-accent)]' 
                    : 'bg-black border-[var(--color-border)] hover:bg-[var(--color-surface)]'
                }`}
              >
                <div className="flex justify-between items-start relative z-10 gap-3">
                  <div className="flex-1 min-w-0 pr-2">
                    <h3 className={`font-bold truncate uppercase tracking-wider ${isSelected ? 'text-[var(--color-accent)]' : 'text-gray-200'}`} title={doc.filename}>
                      {doc.filename}
                    </h3>
                    <div className="flex items-center space-x-4 mt-3 text-xs font-mono text-gray-500 uppercase tracking-widest">
                      <span className="flex items-center space-x-2">
                        <Clock className="w-3 h-3" />
                        <span>{new Intl.DateTimeFormat('en-IN', {
                          timeZone: 'Asia/Kolkata',
                          year: 'numeric',
                          month: 'short',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit'
                        }).format(new Date(doc.created_at))}</span>
                      </span>
                      {doc.page_count > 0 && <span className="border-l border-[var(--color-border)] pl-4">{doc.page_count} PGs</span>}
                    </div>
                  </div>
                  
                  <div className="flex items-center space-x-2 shrink-0 mt-0.5">
                    {isProcessing && (
                      <span className="flex items-center space-x-1.5 text-yellow-500 border border-yellow-500/30 px-2 py-1 text-[10px] font-bold uppercase tracking-wider bg-yellow-500/10">
                        <Loader className="w-3 h-3 animate-spin" />
                        <span>Processing</span>
                      </span>
                    )}
                    {isDone && (
                      <span className="flex items-center space-x-1.5 text-emerald-500 border border-emerald-500/30 px-2 py-1 text-[10px] font-bold uppercase tracking-wider bg-emerald-500/10">
                        <CheckCircle className="w-3 h-3" />
                        <span>Ready</span>
                      </span>
                    )}
                    {isError && (
                      <span className="flex items-center space-x-1.5 text-red-500 border border-red-500/30 px-2 py-1 text-[10px] font-bold uppercase tracking-wider bg-red-500/10" title={doc.error_message}>
                        <AlertCircle className="w-3 h-3" />
                        <span>Error</span>
                      </span>
                    )}

                    {deletingId === doc.id ? (
                      <div 
                        className="flex items-center space-x-1.5 bg-red-950/80 border border-red-500/60 px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-red-300"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <span>Remove?</span>
                        <button
                          type="button"
                          title="Confirm removal"
                          onClick={(e) => {
                            e.stopPropagation();
                            onDelete && onDelete(doc.id, doc.filename);
                            setDeletingId(null);
                          }}
                          className="text-red-400 hover:text-white p-0.5 ml-1 transition-colors"
                        >
                          <Check className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          title="Cancel"
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeletingId(null);
                          }}
                          className="text-gray-400 hover:text-white p-0.5 transition-colors"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        title="Remove document from knowledge base"
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeletingId(doc.id);
                        }}
                        className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-red-500/10 border border-transparent hover:border-red-500/30 transition-all opacity-60 hover:opacity-100"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}
