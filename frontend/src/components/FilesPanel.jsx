import { useState } from 'react'

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
            <div key={ix.field} className="idx-row">
              <span className="kind">{ix.type}</span> · {ix.field}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function FilesPanel({ tables }) {
  return (
    <aside className="panel files">
      <h2>Archivos</h2>
      <div className="panel-body">
        {tables.length === 0 ? (
          <p className="muted">Sin tablas.</p>
        ) : (
          tables.map((t) => <TableItem key={t.name} table={t} />)
        )}
      </div>
    </aside>
  )
}
