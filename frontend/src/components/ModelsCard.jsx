import { useState } from "react";
import { humanizeModelVar } from "../constants";

export function ModelsCard({ models }) {
  const [openVar, setOpenVar] = useState(null);
  const entries = Object.entries(models);

  return (
    <section className="sidebar-card" aria-label="Local models">
      <h2>Local Models</h2>
      {entries.length === 0 ? (
        <p className="muted">Model status unavailable.</p>
      ) : (
        <ul className="sidebar-card__list">
          {entries.map(([varName, model]) => {
            const isOpen = openVar === varName;
            const known = model.available !== null && model.available !== undefined;
            return (
              <li key={varName}>
                <button
                  type="button"
                  className="sidebar-card__item-toggle"
                  aria-expanded={isOpen}
                  onClick={() => setOpenVar(isOpen ? null : varName)}
                >
                  <span
                    className={`status-dot ${known ? (model.available ? "status-dot--success" : "status-dot--danger") : "status-dot--neutral"}`}
                    aria-hidden="true"
                  />
                  <span className="sidebar-card__item-label">{humanizeModelVar(varName)}</span>
                </button>
                {isOpen && (
                  <div className="sidebar-card__item-detail">
                    <div>{model.name}</div>
                    <div className="muted">
                      {known ? (model.available ? "Ready" : "Not pulled in Ollama") : "Unknown - Ollama unreachable"}
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
