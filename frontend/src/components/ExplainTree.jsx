import { useEffect, useRef, useState } from 'react'

const ZOOM_MIN = 0.25
const ZOOM_MAX = 2
const ZOOM_PASO = 0.1

function acotar(valor) {
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(valor * 100) / 100))
}

function fmt(n, d) {
  return Number(n).toFixed(d)
}

function tiempoPropio(nodo) {
  if (!nodo.actual) return 0
  let hijos = 0
  for (const c of nodo.children) {
    if (c.actual) hijos += c.actual.totalMs
  }
  return Math.max(0, nodo.actual.totalMs - hijos)
}

function malaEstimacion(nodo) {
  if (!nodo.actual) return null
  const est = Math.max(nodo.planRows, 1)
  const real = Math.max(nodo.actual.rows, 1)
  const factor = real > est ? real / est : est / real
  if (factor < 10) return null
  return real > est ? `subestimado ×${fmt(factor, 0)}` : `sobreestimado ×${fmt(factor, 0)}`
}

function Tarjeta({ nodo, analyze, totalMs }) {
  const propio = tiempoPropio(nodo)
  const pct = analyze && totalMs > 0 ? Math.min(100, (propio / totalMs) * 100) : 0
  const aviso = malaEstimacion(nodo)
  const detalles = [...nodo.details, ...(nodo.actual ? nodo.actual.details : [])]
  return (
    <div className="hp-nodo">
      <div className="hp-titulo">{nodo.title}</div>
      <div className="hp-linea">cost {fmt(nodo.startupCost, 2)}..{fmt(nodo.totalCost, 2)} · est. {nodo.planRows} filas</div>
      {nodo.actual && (
        <>
          <div className="hp-linea ex-real">real {nodo.actual.rows} filas · {fmt(nodo.actual.startupMs, 3)}..{fmt(nodo.actual.totalMs, 3)} ms</div>
          <div className="hp-linea">buffers read={nodo.actual.sharedRead} hit={nodo.actual.sharedHit}</div>
        </>
      )}
      {aviso && <div className="ex-warn">{aviso}</div>}
      {detalles.map((d, i) => <div key={i} className="hp-detalle">{d}</div>)}
      {analyze && nodo.actual && (
        <div className="ex-bar" title={`tiempo propio ${fmt(propio, 3)} ms`}>
          <div style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  )
}

function Rama({ nodo, analyze, totalMs }) {
  return (
    <div className="hp-rama">
      <Tarjeta nodo={nodo} analyze={analyze} totalMs={totalMs} />
      {nodo.children.length > 0 && (
        <div className="hp-hijos">
          {nodo.children.map((c, i) => (
            <div key={i} className="hp-hijo">
              <Rama nodo={c} analyze={analyze} totalMs={totalMs} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function ExplainTree({ result }) {
  const [vista, setVista] = useState('arbol')
  const [zoom, setZoom] = useState(1)
  const marco = useRef(null)
  const lienzo = useRef(null)
  const explain = result && !result.error ? result.explain : null

  useEffect(() => {
    const nodo = marco.current
    if (!nodo) return
    function rueda(evento) {
      if (!evento.ctrlKey && !evento.metaKey) return
      evento.preventDefault()
      setZoom((actual) => acotar(actual * (evento.deltaY < 0 ? 1.1 : 1 / 1.1)))
    }
    nodo.addEventListener('wheel', rueda, { passive: false })
    return () => nodo.removeEventListener('wheel', rueda)
  }, [vista, explain])

  function ajustar() {
    if (!marco.current || !lienzo.current) return
    const caja = lienzo.current.getBoundingClientRect()
    const ancho = caja.width / zoom
    const alto = caja.height / zoom
    if (!ancho || !alto) return
    const estilo = getComputedStyle(marco.current)
    const disponibleAncho = marco.current.clientWidth - parseFloat(estilo.paddingLeft) - parseFloat(estilo.paddingRight)
    const disponibleAlto = marco.current.clientHeight - parseFloat(estilo.paddingTop) - parseFloat(estilo.paddingBottom)
    setZoom(acotar(Math.min(disponibleAncho / ancho, disponibleAlto / alto, 1)))
  }
  const totalMs = explain?.analyze && explain.tree.actual ? explain.tree.actual.totalMs : 0
  return (
    <section className="panel plan-ancho">
      <h2>Plan</h2>
      {explain && (
        <div className="toolbar">
          <span className="ex-kind">{explain.analyze ? 'EXPLAIN ANALYZE' : 'EXPLAIN'}</span>
          <span className="lbl">las filas fluyen de derecha a izquierda</span>
          {vista === 'arbol' && (
            <span className="zoom-controles" role="group" aria-label="Zoom del árbol">
              <button className="tab" onClick={() => setZoom((z) => acotar(z - ZOOM_PASO))} disabled={zoom <= ZOOM_MIN} aria-label="Alejar" title="Alejar (Ctrl + rueda)">−</button>
              <button className="tab zoom-valor" onClick={() => setZoom(1)} title="Volver al 100 %">{Math.round(zoom * 100)} %</button>
              <button className="tab" onClick={() => setZoom((z) => acotar(z + ZOOM_PASO))} disabled={zoom >= ZOOM_MAX} aria-label="Acercar" title="Acercar (Ctrl + rueda)">+</button>
              <button className="tab" onClick={ajustar} title="Ajustar el árbol al panel">Ajustar</button>
            </span>
          )}
          <button className={vista === 'arbol' ? 'tab active' : 'tab'} onClick={() => setVista('arbol')}>Árbol</button>
          <button className={vista === 'texto' ? 'tab active' : 'tab'} onClick={() => setVista('texto')}>Texto</button>
        </div>
      )}
      <div className="panel-body" ref={marco}>
        {!explain ? (
          <p className="muted">Ejecuta una consulta con Explain o Explain Analyze para ver su plan.</p>
        ) : vista === 'arbol' ? (
          <div className="hp-lienzo" ref={lienzo} style={{ zoom }}>
            <Rama nodo={explain.tree} analyze={explain.analyze} totalMs={totalMs} />
          </div>
        ) : (
          <pre className="ex-text">{explain.text.join('\n')}</pre>
        )}
      </div>
      {explain && (
        <div className="status">
          Planning Time: {fmt(explain.planningMs, 3)} ms
          {explain.analyze && <> · Execution Time: {fmt(explain.executionMs, 3)} ms</>}
        </div>
      )}
    </section>
  )
}
