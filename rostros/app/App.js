import { StatusBar } from 'expo-status-bar';
import { StyleSheet } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import Reconocer from './src/Reconocer';
import { colores } from './src/tema';

export default function App() {
  return (
    <SafeAreaProvider>
      <SafeAreaView style={estilos.raiz} edges={['top', 'bottom']}>
        <StatusBar style="light" />
        <Reconocer />
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const estilos = StyleSheet.create({
  raiz: { flex: 1, backgroundColor: colores.fondo },
});
