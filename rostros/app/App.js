import { useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import MisRostros from './src/MisRostros';
import Persona from './src/Persona';
import Reconocer from './src/Reconocer';
import Registrar from './src/Registrar';
import { colores } from './src/tema';

function Pestana({ titulo, activa, onPress }) {
  return (
    <Pressable style={estilos.pestana} onPress={onPress}>
      <Text style={[estilos.textoPestana, activa && estilos.textoActivo]}>{titulo}</Text>
    </Pressable>
  );
}

export default function App() {
  const [pestana, setPestana] = useState('reconocer');
  const [pantalla, setPantalla] = useState({ tipo: 'lista' });

  function irA(destino) {
    setPestana(destino);
    setPantalla({ tipo: 'lista' });
  }

  const volverALista = () => setPantalla({ tipo: 'lista' });

  let contenido = <Reconocer />;
  if (pestana === 'rostros' && pantalla.tipo === 'persona') {
    contenido = <Persona id={pantalla.id} onVolver={volverALista} />;
  } else if (pestana === 'rostros' && pantalla.tipo === 'registrar') {
    contenido = <Registrar onCancelar={volverALista} onListo={volverALista} onProbar={() => irA('reconocer')} />;
  } else if (pestana === 'rostros') {
    contenido = (
      <MisRostros
        onAbrir={(id) => setPantalla({ tipo: 'persona', id })}
        onRegistrar={() => setPantalla({ tipo: 'registrar' })}
      />
    );
  }

  return (
    <SafeAreaProvider>
      <SafeAreaView style={estilos.raiz} edges={['top', 'bottom']}>
        <StatusBar style="light" />
        <View style={estilos.contenido}>{contenido}</View>
        <View style={estilos.pestanas}>
          <Pestana titulo="Reconocer" activa={pestana === 'reconocer'} onPress={() => irA('reconocer')} />
          <Pestana titulo="Mis rostros" activa={pestana === 'rostros'} onPress={() => irA('rostros')} />
        </View>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const estilos = StyleSheet.create({
  raiz: { flex: 1, backgroundColor: colores.fondo },
  contenido: { flex: 1 },
  pestanas: { flexDirection: 'row', borderTopWidth: 1, borderTopColor: colores.borde },
  pestana: { flex: 1, paddingVertical: 14, alignItems: 'center' },
  textoPestana: { color: colores.tenue, fontWeight: '600' },
  textoActivo: { color: colores.acento },
});
