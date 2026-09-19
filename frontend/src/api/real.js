function normStep(s) {
  if (typeof s === 'string') return { op: s, method: '', detail: '', rows: 0 }
  return { op: s.op || '', method: s.method || '', detail: s.detail || '', rows: s.rows ?? 0 }
}

function normTable(t) {
  return {
    name: t.name,
    columns: t.columns || [],
    indexes: t.indexes || [],
    rows: t.rows ?? 0,
    storage: t.storage || '',
  }
}

function normStatement(s) {
  const out = { type: s.type || '', plan: (s.plan || []).map(normStep) }
  if (s.error) out.error = s.error
  if (s.columns) out.columns = s.columns
  if (s.rows) out.rows = s.rows
  if (s.message) out.message = s.message
  return out
}

export async function listTables() {
  try {
    const res = await fetch('/api/tables')
    if (!res.ok) return []
    const data = await res.json()
    return (Array.isArray(data) ? data : []).map(normTable)
  } catch {
    return []
  }
}

export async function runQuery(sql) {
  try {
    const res = await fetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sql }),
    })
    if (!res.ok) return { error: 'HTTP ' + res.status, plan: [], statements: [] }
    const data = await res.json()
    return {
      error: data.error,
      message: data.message,
      columns: data.columns,
      rows: data.rows || (data.columns ? [] : undefined),
      plan: (data.plan || []).map(normStep),
      statements: (data.statements || []).map(normStatement),
      elapsedMs: data.elapsedMs,
    }
  } catch (e) {
    return { error: String(e), plan: [], statements: [] }
  }
}

export async function importCsv(file, tableName, indexKind, indexField) {
  const form = new FormData()
  form.append('file', file)
  form.append('table_name', tableName)
  form.append('index_kind', indexKind)
  form.append('index_field', indexField)
  try {
    const res = await fetch('/api/tables/import', { method: 'POST', body: form })
    const data = await res.json()
    if (!res.ok) return { error: data.detail || data.error || `HTTP ${res.status}` }
    return data
  } catch (error) {
    return { error: String(error) }
  }
}
