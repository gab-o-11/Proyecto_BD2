export default function ResultsPanel({ result }) {
  const isTable = result && !result.error && !result.message
  return (
    <section className="panel results">
      <h2>Resultados</h2>
      <div className="panel-body flush">
        {!result ? (
          <p className="muted" style={{ padding: '6px 8px' }}>Ejecuta una consulta.</p>
        ) : result.error ? (
          <div className="error">{result.error}</div>
        ) : result.message ? (
          <p className="ok">{result.message}</p>
        ) : (
          <table className="grid-table">
            <thead>
              <tr>
                <th className="rownum" />
                {result.columns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((r, i) => (
                <tr key={i}>
                  <td className="rownum">{i + 1}</td>
                  {result.columns.map((c) => (
                    <td key={c}>{String(r[c])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {isTable && (
        <div className="status">
          {result.rows.length} filas · {result.elapsedMs} ms
        </div>
      )}
    </section>
  )
}
