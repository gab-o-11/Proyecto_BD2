const nombres = [
  'Ana', 'Beto', 'Caro', 'Dora', 'Elin', 'Fabio', 'Gina', 'Hugo', 'Iris', 'Juan',
  'Kira', 'Leo', 'Mia', 'Nico', 'Olga', 'Pablo', 'Rosa', 'Saul', 'Tina', 'Ugo',
  'Vera', 'Wes', 'Xime', 'Yago',
]
const ciudades = ['Lima', 'Cusco', 'Arequipa', 'Trujillo', 'Piura']
const categorias = ['A', 'B', 'C']

const clientesRows = Array.from({ length: 24 }, (_, i) => ({
  id: i + 1,
  nombre: nombres[i],
  ciudad: ciudades[i % ciudades.length],
  edad: 18 + ((i + 1) * 7) % 43,
}))

const ventasRows = Array.from({ length: 40 }, (_, i) => ({
  id: i + 1,
  cliente_id: 1 + ((i + 1) * 5) % 24,
  monto: 100 + ((i + 1) * 137) % 900,
  categoria: categorias[(i + 1) % 3],
}))

const tables = {
  clientes: {
    name: 'clientes',
    columns: [
      { name: 'id', type: 'int' },
      { name: 'nombre', type: 'str' },
      { name: 'ciudad', type: 'str' },
      { name: 'edad', type: 'int' },
    ],
    indexes: [
      { field: 'id', type: 'hash' },
      { field: 'edad', type: 'bplus' },
    ],
    rows: clientesRows,
  },
  ventas: {
    name: 'ventas',
    columns: [
      { name: 'id', type: 'int' },
      { name: 'cliente_id', type: 'int' },
      { name: 'monto', type: 'int' },
      { name: 'categoria', type: 'str' },
    ],
    indexes: [
      { field: 'monto', type: 'bplus' },
      { field: 'categoria', type: 'hash' },
    ],
    rows: ventasRows,
  },
}

function delay(value) {
  return new Promise((resolve) => setTimeout(() => resolve(value), 140))
}

export function listTables() {
  const list = Object.values(tables).map((t) => ({
    name: t.name,
    columns: t.columns,
    indexes: t.indexes,
    rows: t.rows.length,
  }))
  return delay(list)
}

function parseValue(token) {
  const t = token.trim()
  if (/^'.*'$/.test(t)) return t.slice(1, -1)
  const n = Number(t)
  return Number.isNaN(n) ? t : n
}

function parseCondition(where) {
  if (!where) return null
  let m = where.match(/^(\w+)\s+between\s+(\S+)\s+and\s+(\S+)$/i)
  if (m) return { col: m[1], op: 'between', a: parseValue(m[2]), b: parseValue(m[3]) }
  m = where.match(/^(\w+)\s*(<=|>=|=|<|>)\s*('[^']*'|\S+)$/)
  if (m) return { col: m[1], op: m[2], value: parseValue(m[3]) }
  return { invalid: true, raw: where }
}

function matchRow(row, cond) {
  const v = row[cond.col]
  if (cond.op === 'between') return v >= cond.a && v <= cond.b
  if (cond.op === '=') return v === cond.value
  if (cond.op === '<') return v < cond.value
  if (cond.op === '>') return v > cond.value
  if (cond.op === '<=') return v <= cond.value
  if (cond.op === '>=') return v >= cond.value
  return true
}

function accessStep(table, cond) {
  if (!cond) {
    return { op: 'Sequential Scan', method: 'archivo de datos', detail: `${table.name} completo` }
  }
  const idx = table.indexes.find((ix) => ix.field === cond.col)
  const detail = cond.op === 'between'
    ? `${cond.col} entre ${cond.a} y ${cond.b}`
    : `${cond.col} ${cond.op} ${cond.value}`
  const isRange = cond.op === 'between' || ['<', '>', '<=', '>='].includes(cond.op)
  if (isRange) {
    if (idx && idx.type === 'bplus') {
      return { op: 'Index Range Scan', method: `B+ Tree (${idx.field})`, detail }
    }
    return { op: 'Sequential Scan + Filter', method: 'archivo de datos', detail }
  }
  if (idx && idx.type === 'hash') {
    return { op: 'Index Search', method: `Extendible Hash (${idx.field})`, detail }
  }
  if (idx && idx.type === 'bplus') {
    return { op: 'Index Search', method: `B+ Tree (${idx.field})`, detail }
  }
  return { op: 'Sequential Scan + Filter', method: 'archivo de datos', detail }
}

function runSelect(parsed) {
  const table = tables[parsed.table]
  if (!table) return { error: `Tabla desconocida: ${parsed.table}` }

  const cond = parseCondition(parsed.where)
  if (cond && cond.invalid) return { error: `Condición WHERE inválida: ${cond.raw}` }

  const plan = []
  const access = accessStep(table, cond)
  let rows = table.rows.slice()
  if (cond) rows = rows.filter((r) => matchRow(r, cond))
  plan.push({ ...access, rows: rows.length })

  let columns
  if (parsed.groupBy) {
    const counts = new Map()
    for (const r of rows) counts.set(r[parsed.groupBy], (counts.get(r[parsed.groupBy]) || 0) + 1)
    rows = [...counts.entries()].map(([k, c]) => ({ [parsed.groupBy]: k, count: c }))
    columns = [parsed.groupBy, 'count']
    plan.push({ op: 'Group By', method: 'External Hashing', detail: `agrupa por ${parsed.groupBy}`, rows: rows.length })
  } else if (parsed.cols === '*') {
    columns = table.columns.map((c) => c.name)
  } else {
    columns = parsed.cols.split(',').map((c) => c.trim())
  }

  if (parsed.orderBy) {
    const dir = parsed.orderDir === 'desc' ? -1 : 1
    rows.sort((a, b) => (a[parsed.orderBy] > b[parsed.orderBy] ? dir : a[parsed.orderBy] < b[parsed.orderBy] ? -dir : 0))
    const idx = table.indexes.find((ix) => ix.field === parsed.orderBy)
    const method = idx && idx.type === 'bplus' ? `B+ Leaf Scan (${idx.field})` : 'External Sort (k-way merge)'
    plan.push({ op: 'Order By', method, detail: `${parsed.orderBy} ${parsed.orderDir}`, rows: rows.length })
  }

  const projected = rows.map((r) => {
    const out = {}
    for (const c of columns) out[c] = r[c]
    return out
  })
  plan.push({ op: 'Project', method: columns.join(', '), rows: projected.length })

  return { columns, rows: projected, plan, elapsedMs: 2 + Math.round(Math.random() * 9) }
}

function parseSelect(sql) {
  const re = /^select\s+(.+?)\s+from\s+(\w+)(?:\s+where\s+(.+?))?(?:\s+group\s+by\s+(\w+))?(?:\s+order\s+by\s+(\w+)(?:\s+(asc|desc))?)?$/i
  const m = sql.match(re)
  if (!m) return null
  return {
    cols: m[1].trim(),
    table: m[2],
    where: m[3],
    groupBy: m[4],
    orderBy: m[5],
    orderDir: (m[6] || 'asc').toLowerCase(),
  }
}

export function runQuery(sql) {
  const clean = sql.trim().replace(/;\s*$/, '')
  if (/^select\b/i.test(clean)) {
    const parsed = parseSelect(clean)
    if (!parsed) return delay({ error: 'No se pudo interpretar el SELECT.' })
    return delay(runSelect(parsed))
  }
  let m = clean.match(/^insert\s+into\s+(\w+)/i)
  if (m) {
    return delay({
      message: `1 registro insertado en ${m[1]}.`,
      plan: [
        { op: 'Insert', method: 'Heap File (free list)', detail: 'append de registro' },
        { op: 'Index Maintenance', method: 'actualiza hash + B+', detail: `índices de ${m[1]}` },
      ],
      elapsedMs: 3 + Math.round(Math.random() * 5),
    })
  }
  m = clean.match(/^delete\s+from\s+(\w+)/i)
  if (m) {
    return delay({
      message: `Registros eliminados de ${m[1]}.`,
      plan: [
        { op: 'Search', method: 'índice / scan', detail: 'localiza registros' },
        { op: 'Delete', method: 'borrado lazy', detail: `en ${m[1]}` },
      ],
      elapsedMs: 3 + Math.round(Math.random() * 5),
    })
  }
  return delay({ error: 'Consulta no soportada por el mock.' })
}
