import { useEffect, useState } from 'react'
import { listTables, runQuery } from './api/client'
import FilesPanel from './components/FilesPanel'
import QueryPanel from './components/QueryPanel'
import ResultsPanel from './components/ResultsPanel'
import PlanPanel from './components/PlanPanel'

export default function App() {
  const [tables, setTables] = useState([])
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    listTables().then(setTables)
  }, [])

  async function ejecutar(sql) {
    setLoading(true)
    const res = await runQuery(sql)
    setResult(res)
    setLoading(false)
    listTables().then(setTables)
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>MiniGestor BD2</h1>
        <span className="db">— base de datos: minidb</span>
      </header>
      <div className="layout">
        <FilesPanel tables={tables} />
        <div className="workarea">
          <QueryPanel onRun={ejecutar} loading={loading} />
          <div className="bottom">
            <ResultsPanel result={result} />
            <PlanPanel result={result} />
          </div>
        </div>
      </div>
    </div>
  )
}
