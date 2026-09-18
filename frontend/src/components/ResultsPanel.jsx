function lastTable(statements) {
  for (let i = statements.length - 1; i >= 0; i--) {
    if (statements[i].columns) return statements[i]
  }
  return null
}

export default function ResultsPanel({ result }) {
  const statements = result && result.statements ? result.statements : []
  const table = statements.length > 0 ? lastTable(statements) : (result && result.columns ? result : null)
  const messages = statements.filter((s) => s.message).map((s) => s.message)
  const isTable = !result?.error && table
  return (
    <section className="panel results">
      <h2>Resultados</h2>
      <div className="panel-body flush">
        {!result ? (
          <p className="muted" style={{ padding: '6px 8px' }}>Ejecuta una consulta.</p>
        ) : result.error ? (
          <div className="error">{result.error}</div>
        ) : (
          <>
            {messages.length > 0 && messages.map((m, i) => <p key={i} className="ok">{m}</p>)}
            {!isTable && messages.length > 0 ? null : !isTable ? (
              <p className="muted" style={{ padding: '6px 8px' }}>Sin filas.</p>
            ) : (
              <table className="grid-table">
                <thead>
                  <tr>
                    <th className="rownum" />
                    {table.columns.map((c) => (
                      <th key={c}>{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {table.rows.map((r, i) => (
                    <tr key={i}>
                      <td className="rownum">{i + 1}</td>
                      {table.columns.map((c) => (
                        <td key={c}>{String(r[c])}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
      {isTable && (
        <div className="status">
          {table.rows.length} filas · {result.elapsedMs} ms
        </div>
      )}
    </section>
  )
}
