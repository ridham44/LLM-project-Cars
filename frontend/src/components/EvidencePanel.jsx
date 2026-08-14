import { useMemo, useState } from "react";
import { SOURCE_TYPE_LABEL } from "../constants";

export function EvidencePanel({ evidence }) {
  const [manufacturerFilter, setManufacturerFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [expandedId, setExpandedId] = useState(null);

  const manufacturers = useMemo(
    () => Array.from(new Set((evidence || []).map((item) => item.manufacturer).filter(Boolean))),
    [evidence]
  );
  const types = useMemo(
    () => Array.from(new Set((evidence || []).map((item) => item.sourceType).filter(Boolean))),
    [evidence]
  );

  if (!evidence || evidence.length === 0) {
    return (
      <section className="panel" aria-label="Evidence">
        <h2>Evidence</h2>
        <p className="muted">Insufficient evidence in the local knowledge base.</p>
      </section>
    );
  }

  const filtered = evidence.filter(
    (item) =>
      (manufacturerFilter === "all" || item.manufacturer === manufacturerFilter) &&
      (typeFilter === "all" || item.sourceType === typeFilter)
  );

  return (
    <section className="panel" aria-label="Evidence">
      <div className="panel__header">
        <h2>Evidence</h2>
        <div className="panel__filters">
          <select value={manufacturerFilter} onChange={(e) => setManufacturerFilter(e.target.value)} aria-label="Filter by manufacturer">
            <option value="all">All manufacturers</option>
            {manufacturers.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} aria-label="Filter by source type">
            <option value="all">All source types</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {SOURCE_TYPE_LABEL[t] || t}
              </option>
            ))}
          </select>
        </div>
      </div>

      <ul className="evidence-list">
        {filtered.map((item) => {
          const isExpanded = expandedId === item.id;
          return (
            <li key={item.id} className="evidence-card">
              <button
                type="button"
                className="evidence-card__toggle"
                aria-expanded={isExpanded}
                onClick={() => setExpandedId(isExpanded ? null : item.id)}
              >
                <span className="badge badge--neutral">{SOURCE_TYPE_LABEL[item.sourceType] || item.sourceType}</span>
                <span className="evidence-card__title">{item.documentTitle}</span>
                <span className="evidence-card__score">{item.score.toFixed(2)}</span>
              </button>
              {isExpanded && (
                <div className="evidence-card__body">
                  <p>“{item.excerpt}”</p>
                  <dl className="evidence-card__meta">
                    {item.manufacturer && (
                      <div>
                        <dt>Manufacturer</dt>
                        <dd>{item.manufacturer}</dd>
                      </div>
                    )}
                    {item.page && (
                      <div>
                        <dt>Page</dt>
                        <dd>{item.page}</dd>
                      </div>
                    )}
                    <div>
                      <dt>Evidence Score</dt>
                      <dd>{item.score.toFixed(2)}</dd>
                    </div>
                  </dl>
                  {item.url && (
                    <a href={item.url} target="_blank" rel="noreferrer">
                      View source
                    </a>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
