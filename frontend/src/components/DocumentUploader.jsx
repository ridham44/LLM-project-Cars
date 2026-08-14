import { useRef, useState } from "react";
import { ACCEPTED_DOCUMENT_TYPES, isAcceptedDocument, uploadDocument } from "../services/documents";

// Reports only states we can actually observe from the current backend
// contract (uploading -> indexed/error). The brief's fuller pipeline
// (parsing -> chunking -> embedding -> indexed) will populate here once
// POST /documents/upload returns per-stage status or a pollable job id --
// faking those intermediate stages today would violate "don't fake progress".
export function DocumentUploader({ variant = "default", label = "+ Add Document" }) {
  const inputRef = useRef(null);
  const [entries, setEntries] = useState([]);

  async function handleFiles(fileList) {
    const files = Array.from(fileList);
    for (const file of files) {
      if (!isAcceptedDocument(file.name)) {
        setEntries((prev) => [
          { id: `${file.name}-${prev.length}`, name: file.name, stage: "rejected", detail: "Unsupported file type" },
          ...prev,
        ]);
        continue;
      }

      const entryId = `${file.name}-${Date.now()}`;
      setEntries((prev) => [{ id: entryId, name: file.name, stage: "uploading" }, ...prev]);

      try {
        await uploadDocument(file);
        setEntries((prev) =>
          prev.map((entry) => (entry.id === entryId ? { ...entry, stage: "indexed" } : entry))
        );
      } catch (err) {
        setEntries((prev) =>
          prev.map((entry) => (entry.id === entryId ? { ...entry, stage: "error", detail: err.detail || err.message } : entry))
        );
      }
    }
  }

  return (
    <div className={`document-uploader document-uploader--${variant}`}>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPTED_DOCUMENT_TYPES.join(",")}
        className="visually-hidden"
        onChange={(event) => {
          if (event.target.files?.length) handleFiles(event.target.files);
          event.target.value = "";
        }}
      />
      <button
        type="button"
        className={variant === "compact" ? "ghost-button ghost-button--compact" : "ghost-button"}
        onClick={() => inputRef.current?.click()}
      >
        {label}
      </button>

      {entries.length > 0 && (
        <ul className="document-uploader__list" aria-live="polite">
          {entries.map((entry) => (
            <li key={entry.id} className={`document-uploader__entry document-uploader__entry--${entry.stage}`}>
              <span>{entry.name}</span>
              <span className="document-uploader__stage">
                {entry.stage === "uploading" && "Uploading…"}
                {entry.stage === "indexed" && "Indexed"}
                {entry.stage === "error" && (entry.detail || "Failed")}
                {entry.stage === "rejected" && entry.detail}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
