import { useState } from 'react'

const EJEMPLOS = [
  "CREATE TABLE tiendas (id INT PRIMARY KEY, nombre VARCHAR(30), ubicacion POINT); INSERT INTO tiendas VALUES (1, 'Centro', POINT(-12.0464, -77.0428)); INSERT INTO tiendas VALUES (2, 'Sur', POINT(-12.08, -77.03)); INSERT INTO tiendas VALUES (3, 'Lejos', POINT(-12.2, -77.1)); SELECT * FROM tiendas;",
  "SELECT * FROM tiendas WHERE distancia(ubicacion, mi_ubicacion) < 5000;",
  "SELECT id FROM tiendas ORDER BY distancia(ubicacion, mi_ubicacion) LIMIT 2;",
  "SELECT * FROM tiendas WHERE intersecta(ubicacion, POLYGON(POINT(-12.1, -77.1), POINT(-12, -77.1), POINT(-12, -77), POINT(-12.1, -77)));",
  "SELECT * FROM clientes WHERE id = 7;",
  "SELECT id, monto FROM ventas WHERE monto > 500;",
  "SELECT categoria FROM ventas GROUP BY categoria;",
  "SELECT id, edad FROM clientes ORDER BY edad;",
  "EXPLAIN ANALYZE SELECT categoria, SUM(monto) FROM ventas WHERE monto > 300 GROUP BY categoria ORDER BY categoria;",
  "EXPLAIN SELECT * FROM productos WHERE id < 10;",
  "SELECT c.nombre, v.monto FROM clientes c JOIN ventas v ON c.id = v.cliente_id ORDER BY v.monto DESC;",
]

function conExplain(sql, prefijo) {
  const limpio = sql.trim().replace(/^explain\s+(analyze\s+)?/i, '')
  return prefijo + limpio
}

export default function QueryPanel({ onRun, loading }) {
  const [sql, setSql] = useState("SELECT * FROM clientes WHERE id = 7;")
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
