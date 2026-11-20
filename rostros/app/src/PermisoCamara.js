import { Linking, StyleSheet, Text, View } from 'react-native';

import Boton from './Boton';
import { colores } from './tema';

export default function PermisoCamara({ permiso, pedirPermiso }) {
  if (!permiso) {
    return <View style={estilos.centro} />;
  }
  return (
    <View style={estilos.centro}>
      <Text style={estilos.texto}>La app necesita la cámara para reconocer y registrar rostros.</Text>
      {permiso.canAskAgain ? (
        <Boton titulo="Permitir cámara" onPress={pedirPermiso} />
      ) : (
        <Boton titulo="Abrir Ajustes" onPress={() => Linking.openSettings()} />
      )}
    </View>
  );
}

const estilos = StyleSheet.create({
  centro: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 16, padding: 24, backgroundColor: colores.fondo },
  texto: { color: colores.texto, textAlign: 'center', fontSize: 16 },
});
