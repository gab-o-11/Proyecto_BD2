import { useEffect, useState } from 'react'
import { importCsv, listTables, runQuery } from './api/client'
import FilesPanel from './components/FilesPanel'
import QueryPanel from './components/QueryPanel'
import ResultsPanel from './components/ResultsPanel'
import PlanPanel from './components/PlanPanel'
import MapPanel from './components/MapPanel'
import IndexPanel from './components/IndexPanel'
import ExplainTree from './components/ExplainTree'

export default function App() {
  const [tables, setTables] = useState([])
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [dataVersion, setDataVersion] = useState(0)
  const [location, setLocation] = useState([-12.0464, -77.0428])
  const [vista, setVista] = useState('resultados')
  const [rectangulos, setRectangulos] = useState(null)

  useEffect(() => {
    listTables().then(setTables)
  }, [])

  async function ejecutar(sql) {
    setLoading(true)
    const res = await runQuery(sql, { mi_ubicacion: location })
    setResult(res)
    if (res.explain && !res.error) setVista('plan')
    else if (vista === 'plan') setVista('resultados')
    if (res.statements?.some(s => ['insert', 'update', 'delete', 'create'].includes(s.type))) setDataVersion(v => v + 1)
    setLoading(false)
    listTables().then(setTables)
  }

  async function importar(file, tableName, indexKind, indexField) {
    setLoading(true)
    const res = await importCsv(file, tableName, indexKind, indexField)
    setDataVersion(v => v + 1)
    setResult(res)
    setLoading(false)
    listTables().then(setTables)
    return res
  }

  const mbrActivos = vista === 'indices' && rectangulos !== null

  return (
    <div className="app">
      <header className="topbar">
        <h1>MiniGestor BD2</h1>
        <span className="db">— base de datos: minidb</span>
      </header>
      <div className="layout">
        <FilesPanel tables={tables} onImport={importar} loading={loading} />
        <div className="workarea">
          <QueryPanel onRun={ejecutar} loading={loading} />
          <MapPanel tables={tables} result={result} dataVersion={dataVersion} location={location} onLocation={setLocation} rectangulos={mbrActivos ? rectangulos : null} />
          <div className="bottom">
            <div className="stack">
              <div className="tabbar">
                <button className={vista === 'resultados' ? 'tab active' : 'tab'} onClick={() => setVista('resultados')}>Resultados</button>
                <button className={vista === 'plan' ? 'tab active' : 'tab'} onClick={() => setVista('plan')}>Plan</button>
                <button className={vista === 'indices' ? 'tab active' : 'tab'} onClick={() => setVista('indices')}>Índices</button>
              </div>
              {vista === 'resultados' && <ResultsPanel result={result} />}
              {vista === 'plan' && <ExplainTree result={result} />}
              {vista === 'indices' && <IndexPanel tables={tables} result={result} onRectangulos={setRectangulos} />}
            </div>
            <PlanPanel result={result} />
          </div>
        </div>
      </div>
    </div>
  )
}
