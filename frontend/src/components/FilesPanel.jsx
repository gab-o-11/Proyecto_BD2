import { useRef, useState } from 'react'

function TableItem({ table }) {
  const [open, setOpen] = useState(true)
  return (
    <div className="tree-item">
      <button className="tree-head" onClick={() => setOpen(!open)}>
        <span className="chev">{open ? '▾' : '▸'}</span>
        <span className="node-icon tbl" />
        {table.name} <span className="muted">({table.rows})</span>{table.storage && <span className="muted"> · {table.storage}</span>}
      </button>
      {open && (
        <div className="tree-body">
          {table.columns.map((c) => (
            <div key={c.name} className="col-row">
              <span>{c.name}</span>
              <span className="type">{c.type}</span>
            </div>
          ))}
          <div className="idx-title">Índices</div>
          {table.indexes.map((ix) => (
            <div key={ix.name || ix.type + ix.field} className="idx-row" title={ix.name}>
              <span className="kind">{ix.type}</span> · {ix.field}{ix.primary === false && ix.type !== 'RTREE' && <span className="muted"> · {ix.name}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function FilesPanel({ tables, onImport, onReset, loading }) {
  const inputRef = useRef(null)
  const [tableName, setTableName] = useState('')
  const [indexField, setIndexField] = useState('')
  const [indexKind, setIndexKind] = useState('HASH')
  const [importError, setImportError] = useState('')
  const [importMessage, setImportMessage] = useState('')
  const [confirmando, setConfirmando] = useState(false)
  const [resetMessage, setResetMessage] = useState('')

  async function submit(event) {
    event.preventDefault()
    setImportError('')
    setImportMessage('')
    const file = inputRef.current?.files?.[0]
    if (!file) {
      setImportError('Selecciona un archivo CSV.')
      return
    }
    if (!tableName.trim()) {
      setImportError('Escribe un nombre para la tabla.')
      return
    }
    const result = await onImport(file, tableName.trim(), indexKind, indexField.trim())
    if (result?.error) setImportError(result.error)
    else setImportMessage(result?.message || 'Importación completada.')
  }

  async function borrarTodo() {
    setConfirmando(false)
    const result = await onReset()
    setResetMessage(result?.error || result?.message || '')
  }

  return (
    <aside className="panel files">
      <h2>Archivos</h2>
      <div className="panel-body">
        <form className="import-form" onSubmit={submit}>
          <div className="idx-title">Importar CSV</div>
          <input ref={inputRef} type="file" accept=".csv,text/csv" disabled={loading} />
          <input value={tableName} onChange={(event) => setTableName(event.target.value)} placeholder="Nombre de tabla" disabled={loading} />
          <input value={indexField} onChange={(event) => setIndexField(event.target.value)} placeholder="Columna índice (opcional)" disabled={loading} />
          <select value={indexKind} onChange={(event) => setIndexKind(event.target.value)} disabled={loading}>
            <option value="HASH">Hash extensible</option>
            <option value="BPLUS">B+ Tree</option>
            <option value="BPLUS_CLUSTERED">B+ Tree clustered</option>
          </select>
          <button className="btn" type="submit" disabled={loading}>Importar</button>
          {importError && <div className="import-error">{importError}</div>}
          {importMessage && <div className="import-message">{importMessage}</div>}
        </form>
        <div className="reset-box">
          {!confirmando ? (
            <button className="btn danger" onClick={() => { setResetMessage(''); setConfirmando(true) }} disabled={loading || tables.length === 0}>
              Borrar base de datos
            </button>
          ) : (
            <>
              <div className="reset-warning">Se borrarán {tables.length} tablas con sus datos e índices. No se puede deshacer.</div>
              <div className="reset-actions">
                <button className="btn danger" onClick={borrarTodo} disabled={loading}>Borrar todo</button>
                <button className="btn secondary" onClick={() => setConfirmando(false)} disabled={loading}>Cancelar</button>
              </div>
            </>
          )}
          {resetMessage && <div className="import-message">{resetMessage}</div>}
        </div>
        {tables.length === 0 ? (
          <p className="muted">Sin tablas.</p>
        ) : (
          tables.map((t) => <TableItem key={t.name} table={t} />)
        )}
      </div>
    </aside>
  )
}
