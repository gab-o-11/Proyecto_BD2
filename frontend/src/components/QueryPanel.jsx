import { useState } from 'react'

const EJEMPLOS = [
  "SELECT * FROM clientes WHERE id = 7;",
  "SELECT * FROM clientes WHERE edad BETWEEN 25 AND 40;",
  "SELECT * FROM ventas WHERE categoria = 'A' ORDER BY monto DESC;",
  "SELECT categoria, COUNT(*) FROM ventas GROUP BY categoria;",
]

export default function QueryPanel({ onRun, loading }) {
  const [sql, setSql] = useState(EJEMPLOS[0])
  return (
    <section className="panel query">
      <h2>Consultas</h2>
      <div className="toolbar">
        <button className="btn" onClick={() => onRun(sql)} disabled={loading}>
          ▶ Ejecutar
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
