/**
 * SignReader App — root navigation component.
 * Wraps the app in AppProvider and sets up a Stack.Navigator with 3 screens.
 */
import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AppProvider } from './context/AppContext';
import CameraScreen from './screens/CameraScreen';
import SessionListScreen from './screens/SessionListScreen';
import ResultsScreen from './screens/ResultsScreen';

// ─────────────────────────────── Navigation types ────────────────────────────

export type RootStackParamList = {
  Camera: undefined;
  SessionList: undefined;
  Results: { sessionId: string; sessionTitle: string };
};

const Stack = createStackNavigator<RootStackParamList>();

// ─────────────────────────────── App ─────────────────────────────────────────

export default function App(): React.JSX.Element {
  return (
    <SafeAreaProvider>
      <AppProvider>
        <NavigationContainer>
          <Stack.Navigator
            initialRouteName="Camera"
            screenOptions={{
              headerStyle: { backgroundColor: '#1a1a2e' },
              headerTintColor: '#ffffff',
              headerTitleStyle: { fontWeight: 'bold' },
            }}
          >
            <Stack.Screen
              name="Camera"
              component={CameraScreen}
              options={{ title: 'Pi Monitor' }}
            />
            <Stack.Screen
              name="SessionList"
              component={SessionListScreen}
              options={{ title: 'Sessions' }}
            />
            <Stack.Screen
              name="Results"
              component={ResultsScreen}
              options={({ route }) => ({ title: route.params.sessionTitle })}
            />
          </Stack.Navigator>
        </NavigationContainer>
      </AppProvider>
    </SafeAreaProvider>
  );
}
