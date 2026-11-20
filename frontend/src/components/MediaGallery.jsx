import { useState } from 'react'
import { urlArchivo } from '../api/client'

const IMAGEN = /\.(jpe?g|png|gif|bmp|webp)$/i
const AUDIO = /\.(mp3|wav|ogg|flac)$/i
const ETIQUETA = /^(clase|categoria|category|label|etiqueta|wnid|genero|genre|artista|artist)$/i
const MAXIMO = 200

function esMultimedia(valor) {
  return typeof valor === 'string' && (IMAGEN.test(valor) || AUDIO.test(valor))
}

export function columnasMultimedia(table) {
  if (!table?.columns || !table.rows?.length) return []
  return table.columns.filter((c) => table.rows.some((r) => esMultimedia(r[c])))
}

export function archivoDeConsulta(sql) {
  const m = /SIMILAR_TO\s*\(\s*'((?:[^']|'')+)'/i.exec(sql || '')
  return m ? m[1].replace(/''/g, "'") : null
}

function nombreArchivo(ruta) {
  return ruta.split('/').pop()
}

function Vista({ ruta }) {
  const [falla, setFalla] = useState(false)
  const [pixelada, setPixelada] = useState(false)
  if (falla) return <div className="media-falla">sin vista previa</div>
  if (AUDIO.test(ruta)) {
    return <audio controls preload="none" src={urlArchivo(ruta)} onError={() => setFalla(true)} />
  }
  return (
    <img
      src={urlArchivo(ruta)}
      alt={nombreArchivo(ruta)}
      title={ruta}
      loading="lazy"
      className={pixelada ? 'pixelada' : undefined}
      onLoad={(e) => setPixelada(e.currentTarget.naturalWidth < 128)}
      onError={() => setFalla(true)}
    />
  )
}

export default function MediaGallery({ table, consulta }) {
  const columna = columnasMultimedia(table)[0]
  if (!columna) return null
  const columnaScore = table.columns.find((c) => /score/i.test(c))
  const columnaEtiqueta = table.columns.find((c) => ETIQUETA.test(c))
  const columnaId = table.columns.find((c) => /^id$/i.test(c))

  const rutaConsulta = archivoDeConsulta(consulta)
  const filaConsulta = rutaConsulta ? table.rows.find((r) => r[columna] === rutaConsulta) : null
  const etiquetaConsulta = filaConsulta && columnaEtiqueta ? filaConsulta[columnaEtiqueta] : null
  const marcar = etiquetaConsulta !== null && etiquetaConsulta !== undefined
  // La propia consulta suele salir primera con score 1: no cuenta como acierto
  const otras = table.rows.filter((r) => r[columna] !== rutaConsulta)
  const aciertos = marcar ? otras.filter((r) => r[columnaEtiqueta] === etiquetaConsulta).length : 0
  const filas = table.rows.slice(0, MAXIMO)
  const metrica = /METRIC\s*=\s*(\w+)/i.exec(consulta || '')?.[1]?.toLowerCase()
  const absoluta = metrica === 'cosine'
  const valorScore = (r) => {
    const v = columnaScore ? r[columnaScore] : null
    return v === null || v === undefined || !Number.isFinite(Number(v)) ? null : Number(v)
  }
  const mejor = Math.max(0, ...filas.map(valorScore).filter((v) => v !== null))
  const proporcion = (v) => Math.min(1, Math.max(0, absoluta ? v : mejor > 0 ? v / mejor : 0))

  return (
    <div className="galeria">
      {rutaConsulta && (
        <figure className="media-card consulta">
          <Vista key={rutaConsulta} ruta={rutaConsulta} />
          <figcaption>
            <strong>Consulta</strong>
            {marcar && <span>{String(etiquetaConsulta)}</span>}
            <span className="ruta" title={rutaConsulta}>{nombreArchivo(rutaConsulta)}</span>
          </figcaption>
        </figure>
      )}
      <div className="galeria-cuerpo">
        {marcar && otras.length > 0 && (
          <p className="galeria-resumen">
            {aciertos} de {otras.length} resultados con {columnaEtiqueta} «{String(etiquetaConsulta)}» (sin contar la propia consulta)
          </p>
        )}
        {table.rows.length > MAXIMO && (
          <p className="galeria-resumen">Se muestran {MAXIMO} de {table.rows.length} filas; el resto está en la tabla.</p>
        )}
        <div className="galeria-resultados">
          {filas.map((r, i) => {
            const ruta = r[columna]
            const propia = ruta === rutaConsulta
            const acierto = marcar && !propia ? r[columnaEtiqueta] === etiquetaConsulta : null
            const clase = ['media-card', propia ? 'propia' : '', acierto === true ? 'acierto' : '', acierto === false ? 'fallo' : '']
            return (
              <figure key={i} className={clase.filter(Boolean).join(' ')}>
                {esMultimedia(ruta) ? <Vista key={ruta} ruta={ruta} /> : <div className="media-falla">sin archivo</div>}
                {valorScore(r) !== null && (
                  <div
                    className="barra-score"
                    title={absoluta
                      ? `coseno ${Math.round(valorScore(r) * 100)} %`
                      : `${Math.round(proporcion(valorScore(r)) * 100)} % del mejor resultado`}
                  >
                    <span style={{ width: `${Math.round(proporcion(valorScore(r)) * 100)}%` }} />
                  </div>
                )}
                <figcaption>
                  <span className="pos">#{i + 1}</span>
                  {columnaScore && r[columnaScore] !== null && r[columnaScore] !== undefined && (
                    <span className="score" title={columnaScore}>{Number(r[columnaScore]).toFixed(3)}</span>
                  )}
                  {acierto !== null && <span className={acierto ? 'marca acierto' : 'marca fallo'}>{acierto ? '✓' : '✗'}</span>}
                  {propia && <span className="marca">consulta</span>}
                  {columnaEtiqueta && <span className="etiqueta">{String(r[columnaEtiqueta])}</span>}
                  {columnaId && <span className="muted">id {String(r[columnaId])}</span>}
                </figcaption>
              </figure>
            )
          })}
        </div>
      </div>
    </div>
  )
}