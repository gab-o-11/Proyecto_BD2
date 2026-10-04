import { useState } from 'react'

function fmt(n, d) {
  return Number(n).toFixed(d)
}

function tiempoPropio(nodo) {
  if (!nodo.actual) return 0
  let hijos = 0
  for (const c of nodo.children) {
    if (c.actual) hijos += c.actual.totalMs
  }
  return Math.max(0, nodo.actual.totalMs - hijos)
}

function malaEstimacion(nodo) {
  if (!nodo.actual) return null
  const est = Math.max(nodo.planRows, 1)
  const real = Math.max(nodo.actual.rows, 1)
  const factor = real > est ? real / est : est / real
  if (factor < 10) return null
  return real > est ? `subestimado ×${fmt(factor, 0)}` : `sobreestimado ×${fmt(factor, 0)}`
}

function Tarjeta({ nodo, analyze, totalMs }) {
  const propio = tiempoPropio(nodo)
  const pct = analyze && totalMs > 0 ? Math.min(100, (propio / totalMs) * 100) : 0
  const aviso = malaEstimacion(nodo)
  const detalles = [...nodo.details, ...(nodo.actual ? nodo.actual.details : [])]
  return (
    <div className="hp-nodo">
      <div className="hp-titulo">{nodo.title}</div>
      <div className="hp-linea">cost {fmt(nodo.startupCost, 2)}..{fmt(nodo.totalCost, 2)} · est. {nodo.planRows} filas</div>
      {nodo.actual && (
        <>
          <div className="hp-linea ex-real">real {nodo.actual.rows} filas · {fmt(nodo.actual.startupMs, 3)}..{fmt(nodo.actual.totalMs, 3)} ms</div>
          <div className="hp-linea">buffers read={nodo.actual.sharedRead} hit={nodo.actual.sharedHit}</div>
        </>
      )}
      {aviso && <div className="ex-warn">{aviso}</div>}
      {detalles.map((d, i) => <div key={i} className="hp-detalle">{d}</div>)}
      {analyze && nodo.actual && (
        <div className="ex-bar" title={`tiempo propio ${fmt(propio, 3)} ms`}>
          <div style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  )
}

function Rama({ nodo, analyze, totalMs }) {
  return (
    <div className="hp-rama">
      <Tarjeta nodo={nodo} analyze={analyze} totalMs={totalMs} />
      {nodo.children.length > 0 && (
        <div className="hp-hijos">
          {nodo.children.map((c, i) => (
            <div key={i} className="hp-hijo">
              <Rama nodo={c} analyze={analyze} totalMs={totalMs} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function ExplainTree({ result }) {
  const [vista, setVista] = useState('arbol')
  const explain = result && !result.error ? result.explain : null
  const totalMs = explain?.analyze && explain.tree.actual ? explain.tree.actual.totalMs : 0
  return (
    <section className="panel plan-ancho">
      <h2>Plan</h2>
      {explain && (
        <div className="toolbar">
          <span className="ex-kind">{explain.analyze ? 'EXPLAIN ANALYZE' : 'EXPLAIN'}</span>
          <span className="lbl">las filas fluyen de derecha a izquierda</span>
          <button className={vista === 'arbol' ? 'tab active' : 'tab'} onClick={() => setVista('arbol')}>Árbol</button>
          <button className={vista === 'texto' ? 'tab active' : 'tab'} onClick={() => setVista('texto')}>Texto</button>
        </div>
      )}
      <div className="panel-body">
        {!explain ? (
          <p className="muted">Ejecuta una consulta con Explain o Explain Analyze para ver su plan.</p>
        ) : vista === 'arbol' ? (
          <div className="hp-lienzo">
            <Rama nodo={explain.tree} analyze={explain.analyze} totalMs={totalMs} />
          </div>
        ) : (
          <pre className="ex-text">{explain.text.join('\n')}</pre>
        )}
      </div>
      {explain && (
        <div className="status">
          Planning Time: {fmt(explain.planningMs, 3)} ms
          {explain.analyze && <> · Execution Time: {fmt(explain.executionMs, 3)} ms</>}
        </div>
      )}
    </section>
  )
}
