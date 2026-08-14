import { SystemHealthCard } from "./SystemHealthCard";
import { ModelsCard } from "./ModelsCard";
import { KnowledgeBaseCard } from "./KnowledgeBaseCard";

// Document upload deliberately lives only in the composer toolbar
// (DocumentUploader, "compact" variant) - having it here as well put two
// upload controls on screen for one capability.

export function LeftSidebar({ systemStatus, mobileOpen, onClose }) {
  return (
    <aside className={`side-panel side-panel--left ${mobileOpen ? "side-panel--open" : ""}`} aria-label="Research info">
      <div className="side-panel__mobile-header mobile-only">
        <span>Research Info</span>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close panel">
          ✕
        </button>
      </div>
      <SystemHealthCard systemStatus={systemStatus} />
      <ModelsCard models={systemStatus.models} />
      <KnowledgeBaseCard knowledgeBase={systemStatus.knowledgeBase} />
    </aside>
  );
}
