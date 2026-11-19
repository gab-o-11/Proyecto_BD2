import { useEffect, useRef, useState } from 'react';
import { Image, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';

import { reconocer, reducir, urlFoto } from './api';
import Boton from './Boton';
import PermisoCamara from './PermisoCamara';
import { colores } from './tema';

const INTERVALO = 500;

function porcentaje(valor) {
  return valor == null ? '—' : `${Math.round(valor * 100)} %`;
}

function cajasEnVista(resultado, vista, espejo) {
  if (!resultado || !vista.width || !vista.height) {
    return [];
  }
  const escala = Math.max(vista.width / resultado.ancho, vista.height / resultado.alto);
  const dx = (vista.width - resultado.ancho * escala) / 2;
  const dy = (vista.height - resultado.alto * escala) / 2;
  return resultado.caras.map((cara, indice) => {
    const [x, y, ancho, alto] = cara.caja;
    const izquierda = espejo ? resultado.ancho - x - ancho : x;
    return {
      indice,
      cara,
      left: izquierda * escala + dx,
      top: y * escala + dy,
      width: ancho * escala,
      height: alto * escala,
    };
  });
}

export default function Reconocer() {
  const [permiso, pedirPermiso] = useCameraPermissions();
  const camara = useRef(null);
  const [lista, setLista] = useState(false);
  const [lado, setLado] = useState('front');
  const [pausado, setPausado] = useState(false);
  const [usarCache, setUsarCache] = useState(true);
  const [resultado, setResultado] = useState(null);
  const [error, setError] = useState(null);
  const [vista, setVista] = useState({ width: 0, height: 0 });

  useEffect(() => {
    if (!lista || pausado) {
      return undefined;
    }
    let vivo = true;
    async function ciclo() {
      while (vivo) {
        const inicio = Date.now();
        try {
          const foto = await camara.current.takePictureAsync({ quality: 0.5, shutterSound: false });
          const datos = await reconocer(await reducir(foto.uri), usarCache);
          if (vivo) {
            setResultado(datos);
            setError(null);
          }
        } catch (e) {
          if (vivo) {
            setError(e.message);
          }
        }
        const espera = INTERVALO - (Date.now() - inicio);
        if (espera > 0) {
          await new Promise((listo) => setTimeout(listo, espera));
        }
      }
    }
    ciclo();
    return () => {
      vivo = false;
    };
  }, [lista, pausado, usarCache]);

  if (!permiso?.granted) {
    return <PermisoCamara permiso={permiso} pedirPermiso={pedirPermiso} />;
  }

  function girar() {
    setLista(false);
    setResultado(null);
    setLado(lado === 'front' ? 'back' : 'front');
  }

  const cajas = cajasEnVista(resultado, vista, lado === 'front');
  const cacheCaida = resultado?.cache === 'no disponible';
  const desdeCache = resultado?.caras.some((cara) => cara.fuente === 'cache');

  return (
    <View style={estilos.raiz}>
      <View style={estilos.camara} onLayout={(evento) => setVista(evento.nativeEvent.layout)}>
        <CameraView
          key={lado}
          ref={camara}
          style={StyleSheet.absoluteFill}
          facing={lado}
          animateShutter={false}
          onCameraReady={() => setLista(true)}
        />
        {cajas.map((caja) => (
          <View
            key={caja.indice}
            style={[
              estilos.caja,
              {
                left: caja.left,
                top: caja.top,
                width: caja.width,
                height: caja.height,
                borderColor: caja.cara.nombre ? colores.acierto : colores.desconocido,
              },
            ]}
          >
            <Text style={estilos.etiqueta}>{`${caja.cara.nombre ?? 'desconocido'} ${porcentaje(caja.cara.similitud)}`}</Text>
          </View>
        ))}
        <View style={estilos.barra}>
          <Text style={estilos.fuente}>{resultado ? `● ${desdeCache ? 'caché' : 'motor'}` : 'conectando…'}</Text>
          <View style={estilos.botones}>
            <Boton chico titulo="Girar" onPress={girar} />
            <Boton chico titulo={pausado ? 'Seguir' : 'Pausar'} onPress={() => setPausado(!pausado)} />
          </View>
        </View>
      </View>
      <ScrollView style={estilos.panel} contentContainerStyle={estilos.panelContenido}>
        {error && <Text style={estilos.error}>{error}</Text>}
        {resultado && resultado.caras.length === 0 && <Text style={estilos.tenue}>No se detectan rostros</Text>}
        {resultado?.caras.map((cara, indice) => (
          <View key={indice} style={estilos.tarjeta}>
            {cara.foto ? (
              <Image source={{ uri: urlFoto(cara.foto) }} style={estilos.miniatura} />
            ) : (
              <View style={[estilos.miniatura, estilos.sinFoto]}>
                <Text style={estilos.tenue}>?</Text>
              </View>
            )}
            <Text style={estilos.nombre}>{cara.nombre ?? 'desconocido'}</Text>
            <Text style={estilos.texto}>{porcentaje(cara.similitud)}</Text>
            <Text style={estilos.tenue}>{cara.fuente === 'cache' ? 'caché' : 'motor'}</Text>
          </View>
        ))}
        {resultado && (
          <Text style={estilos.tiempos}>
            {`detección ${resultado.tiempos.deteccion} · embedding ${resultado.tiempos.embedding} · caché ${resultado.tiempos.cache}\n`}
            {`motor ${resultado.tiempos.motor} (http ${resultado.tiempos.motor_http}) · total ${resultado.tiempos.total} ms`}
          </Text>
        )}
        <View style={estilos.fila}>
          <Text style={estilos.texto}>{cacheCaida ? 'Caché (Redis no disponible)' : 'Caché'}</Text>
          <Switch value={usarCache && !cacheCaida} disabled={cacheCaida} onValueChange={setUsarCache} />
        </View>
      </ScrollView>
    </View>
  );
}

const estilos = StyleSheet.create({
  raiz: { flex: 1, backgroundColor: colores.fondo },
  camara: { flex: 3, overflow: 'hidden', backgroundColor: '#000' },
  caja: { position: 'absolute', borderWidth: 2, borderRadius: 6 },
  etiqueta: {
    position: 'absolute',
    top: -24,
    left: -2,
    color: '#000',
    backgroundColor: '#ffffffd9',
    paddingHorizontal: 6,
    paddingVertical: 2,
    fontSize: 13,
    fontWeight: '600',
  },
  barra: { position: 'absolute', top: 8, left: 8, right: 8, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  botones: { flexDirection: 'row', gap: 8 },
  fuente: { color: colores.texto, backgroundColor: '#000a', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 },
  panel: { flex: 2 },
  panelContenido: { padding: 12, gap: 8 },
  tarjeta: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: colores.panel, borderRadius: 8, padding: 8 },
  miniatura: { width: 48, height: 48, borderRadius: 6, backgroundColor: colores.borde },
  sinFoto: { alignItems: 'center', justifyContent: 'center' },
  nombre: { flex: 1, color: colores.texto, fontSize: 16, fontWeight: '600' },
  texto: { color: colores.texto },
  tenue: { color: colores.tenue },
  tiempos: { color: colores.tenue, fontSize: 12, fontVariant: ['tabular-nums'] },
  error: { color: colores.peligro },
  fila: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
});
