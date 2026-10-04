import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { runQuery } from '../api/client'

const geographic = p => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite)
  && Math.abs(p[0]) <= 90 && Math.abs(p[1]) <= 180
const key = p => p.join(',')

export default function MapPanel({ tables, result, dataVersion, location, onLocation }) {
  const container = useRef(null)
  const map = useRef(null)
  const layers = useRef(null)
  const center = useRef(null)
  const [selected, setSelected] = useState('')
  const [points, setPoints] = useState([])
  const [error, setError] = useState('')
  const options = tables.flatMap(t => t.columns.filter(c => c.type.toLowerCase() === 'point')
    .map(c => ({ value: JSON.stringify([t.name, c.name]), label: `${t.name}.${c.name}` })))
  const statement = [...(result?.statements || [])].reverse().find(s => s.spatial)
  const spatial = result?.error ? [] : statement?.spatial || []
  const [table, column] = selected ? JSON.parse(selected) : ['', '']
  const matched = spatial.find(s => s.table === table && s.column === column)?.points || []
  const highlighted = matched.filter(geographic)

  useEffect(() => {
    const first = spatial[0]
    const preferred = first ? JSON.stringify([first.table, first.column]) : selected
    setSelected(options.some(o => o.value === preferred) ? preferred : options[0]?.value || '')
  }, [tables, result])

  useEffect(() => {
    const instance = L.map(container.current, { preferCanvas: true }).setView([-12.0464, -77.0428], 12)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(instance)
    map.current = instance
    layers.current = L.layerGroup().addTo(instance)
    const observer = new ResizeObserver(() => instance.invalidateSize())
    observer.observe(container.current)
    return () => { observer.disconnect(); instance.remove() }
  }, [])

  useEffect(() => {
    const instance = map.current
    const click = e => onLocation([e.latlng.lat, e.latlng.lng])
    instance.on('click', click)
    return () => instance.off('click', click)
  }, [onLocation])

  useEffect(() => {
    if (center.current) center.current.remove()
    if (geographic(location)) {
      center.current = L.circleMarker(location, { radius: 7, color: '#682ca4', fillOpacity: 0.8 })
        .bindTooltip('mi_ubicacion').addTo(map.current)
    }
  }, [location])

  useEffect(() => {
    let active = true
    setPoints([])
    setError('')
    if (table) runQuery(`SELECT ${column} FROM ${table};`).then(response => {
      if (!active) return
      setError(response.error || '')
      setPoints((response.rows || []).map(row => row[column]))
    })
    return () => { active = false }
  }, [selected, dataVersion])

  useEffect(() => {
    layers.current.clearLayers()
    const chosen = new Set(highlighted.map(key))
    const visible = points.filter(geographic)
    for (const p of visible) {
      if (chosen.has(key(p))) continue
      L.circleMarker(p, { radius: 3, weight: 1, color: '#287cba', fillOpacity: 0.45 })
        .bindPopup(`${p[0]}, ${p[1]}`).addTo(layers.current)
    }
    for (const p of highlighted) {
      L.circleMarker(p, { radius: 6, weight: 2, color: '#d54a14', fillOpacity: 0.9 })
        .bindPopup(`Resultado: ${p[0]}, ${p[1]}`).addTo(layers.current)
    }
    const focus = highlighted.length ? highlighted : visible
    if (focus.length) map.current.fitBounds(L.latLngBounds(focus), { padding: [20, 20], maxZoom: 16 })
  }, [points, result, selected])

  return <section className="panel spatial-map">
    <h2>Mapa espacial</h2>
    <div className="toolbar map-toolbar">
      <label>Datos <select aria-label="Columna espacial" value={selected} onChange={e => setSelected(e.target.value)}>
        {!options.length && <option value="">Sin columnas POINT</option>}
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select></label>
      <label>Latitud <input aria-label="Latitud" type="number" min="-90" max="90" step="any" value={location[0]}
        onChange={e => { if (e.target.value !== '') onLocation([Number(e.target.value), location[1]]) }} /></label>
      <label>Longitud <input aria-label="Longitud" type="number" min="-180" max="180" step="any" value={location[1]}
        onChange={e => { if (e.target.value !== '') onLocation([location[0], Number(e.target.value)]) }} /></label>
      <span className="muted">Clic en el mapa para fijar mi_ubicacion</span>
    </div>
    <div ref={container} className="map-canvas" aria-label="Mapa interactivo de puntos y resultados" />
    <div className="status">{error || `${points.filter(geographic).length} puntos · azul: tabla · ${highlighted.length} resultados en naranja · mi_ubicacion violeta`}
      {points.some(p => !geographic(p)) && ' · Se omiten coordenadas fuera del rango geográfico'}
    </div>
  </section>
}
