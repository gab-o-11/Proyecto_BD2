export async function listTables() {
  const res = await fetch('/api/tables')
  if (!res.ok) throw new Error('HTTP ' + res.status)
  return res.json()
}

export async function runQuery(sql) {
  const res = await fetch('/api/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sql }),
  })
  if (!res.ok) return { error: 'HTTP ' + res.status }
  return res.json()
}
