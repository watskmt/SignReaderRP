/**
 * CameraScreen — main recording screen.
 * Shows the camera feed, start/stop recording button, GPS toggle,
 * and a scrollable overlay of recently extracted texts.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  FlatList,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import {
  Camera,
  useCameraDevice,
  useCameraPermission,
} from 'react-native-vision-camera';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RouteProp } from '@react-navigation/native';

import { useAppContext } from '../context/AppContext';
import type { RootStackParamList } from '../App';
import cameraService from '../services/camera';
import storageService from '../services/storage';
import { createSession, processOCRAsync, getTaskStatus, getExtractions } from '../services/api';

type CameraScreenNavigationProp = NativeStackNavigationProp<
  RootStackParamList,
  'Camera'
>;

interface Props {
  navigation: CameraScreenNavigationProp;
  route: RouteProp<RootStackParamList, 'Camera'>;
}

const FRAME_INTERVAL_MS = 500;
const TASK_POLL_INTERVAL_MS = 800;

export default function CameraScreen({ navigation }: Props): React.JSX.Element {
  const cameraRef = useRef<Camera>(null);
  const device = useCameraDevice('back');
  const { hasPermission, requestPermission } = useCameraPermission();
  const captureIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pendingTasksRef = useRef<Set<string>>(new Set());

  const {
    currentSession,
    extractions,
    isRecording,
    gpsEnabled,
    setCurrentSession,
    addExtraction,
    clearExtractions,
    setRecording,
    setGpsEnabled,
  } = useAppContext();

  const [cameraReady, setCameraReady] = useState(false);
  const [statusMessage, setStatusMessage] = useState('Ready');

  // ──────────────────────────────── Permissions ─────────────────────────────

  useEffect(() => {
    (async () => {
      if (!hasPermission) {
        const granted = await requestPermission();
        if (!granted) {
          Alert.alert(
            'Camera Permission Required',
            'Please grant camera access in Settings to use SignReader.',
          );
        }
      }
    })();
  }, [hasPermission, requestPermission]);

  // ──────────────────────────────── GPS toggle ──────────────────────────────

  const handleGpsToggle = useCallback(async () => {
    if (!gpsEnabled) {
      const hasLocation = await cameraService.requestLocationPermission();
      if (!hasLocation) {
        Alert.alert(
          'Location Permission',
          'Location access was denied. GPS tagging will be disabled.',
        );
        return;
      }
    }
    setGpsEnabled(!gpsEnabled);
  }, [gpsEnabled, setGpsEnabled]);

  // ──────────────────────────────── Session management ──────────────────────

  const ensureSession = useCallback(async () => {
    if (currentSession) {
      return currentSession;
    }
    const now = new Date().toISOString().slice(0, 10);
    const session = await createSession({ title: `Session ${now}` });
    await storageService.saveSession(session);
    await storageService.setCurrentSessionId(session.id);
    setCurrentSession(session);
    return session;
  }, [currentSession, setCurrentSession]);

  // ──────────────────────────────── Task polling ────────────────────────────

  const pollTask = useCallback(
    async (taskId: string, sessionId: string) => {
      const maxAttempts = 20;
      let attempts = 0;

      const poll = async (): Promise<void> => {
        attempts++;
        try {
          const status = await getTaskStatus(taskId);
          if (status.status === 'success' && status.result) {
            const result = status.result as {
              extraction_ids?: string[];
              texts_found?: number;
            };
            setStatusMessage(`Found ${result.texts_found ?? 0} text(s)`);
            pendingTasksRef.current.delete(taskId);

            try {
              const fetched = await getExtractions(sessionId);
              fetched.forEach((ext) => addExtraction({
                id: ext.id,
                session_id: ext.session_id,
                content: ext.content,
                confidence: ext.confidence,
                bounding_box: ext.bounding_box,
                latitude: ext.latitude,
                longitude: ext.longitude,
                altitude: ext.altitude,
                timestamp: ext.timestamp,
                engine: ext.engine,
                is_duplicate: ext.is_duplicate,
              }));
            } catch {
              // extraction fetch failed — data is on server but UI won't update
            }
          } else if (status.status === 'failure') {
            pendingTasksRef.current.delete(taskId);
          } else if (attempts < maxAttempts) {
            setTimeout(poll, TASK_POLL_INTERVAL_MS);
          }
        } catch {
          pendingTasksRef.current.delete(taskId);
        }
      };

      setTimeout(poll, TASK_POLL_INTERVAL_MS);
    },
    [addExtraction],
  );

  // ──────────────────────────────── Frame capture ───────────────────────────

  const handleFrame = useCallback(
    async (frame: string) => {
      try {
        const session = await ensureSession();

        let lat: number | null = null;
        let lon: number | null = null;

        if (gpsEnabled) {
          try {
            const coords = await cameraService.getCurrentLocation();
            lat = coords.latitude;
            lon = coords.longitude;
          } catch {
            // GPS unavailable — continue without coordinates
          }
        }

        const task = await processOCRAsync(frame, session.id, lat, lon);
        pendingTasksRef.current.add(task.task_id);
        void pollTask(task.task_id, session.id);
      } catch (err) {
        console.warn('[CameraScreen] Frame processing error:', err);
        setStatusMessage('Upload error — retrying');
      }
    },
    [ensureSession, gpsEnabled, pollTask],
  );

  // ──────────────────────────────── Record toggle ───────────────────────────

  const handleRecordToggle = useCallback(async () => {
    if (isRecording) {
      // Stop
      if (captureIntervalRef.current !== null) {
        cameraService.stopFrameCapture(captureIntervalRef.current);
        captureIntervalRef.current = null;
      }
      setRecording(false);
      setStatusMessage('Stopped');
    } else {
      // Start
      await ensureSession();
      clearExtractions();
      setRecording(true);
      setStatusMessage('Recording…');

      captureIntervalRef.current = cameraService.startFrameCapture(
        cameraRef,
        FRAME_INTERVAL_MS,
        handleFrame,
      );
    }
  }, [isRecording, ensureSession, clearExtractions, setRecording, handleFrame]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (captureIntervalRef.current !== null) {
        cameraService.stopFrameCapture(captureIntervalRef.current);
      }
    };
  }, []);

  // ──────────────────────────────── Render ──────────────────────────────────

  if (!device) {
    return (
      <View style={styles.container}>
        <Text style={styles.statusText}>No camera device found</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Camera
        ref={cameraRef}
        style={styles.camera}
        device={device}
        isActive={true}
        photo={true}
        onInitialized={() => setCameraReady(true)}
      />

      {/* Overlay panel */}
      <View style={styles.overlay}>
        {/* Status bar */}
        <View style={styles.statusBar}>
          <Text style={styles.statusText}>{statusMessage}</Text>
          <TouchableOpacity
            style={styles.gpsButton}
            onPress={handleGpsToggle}
          >
            <Text style={styles.gpsText}>
              GPS {gpsEnabled ? 'ON' : 'OFF'}
            </Text>
          </TouchableOpacity>
        </View>

        {/* Extracted texts list */}
        <ScrollView style={styles.resultsContainer} nestedScrollEnabled>
          {extractions.length === 0 ? (
            <Text style={styles.emptyText}>
              {isRecording
                ? 'Scanning for text…'
                : 'Tap Record to start scanning'}
            </Text>
          ) : (
            extractions
              .filter((e) => !e.is_duplicate)
              .slice(-10)
              .map((ext) => (
                <View key={ext.id} style={styles.extractionItem}>
                  <Text style={styles.extractionText}>{ext.content}</Text>
                  <Text style={styles.confidenceText}>
                    {Math.round(ext.confidence * 100)}%
                  </Text>
                </View>
              ))
          )}
        </ScrollView>

        {/* Controls */}
        <View style={styles.controls}>
          <TouchableOpacity
            style={[
              styles.recordButton,
              isRecording && styles.recordButtonActive,
              !cameraReady && styles.recordButtonDisabled,
            ]}
            onPress={handleRecordToggle}
            disabled={!cameraReady}
          >
            <Text style={styles.recordButtonText}>
              {isRecording ? 'Stop' : 'Record'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.sessionsButton}
            onPress={() => navigation.navigate('SessionList')}
          >
            <Text style={styles.sessionsButtonText}>Sessions</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  camera: { flex: 1 },
  overlay: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: 'rgba(0,0,0,0.7)',
    paddingBottom: Platform.OS === 'ios' ? 32 : 16,
  },
  statusBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.1)',
  },
  statusText: { color: '#aaa', fontSize: 12 },
  gpsButton: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    backgroundColor: 'rgba(255,255,255,0.15)',
  },
  gpsText: { color: '#fff', fontSize: 12 },
  resultsContainer: {
    maxHeight: 160,
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  emptyText: { color: 'rgba(255,255,255,0.4)', fontSize: 13, textAlign: 'center', paddingVertical: 8 },
  extractionItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 4,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.1)',
  },
  extractionText: { color: '#fff', fontSize: 14, flex: 1 },
  confidenceText: { color: '#4caf50', fontSize: 12, marginLeft: 8 },
  controls: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 24,
    paddingTop: 12,
    gap: 16,
  },
  recordButton: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 10,
    backgroundColor: '#e53935',
    alignItems: 'center',
  },
  recordButtonActive: { backgroundColor: '#666' },
  recordButtonDisabled: { opacity: 0.4 },
  recordButtonText: { color: '#fff', fontWeight: 'bold', fontSize: 16 },
  sessionsButton: {
    paddingVertical: 14,
    paddingHorizontal: 20,
    borderRadius: 10,
    backgroundColor: 'rgba(255,255,255,0.15)',
    alignItems: 'center',
  },
  sessionsButtonText: { color: '#fff', fontSize: 16 },
});
