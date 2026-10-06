import { useRef, useState } from "react";

export default function DropZone({ onFile, busy, error }) {
  const input = useRef(null);
  const [over, setOver] = useState(false);

  const pick = (files) => {
    const file = files?.[0];
    if (file) onFile(file);
  };

  return (
    <div
      className={`dropzone${over ? " over" : ""}`}
      onClick={() => !busy && input.current.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (!busy) pick(e.dataTransfer.files);
      }}
    >
      <input
        ref={input}
        type="file"
        accept=".dxf"
        hidden
        onChange={(e) => {
          pick(e.target.files);
          e.target.value = "";
        }}
      />
      <div className="dropzone-icon" aria-hidden>
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.25">
          <path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z" />
          <path d="M14 3v5h5M12 18v-6M9 15l3-3 3 3" />
        </svg>
      </div>
      <h1>{busy ? "Reading drawing…" : "Open a DXF drawing"}</h1>
      <p className="muted">Drop a file here or click to browse</p>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
