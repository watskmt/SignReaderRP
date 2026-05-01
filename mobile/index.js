/**
 * SignReader — app entry point
 * Registers the root React Native component with AppRegistry.
 */
import { AppRegistry } from 'react-native';
import App from './src/App';
import { name as appName } from './app.json';

AppRegistry.registerComponent(appName, () => App);
