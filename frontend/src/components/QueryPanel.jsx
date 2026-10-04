import { useState } from 'react'

const EJEMPLOS = [
  "SELECT * FROM clientes WHERE id = 7;",
  "SELECT id, monto FROM ventas WHERE monto > 500;",
  "SELECT categoria FROM ventas GROUP BY categoria;",
  "SELECT id, edad FROM clientes ORDER BY edad;",
  "EXPLAIN ANALYZE SELECT categoria, SUM(monto) FROM ventas WHERE monto > 300 GROUP BY categoria ORDER BY categoria;",
  "EXPLAIN SELECT * FROM productos WHERE id < 10;",
]

function conExplain(sql, prefijo) {
  const limpio = sql.trim().replace(/^explain\s+(analyze\s+)?/i, '')
  return prefijo + limpio
}

export default function QueryPanel({ onRun, loading }) {
  const [sql, setSql] = useState(EJEMPLOS[0])
  return (
    <section className="panel query">
      <h2>Consultas</h2>
      <div className="toolbar">
        <button className="btn" onClick={() => onRun(sql)} disabled={loading}>
          ▶ Ejecutar
        </button>
        <button className="btn secondary" onClick={() => onRun(conExplain(sql, 'EXPLAIN '))} disabled={loading}>
          Explain
        </button>
        <button className="btn secondary" onClick={() => onRun(conExplain(sql, 'EXPLAIN ANALYZE '))} disabled={loading}>
          Explain Analyze
        </button>
        <span className="lbl">Ejemplos:</span>
        {EJEMPLOS.map((q, i) => (
          <button key={i} className="ex-link" title={q} onClick={() => setSql(q)}>
            {i + 1}
          </button>
        ))}
      </div>
      <div className="panel-body flush query">
        <textarea
          value={sql}
          spellCheck={false}
          onChange={(e) => setSql(e.target.value)}
        />
      </div>
    </section>
  )
}
