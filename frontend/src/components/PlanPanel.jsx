import { useState } from 'react'

function combinedPlan(result) {
  if (!result) return []
  if (result.statements && result.statements.length > 0) {
    const out = []
    for (const st of result.statements) {
      for (const s of st.plan || []) {
        out.push({ ...s, type: st.type })
      }
    }
    return out
  }
  return result.plan || []
}

function fmt(n, d) {
  return Number(n).toFixed(d)
}

function selfTime(node) {
  if (!node.actual) return 0
  let hijos = 0
  for (const c of node.children) {
    if (c.actual) hijos += c.actual.totalMs
  }
  return Math.max(0, node.actual.totalMs - hijos)
}

function misestimate(node) {
  if (!node.actual) return null
  const est = Math.max(node.planRows, 1)
  const real = Math.max(node.actual.rows, 1)
  const factor = real > est ? real / est : est / real
  if (factor < 10) return null
  return real > est ? `subestimado ×${fmt(factor, 0)}` : `sobreestimado ×${fmt(factor, 0)}`
}

function ExplainNode({ node, analyze, totalMs }) {
  const [open, setOpen] = useState(true)
  const propio = selfTime(node)
  const pct = analyze && totalMs > 0 ? Math.min(100, (propio / totalMs) * 100) : 0
  const aviso = misestimate(node)
  return (
    <li className="ex-node">
      <div className="ex-card">
        <div className="ex-head" onClick={() => setOpen(!open)}>
          {node.children.length > 0 && <span className="chev">{open ? '▾' : '▸'}</span>}
          <span className="ex-title">{node.title}</span>
        </div>
        <div className="ex-metrics">
          <span title="costo de arranque..costo total (unidades de página secuencial)">
            cost {fmt(node.startupCost, 2)}..{fmt(node.totalCost, 2)}
          </span>
          <span>est. {node.planRows} filas</span>
          <span>width {node.planWidth}</span>
          {node.actual && (
            <>
              <span className="ex-real">real {node.actual.rows} filas</span>
              <span className="ex-real">
                {fmt(node.actual.startupMs, 3)}..{fmt(node.actual.totalMs, 3)} ms
              </span>
              <span title="páginas distintas leídas / accesos repetidos">
                buffers read={node.actual.sharedRead} hit={node.actual.sharedHit}
              </span>
            </>
          )}
        </div>
        {aviso && <div className="ex-warn">{aviso}</div>}
        {[...node.details, ...(node.actual ? node.actual.details : [])].map((d, i) => (
          <div key={i} className="plan-detail">{d}</div>
        ))}
        {analyze && node.actual && (
          <div className="ex-bar" title={`tiempo propio ${fmt(propio, 3)} ms`}>
            <div style={{ width: `${pct}%` }} />
          </div>
        )}
      </div>
      {open && node.children.length > 0 && (
        <ul className="ex-children">
          {node.children.map((c, i) => (
            <ExplainNode key={i} node={c} analyze={analyze} totalMs={totalMs} />
          ))}
        </ul>
      )}
    </li>
  )
}

function ExplainView({ explain }) {
  const [vista, setVista] = useState('arbol')
  const totalMs = explain.analyze && explain.tree.actual ? explain.tree.actual.totalMs : 0
  return (
    <>
      <div className="ex-toolbar">
        <span className="ex-kind">{explain.analyze ? 'EXPLAIN ANALYZE' : 'EXPLAIN'}</span>
        <button className={vista === 'arbol' ? 'tab active' : 'tab'} onClick={() => setVista('arbol')}>
          Árbol
        </button>
        <button className={vista === 'texto' ? 'tab active' : 'tab'} onClick={() => setVista('texto')}>
          Texto
        </button>
      </div>
      {vista === 'arbol' ? (
        <ul className="ex-root">
          <ExplainNode node={explain.tree} analyze={explain.analyze} totalMs={totalMs} />
        </ul>
      ) : (
        <pre className="ex-text">{explain.text.join('\n')}</pre>
      )}
      {vista === 'arbol' && (
        <div className="ex-times">
          Planning Time: {fmt(explain.planningMs, 3)} ms
          {explain.analyze && <> · Execution Time: {fmt(explain.executionMs, 3)} ms</>}
        </div>
      )}
    </>
  )
}

export default function PlanPanel({ result }) {
  const plan = combinedPlan(result)
  const explain = result && !result.error ? result.explain : null
  const hasPlan = result && !result.error && plan.length > 0
  return (
    <section className="panel plan">
      <h2>Plan de Ejecución</h2>
      <div className="panel-body">
        {explain ? (
          <ExplainView explain={explain} />
        ) : !hasPlan ? (
          <p className="muted">Sin plan. Usa EXPLAIN o EXPLAIN ANALYZE para ver el plan estimado.</p>
        ) : (
          <ol className="plan-list">
            {plan.map((s, i) => (
              <li key={i} className="plan-step">
                <div className="plan-op">{s.type ? `[${s.type}] ` : ''}{s.op}</div>
                {s.method && <div className="plan-method">{s.method}</div>}
                {s.detail && <div className="plan-detail">{s.detail}</div>}
                {s.rows != null && <div className="plan-rows">{s.rows} filas</div>}
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  )
}
