import { useMemo, useState } from "react";
import { SOURCE_TYPE_LABEL } from "../constants";

export function SourcesPanel({ sources }) {
  const [manufacturerFilter, setManufacturerFilter] = useState("all");

  const manufacturers = useMemo(
    () => Array.from(new Set((sources || []).map((item) => item.manufacturer).filter(Boolean))),
    [sources]
  );

  if (!sources || sources.length === 0) {
    return (
      <section className="panel" aria-label="Sources">
        <h2>Sources</h2>
        <p className="muted">No sources were used for this research question.</p>
      </section>
    );
  }

  const filtered = sources.filter(
    (item) => manufacturerFilter === "all" || item.manufacturer === manufacturerFilter
  );

  return (
    <section className="panel" aria-label="Sources">
      <div className="panel__header">
        <h2>Sources</h2>
        <select value={manufacturerFilter} onChange={(e) => setManufacturerFilter(e.target.value)} aria-label="Filter sources by manufacturer">
          <option value="all">All manufacturers</option>
          {manufacturers.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>
      <ol className="sources-list">
        {filtered.map((source, index) => (
          <li key={source.id} className="source-item">
            <span className="source-item__index">{String(index + 1).padStart(2, "0")}</span>
            <div>
              <p className="source-item__manufacturer">{source.manufacturer}</p>
              <p>
                {source.url ? (
                  <a href={source.url} target="_blank" rel="noreferrer">
                    {source.title}
                  </a>
                ) : (
                  source.title
                )}
              </p>
              <p className="muted">
                {SOURCE_TYPE_LABEL[source.type] || source.type}
                {source.date ? ` · ${source.date.slice(0, 4)}` : ""}
                {source.page ? ` · Page ${source.page}` : ""}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
