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

export default function PlanPanel({ result }) {
  const plan = combinedPlan(result)
  const explain = result && !result.error ? result.explain : null
  const hasPlan = result && !result.error && plan.length > 0
  return (
    <section className="panel plan">
      <h2>Plan de Ejecución</h2>
      <div className="panel-body">
        {explain && (
          <div className="ex-resumen">
            <div className="ex-kind">{explain.analyze ? 'EXPLAIN ANALYZE' : 'EXPLAIN'}</div>
            <div>Planning Time: {fmt(explain.planningMs, 3)} ms</div>
            {explain.analyze && <div>Execution Time: {fmt(explain.executionMs, 3)} ms</div>}
            <div className="muted">Árbol completo en la pestaña Plan.</div>
          </div>
        )}
        {hasPlan ? (
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
        ) : (
          !explain && <p className="muted">Sin plan. Usa EXPLAIN o EXPLAIN ANALYZE para ver el plan estimado.</p>
        )}
      </div>
    </section>
  )
}
