import { useState } from 'react'

function Panel({ title, children }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      <div className="panel-body">{children}</div>
    </section>
  )
}

export default function App() {
  const [stats, setStats] = useState(null)
  const [claves, setClaves] = useState([])
  const [error, setError] = useState(null)

  async function correrDemo() {
    setError(null)
    try {
      const res = await fetch('/api/hashing/demo')
      if (!res.ok) throw new Error('HTTP ' + res.status)
      const data = await res.json()
      setStats(data.stats)
      setClaves(data.claves)
    } catch (e) {
      setError(String(e))
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>MiniGestor BD2</h1>
        <button onClick={correrDemo}>Correr demo hashing</button>
      </header>
      {error && <div className="error">{error}</div>}
      <main className="grid">
        <Panel title="Archivos">
          <p>Tablas e indices cargados.</p>
        </Panel>
        <Panel title="Consultas">
          <textarea placeholder="SELECT * FROM tabla WHERE ..." />
        </Panel>
        <Panel title="Resultados">
          {claves.length > 0 ? (
            <p>Claves insertadas: {claves.join(', ')}</p>
          ) : (
            <p>Sin resultados.</p>
          )}
        </Panel>
        <Panel title="Plan de Ejecucion">
          {stats ? (
            <ul>
              {Object.entries(stats).map(([k, v]) => (
                <li key={k}>
                  {k}: {String(v)}
                </li>
              ))}
            </ul>
          ) : (
            <p>Ejecuta una consulta para ver el plan.</p>
          )}
        </Panel>
      </main>
    </div>
  )
}
