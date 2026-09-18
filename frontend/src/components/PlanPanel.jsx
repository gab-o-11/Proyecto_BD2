export default function PlanPanel({ result }) {
  const hasPlan = result && !result.error && result.plan
  return (
    <section className="panel plan">
      <h2>Plan de Ejecución</h2>
      <div className="panel-body">
        {!hasPlan ? (
          <p className="muted">Sin plan.</p>
        ) : (
          <ol className="plan-list">
            {result.plan.map((s, i) => (
              <li key={i} className="plan-step">
                <div className="plan-op">{s.op}</div>
                <div className="plan-method">{s.method}</div>
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
