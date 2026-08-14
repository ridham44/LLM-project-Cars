import { Fragment, useState } from "react";

export function ComparisonTable({ comparison, evidence }) {
  const [expandedRow, setExpandedRow] = useState(null);

  if (!comparison || !comparison.rows?.length) return null;

  const evidenceById = new Map((evidence || []).map((item) => [item.id, item]));

  return (
    <section className="panel comparison-table" aria-label="Comparison table">
      <h2>Comparison</h2>
      <div className="comparison-table__scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Category</th>
              {comparison.entities.map((entity) => (
                <th scope="col" key={entity}>
                  {entity}
                </th>
              ))}
              <th scope="col">Evidence</th>
            </tr>
          </thead>
          <tbody>
            {comparison.rows.map((row) => {
              const isExpanded = expandedRow === row.category;
              const rowEvidence = (row.evidenceIds || []).map((id) => evidenceById.get(id)).filter(Boolean);

              return (
                <Fragment key={row.category}>
                  <tr>
                    <th scope="row">{row.category}</th>
                    {row.values.map((value, index) => (
                      <td key={index}>{value}</td>
                    ))}
                    <td>
                      <button
                        type="button"
                        className="evidence-indicator"
                        aria-expanded={isExpanded}
                        onClick={() => setExpandedRow(isExpanded ? null : row.category)}
                        disabled={rowEvidence.length === 0}
                      >
                        ✓ {rowEvidence.length}
                      </button>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr className="comparison-table__detail-row">
                      <td colSpan={row.values.length + 2}>
                        <ul>
                          {rowEvidence.map((item) => (
                            <li key={item.id}>
                              <strong>{item.documentTitle}</strong>
                              {item.page ? ` · Page ${item.page}` : ""} — “{item.excerpt}” (score {item.score.toFixed(2)})
                            </li>
                          ))}
                        </ul>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
