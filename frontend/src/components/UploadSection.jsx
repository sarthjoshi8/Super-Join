import { useState, useRef } from 'react';
import { UploadCloud, FileType, CheckCircle, AlertCircle } from 'lucide-react';
import { API_BASE_URL } from '../api';

export default function UploadSection({ onUploadComplete }) {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  const handleFileChange = async (e) => {
    const files = e.target.files;
    if (files.length > 0) {
      await uploadFile(files[0]);
    }
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    setIsDragging(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (file.type === 'application/pdf') {
        await uploadFile(file);
      } else {
        setError('PLEASE UPLOAD A PDF FILE.');
      }
    }
  };

  const uploadFile = async (file) => {
    setIsUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`${API_BASE_URL}/api/documents/upload`, {
        method: 'POST',
        body: formData,
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || 'Upload failed');
      }

      if (onUploadComplete) {
        onUploadComplete(data.document_id);
      }
    } catch (err) {
      setError(err.message.toUpperCase());
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  return (
    <div className="dossier-panel p-8">
      <div
        className={`border-2 border-dashed p-10 text-center transition-all duration-300 ${isDragging ? 'border-[var(--color-accent)] bg-[var(--color-accent)]/10' : 'border-[var(--color-border)] hover:border-gray-500'
          }`}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
      >
        <UploadCloud className={`w-12 h-12 mx-auto mb-4 ${isDragging ? 'text-[var(--color-accent)]' : 'text-gray-600'}`} />
        <h3 className="text-2xl font-serif uppercase tracking-widest text-white mb-2">Initialize Upload</h3>
        <p className="text-gray-500 mb-8 max-w-sm mx-auto text-sm tracking-wider uppercase font-mono">
          Drag and drop PDF report to extract and map facts.
        </p>

        <input
          type="file"
          accept="application/pdf"
          className="hidden"
          ref={fileInputRef}
          onChange={handleFileChange}
        />

        <button
          className="btn-primary flex items-center justify-center mx-auto space-x-3 w-full max-w-xs"
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
        >
          {isUploading ? (
            <>
              <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin"></div>
              <span>Transmitting...</span>
            </>
          ) : (
            <>
              <FileType className="w-5 h-5" />
              <span>Select PDF</span>
            </>
          )}
        </button>

        {error && (
          <div className="mt-6 p-4 bg-red-950/50 border border-red-500 text-red-500 flex items-center justify-center space-x-3 text-sm font-bold tracking-wider">
            <AlertCircle className="w-5 h-5" />
            <span>{error}</span>
          </div>
        )}
      </div>
    </div>
  );
}
