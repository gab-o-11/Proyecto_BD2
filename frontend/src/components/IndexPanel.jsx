import { useEffect, useRef, useState } from 'react'
import { describirIndice, rectangulosIndice } from '../api/client'

const TIPOS = { BPLUS: 'B+ no agrupado', BPLUS_CLUSTERED: 'B+ agrupado', RTREE: 'R-Tree' }
const MAX_FILAS = 60

function opcionesDe(tables) {
  const salida = []
  for (const t of tables) {
    for (const i of t.indexes || []) {
      if (!TIPOS[i.type]) continue
      salida.push({
        value: JSON.stringify([t.name, i.field]),
        tabla: t.name,
        columna: i.field,
        label: `${t.name}.${i.field} · ${TIPOS[i.type]}`,
      })
    }
  }
  return salida
}

function resumir(lista, max = 6) {
  if (lista.length <= max) return lista.join(' | ')
  return [...lista.slice(0, 3), '…', ...lista.slice(-2)].join(' | ')
}

const num = (x) => Number(x).toFixed(4)
const mbrTexto = (m) => (m ? `[${num(m[0])}, ${num(m[1])}] – [${num(m[2])}, ${num(m[3])}]` : 'vacío')

function hijosDe(nodo) {
  if (!nodo || nodo.hoja) return []
  return nodo.hijos.map((h) => (typeof h === 'number' ? h : h.pagina))
}

function aplanar(nodo, mapa) {
  const { nodos, ...resto } = nodo
  mapa[nodo.pagina] = resto
  for (const hijo of nodos || []) aplanar(hijo, mapa)
}

function Caja({ nodo, rtree, visitado, abierto, seleccionado, onClick }) {
  const clases = ['idx-node']
  if (nodo.hoja) clases.push('hoja')
  if (visitado) clases.push('visitado')
  if (seleccionado) clases.push('seleccionado')
  let cuerpo
  if (rtree) cuerpo = nodo.hoja ? `${nodo.puntos.length} puntos` : `${nodo.hijos.length} hijos`
  else cuerpo = resumir(nodo.claves) || 'vacío'
  const marca = nodo.hoja ? '' : abierto ? ' ▾' : ' ▸'
  return (
    <button className={clases.join(' ')} onClick={onClick} title={rtree ? mbrTexto(nodo.mbr) : nodo.claves.join(', ')}>
      <span className="idx-pg">p.{nodo.pagina}{marca}</span>
      <span className="idx-keys">{cuerpo}</span>
    </button>
  )
}

function Rama({ pagina, ctx }) {
  const nodo = ctx.nodos[pagina]
  if (!nodo) return <li><span className="idx-node pendiente">p.{pagina}</span></li>
  const abierto = ctx.abiertos.has(pagina)
  const hijos = hijosDe(nodo)
  return (
    <li>
      <Caja
        nodo={nodo}
        rtree={ctx.rtree}
        visitado={ctx.visitadas.has(pagina)}
        abierto={abierto}
        seleccionado={ctx.seleccion === pagina}
        onClick={() => ctx.alternar(pagina)}
      />
      {abierto && hijos.length > 0 && (
        <ul>
          {hijos.map((h) => <Rama key={h} pagina={h} ctx={ctx} />)}
        </ul>
      )}
    </li>
  )
}

function rango(claves, i) {
  if (!claves.length) return 'todas'
  if (i === 0) return `< ${claves[0]}`
  if (i >= claves.length) return `≥ ${claves[claves.length - 1]}`
  return `[${claves[i - 1]}, ${claves[i]})`
}

function Detalle({ nodo, rtree }) {
  if (!nodo) return <p className="muted">Haz clic en un nodo para ver su contenido.</p>
  const titulo = `Página ${nodo.pagina} · ${nodo.hoja ? 'hoja' : 'nodo interno'}`
  if (rtree && nodo.hoja) {
    return (
      <div>
        <div className="idx-det-title">{titulo} · MBR {mbrTexto(nodo.mbr)}</div>
        <table className="grid-table">
          <thead><tr><th>Latitud</th><th>Longitud</th><th>RID</th></tr></thead>
          <tbody>
            {nodo.puntos.slice(0, MAX_FILAS).map((p, i) => (
              <tr key={i}><td>{num(p.coordenadas[0])}</td><td>{num(p.coordenadas[1])}</td><td>{JSON.stringify(p.rid)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  if (rtree) {
    return (
      <div>
        <div className="idx-det-title">{titulo} · MBR {mbrTexto(nodo.mbr)}</div>
        <table className="grid-table">
          <thead><tr><th>Hijo</th><th>Entradas</th><th>MBR</th></tr></thead>
          <tbody>
            {nodo.hijos.map((h) => (
              <tr key={h.pagina}><td>p.{h.pagina}</td><td>{h.entradas}</td><td>{mbrTexto(h.mbr)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  if (nodo.hoja) {
    return (
      <div>
        <div className="idx-det-title">{titulo} · siguiente hoja: {nodo.siguiente >= 0 ? `p.${nodo.siguiente}` : 'ninguna'}</div>
        <table className="grid-table">
          <thead><tr><th>Clave</th><th>RID</th></tr></thead>
          <tbody>
            {nodo.claves.slice(0, MAX_FILAS).map((k, i) => (
              <tr key={i}><td>{String(k)}</td><td>{JSON.stringify(nodo.rids[i])}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  return (
    <div>
      <div className="idx-det-title">{titulo}</div>
      <table className="grid-table">
        <thead><tr><th>Hijo</th><th>Rango de claves</th></tr></thead>
        <tbody>
          {nodo.hijos.map((h, i) => (
            <tr key={h}><td>p.{h}</td><td>{rango(nodo.claves, i)}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function IndexPanel({ tables, result, onRectangulos }) {
  const opciones = opcionesDe(tables)
  const [elegido, setElegido] = useState('')
  const [info, setInfo] = useState(null)
  const [nodos, setNodos] = useState({})
  const [abiertos, setAbiertos] = useState(new Set())
  const [seleccion, setSeleccion] = useState(null)
  const [error, setError] = useState('')
  const [verMapa, setVerMapa] = useState(false)
  const [niveles, setNiveles] = useState(2)
  const nodosRef = useRef({})
  const turno = useRef(0)
  const contenedor = useRef(null)
  const centrar = useRef(false)

  const recorrido = result && !result.error ? result.recorrido || [] : []
  const [tabla, columna] = elegido ? JSON.parse(elegido) : ['', '']
  const entrada = recorrido.find((r) => r.tabla === tabla && r.columna === columna)
  const visitadas = new Set(entrada ? entrada.paginas : [])
  const rtree = info?.tipo === 'RTREE'

  function guardar(mapa) {
    nodosRef.current = mapa
    setNodos(mapa)
  }

  useEffect(() => {
    const usado = recorrido.map((r) => JSON.stringify([r.tabla, r.columna])).find((v) => opciones.some((o) => o.value === v))
    if (usado) setElegido(usado)
    else if (!opciones.some((o) => o.value === elegido)) setElegido(opciones[0]?.value || '')
  }, [tables, result])

  useEffect(() => {
    if (!tabla) {
      setInfo(null)
      guardar({})
      return
    }
    const mio = ++turno.current
    setError('')
    describirIndice(tabla, columna, null, 2).then(async (r) => {
      if (mio !== turno.current) return
      if (r.error) {
        setError(r.error)
        setInfo(null)
        guardar({})
        return
      }
      const mapa = {}
      aplanar(r.nodo, mapa)
      const abiertosNuevos = new Set([r.raiz])
      await expandirCamino(r.raiz, mapa, abiertosNuevos, mio)
      if (mio !== turno.current) return
      setInfo({ tipo: r.tipo, altura: r.altura, raiz: r.raiz, orden: r.orden })
      guardar(mapa)
      setAbiertos(abiertosNuevos)
      setSeleccion(null)
      centrar.current = true
    })
  }, [elegido, result])

  useEffect(() => {
    if (!centrar.current || !contenedor.current) return
    centrar.current = false
    const caja = contenedor.current
    const visitados = caja.querySelectorAll('.idx-node.visitado')
    const objetivo = visitados.length ? visitados[visitados.length - 1] : caja.querySelector('.idx-node')
    if (!objetivo) return
    const a = caja.getBoundingClientRect()
    const b = objetivo.getBoundingClientRect()
    caja.scrollLeft += b.left + b.width / 2 - (a.left + a.width / 2)
    caja.scrollTop += b.top + b.height / 2 - (a.top + a.height / 2)
  }, [abiertos, nodos])

  async function expandirCamino(raiz, mapa, abiertosNuevos, mio) {
    if (!visitadas.size) return
    const cola = [raiz]
    while (cola.length) {
      const pagina = cola.shift()
      const nodo = mapa[pagina]
      if (!nodo || nodo.hoja) continue
      const caminos = hijosDe(nodo).filter((h) => visitadas.has(h))
      if (!caminos.length) continue
      if (hijosDe(nodo).some((h) => !mapa[h])) {
        const r = await describirIndice(tabla, columna, pagina, 1)
        if (mio !== turno.current) return
        if (r.nodo) aplanar(r.nodo, mapa)
      }
      abiertosNuevos.add(pagina)
      cola.push(...caminos)
    }
  }

  async function alternar(pagina) {
    setSeleccion(pagina)
    const nodo = nodosRef.current[pagina]
    if (!nodo || nodo.hoja) return
    if (abiertos.has(pagina)) {
      const nuevos = new Set(abiertos)
      nuevos.delete(pagina)
      setAbiertos(nuevos)
      return
    }
    if (hijosDe(nodo).some((h) => !nodosRef.current[h])) {
      const r = await describirIndice(tabla, columna, pagina, 1)
      if (r.error) {
        setError(r.error)
        return
      }
      const mapa = { ...nodosRef.current }
      aplanar(r.nodo, mapa)
      guardar(mapa)
    }
    setAbiertos((previos) => new Set(previos).add(pagina))
  }

  useEffect(() => {
    if (!onRectangulos) return
    if (!verMapa || !rtree) {
      onRectangulos(null)
      return
    }
    let activo = true
    rectangulosIndice(tabla, columna, niveles).then((r) => {
      if (!activo) return
      if (r.error) {
        setError(r.error)
        onRectangulos(null)
        return
      }
      onRectangulos({ tabla, columna, rectangulos: r.rectangulos, visitadas: [...visitadas] })
    })
    return () => { activo = false }
  }, [verMapa, niveles, elegido, result, rtree])

  const ctx = { nodos, abiertos, visitadas, seleccion, rtree, alternar }

  return (
    <section className="panel indices">
      <h2>Índices</h2>
      <div className="toolbar idx-toolbar">
        <select aria-label="Índice" value={elegido} onChange={(e) => setElegido(e.target.value)}>
          {!opciones.length && <option value="">Sin índices B+ ni R-Tree</option>}
          {opciones.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        {info && <span className="lbl">altura {info.altura} · hasta {info.orden} entradas por nodo · raíz p.{info.raiz}</span>}
        {rtree && (
          <>
            <label className="lbl"><input type="checkbox" checked={verMapa} onChange={(e) => setVerMapa(e.target.checked)} /> MBR en el mapa</label>
            {verMapa && (
              <select aria-label="Niveles" value={niveles} onChange={(e) => setNiveles(Number(e.target.value))}>
                {Array.from({ length: info.altura }, (_, i) => i + 1).map((n) => (
                  <option key={n} value={n}>{n === info.altura ? `${n} niveles (hasta hojas)` : `${n} nivel${n > 1 ? 'es' : ''}`}</option>
                ))}
              </select>
            )}
          </>
        )}
      </div>
      <div className="panel-body flush idx-body">
        {error ? (
          <div className="error">{error}</div>
        ) : !info ? (
          <p className="muted" style={{ padding: '6px 8px' }}>Elige un índice B+ o R-Tree.</p>
        ) : (
          <div className="idx-split">
            <div className="idx-tree" ref={contenedor}>
              <ul><Rama pagina={info.raiz} ctx={ctx} /></ul>
            </div>
            <div className="idx-detail">
              <Detalle nodo={seleccion !== null ? nodos[seleccion] : null} rtree={rtree} />
            </div>
          </div>
        )}
      </div>
      <div className="status">
        {visitadas.size > 0
          ? `Naranja: ${visitadas.size} páginas de este índice visitadas por la última consulta`
          : 'Ejecuta una consulta que use este índice para ver su recorrido'}
      </div>
    </section>
  )
}
