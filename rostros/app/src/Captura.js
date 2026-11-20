import { useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';

import { reducir } from './api';
import Boton from './Boton';
import PermisoCamara from './PermisoCamara';
import { colores } from './tema';

export default function Captura({ instruccion, onFoto, onCancelar }) {
  const [permiso, pedirPermiso] = useCameraPermissions();
  const camara = useRef(null);
  const [lista, setLista] = useState(false);
  const [tomando, setTomando] = useState(false);

  if (!permiso?.granted) {
    return <PermisoCamara permiso={permiso} pedirPermiso={pedirPermiso} />;
  }

  async function tomar() {
    if (!lista || tomando) {
      return;
    }
    setTomando(true);
    try {
      const foto = await camara.current.takePictureAsync({ quality: 0.7, shutterSound: false });
      onFoto(await reducir(foto.uri));
    } finally {
      setTomando(false);
    }
  }

  return (
    <View style={estilos.raiz}>
      <View style={estilos.marco}>
        <CameraView ref={camara} style={StyleSheet.absoluteFill} facing="front" onCameraReady={() => setLista(true)} />
      </View>
      <Text style={estilos.instruccion}>{instruccion}</Text>
      <View style={estilos.fila}>
        <Boton titulo="Cancelar" onPress={onCancelar} />
        <Boton titulo={tomando ? 'Tomando…' : 'Tomar foto'} onPress={tomar} desactivado={!lista || tomando} />
      </View>
    </View>
  );
}

const estilos = StyleSheet.create({
  raiz: { flex: 1, backgroundColor: colores.fondo, padding: 12, gap: 12 },
  marco: { flex: 1, borderRadius: 12, overflow: 'hidden', backgroundColor: '#000' },
  instruccion: { color: colores.texto, fontSize: 18, textAlign: 'center', fontWeight: '600' },
  fila: { flexDirection: 'row', justifyContent: 'space-between', gap: 12 },
});
