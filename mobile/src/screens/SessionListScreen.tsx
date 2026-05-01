/**
 * SessionListScreen — displays all sessions from local storage,
 * with pull-to-refresh, session creation modal, and tap-to-view-results.
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RouteProp } from '@react-navigation/native';

import type { RootStackParamList } from '../App';
import storageService, { SessionData } from '../services/storage';
import { createSession } from '../services/api';
import { useAppContext } from '../context/AppContext';

type SessionListNavigationProp = NativeStackNavigationProp<
  RootStackParamList,
  'SessionList'
>;

interface Props {
  navigation: SessionListNavigationProp;
  route: RouteProp<RootStackParamList, 'SessionList'>;
}

interface SessionWithCount extends SessionData {
  extractionCount: number;
}

export default function SessionListScreen({ navigation }: Props): React.JSX.Element {
  const [sessions, setSessions] = useState<SessionWithCount[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [creating, setCreating] = useState(false);

  const { setCurrentSession, clearExtractions } = useAppContext();

  // ──────────────────────────────── Load sessions ───────────────────────────

  const loadSessions = useCallback(async () => {
    setLoading(true);
    try {
      const stored = await storageService.getAllSessions();
      const withCounts: SessionWithCount[] = await Promise.all(
        stored.map(async (s) => {
          const extractions = await storageService.getExtractions(s.id);
          return { ...s, extractionCount: extractions.length };
        }),
      );
      // Newest first
      withCounts.sort(
        (a, b) =>
          new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
      );
      setSessions(withCounts);
    } catch (err) {
      Alert.alert('Error', 'Failed to load sessions');
    } finally {
      setLoading(false);
    }
  }, []);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await loadSessions();
    setRefreshing(false);
  }, [loadSessions]);

  useEffect(() => {
    const unsubscribe = navigation.addListener('focus', loadSessions);
    return unsubscribe;
  }, [navigation, loadSessions]);

  // ──────────────────────────────── Create session ──────────────────────────

  const handleCreateSession = useCallback(async () => {
    const title = newTitle.trim();
    if (!title) {
      Alert.alert('Validation', 'Please enter a session title');
      return;
    }

    setCreating(true);
    try {
      const session = await createSession({ title });
      await storageService.saveSession(session);
      setCurrentSession(session);
      clearExtractions();
      setShowModal(false);
      setNewTitle('');
      navigation.navigate('Camera');
    } catch (err) {
      Alert.alert('Error', 'Failed to create session. Check your connection.');
    } finally {
      setCreating(false);
    }
  }, [newTitle, setCurrentSession, clearExtractions, navigation]);

  // ──────────────────────────────── Render item ─────────────────────────────

  const renderItem = ({ item }: { item: SessionWithCount }) => {
    const date = new Date(item.started_at);
    const dateStr = date.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
    const timeStr = date.toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
    });

    return (
      <TouchableOpacity
        style={styles.sessionCard}
        onPress={() =>
          navigation.navigate('Results', {
            sessionId: item.id,
            sessionTitle: item.title,
          })
        }
        activeOpacity={0.7}
      >
        <View style={styles.cardLeft}>
          <Text style={styles.sessionTitle} numberOfLines={1}>
            {item.title}
          </Text>
          <Text style={styles.sessionMeta}>
            {dateStr} at {timeStr}
          </Text>
        </View>
        <View style={styles.cardRight}>
          <View
            style={[
              styles.statusBadge,
              item.status === 'active'
                ? styles.statusActive
                : styles.statusComplete,
            ]}
          >
            <Text style={styles.statusBadgeText}>{item.status}</Text>
          </View>
          <Text style={styles.countText}>{item.extractionCount} texts</Text>
        </View>
      </TouchableOpacity>
    );
  };

  // ──────────────────────────────── Render ──────────────────────────────────

  return (
    <View style={styles.container}>
      {loading && sessions.length === 0 ? (
        <ActivityIndicator style={styles.loader} color="#4caf50" />
      ) : (
        <FlatList
          data={sessions}
          keyExtractor={(item) => item.id}
          renderItem={renderItem}
          refreshing={refreshing}
          onRefresh={handleRefresh}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <Text style={styles.emptyText}>
              No sessions yet. Tap "New Session" to start recording.
            </Text>
          }
        />
      )}

      <TouchableOpacity
        style={styles.newButton}
        onPress={() => setShowModal(true)}
      >
        <Text style={styles.newButtonText}>+ New Session</Text>
      </TouchableOpacity>

      {/* Create session modal */}
      <Modal
        visible={showModal}
        transparent
        animationType="slide"
        onRequestClose={() => setShowModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>New Session</Text>
            <TextInput
              style={styles.modalInput}
              placeholder="Session title"
              placeholderTextColor="#999"
              value={newTitle}
              onChangeText={setNewTitle}
              autoFocus
              returnKeyType="done"
              onSubmitEditing={handleCreateSession}
            />
            <View style={styles.modalButtons}>
              <TouchableOpacity
                style={styles.cancelButton}
                onPress={() => {
                  setShowModal(false);
                  setNewTitle('');
                }}
              >
                <Text style={styles.cancelButtonText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.createButton, creating && styles.buttonDisabled]}
                onPress={handleCreateSession}
                disabled={creating}
              >
                <Text style={styles.createButtonText}>
                  {creating ? 'Creating…' : 'Create'}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f1a' },
  loader: { flex: 1 },
  list: { padding: 16, paddingBottom: 100 },
  sessionCard: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#1a1a2e',
    borderRadius: 10,
    padding: 14,
    marginBottom: 10,
  },
  cardLeft: { flex: 1 },
  sessionTitle: { color: '#fff', fontSize: 16, fontWeight: '600', marginBottom: 4 },
  sessionMeta: { color: '#888', fontSize: 12 },
  cardRight: { alignItems: 'flex-end', gap: 4 },
  statusBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  statusActive: { backgroundColor: 'rgba(76,175,80,0.2)' },
  statusComplete: { backgroundColor: 'rgba(158,158,158,0.2)' },
  statusBadgeText: { color: '#4caf50', fontSize: 10, fontWeight: '600' },
  countText: { color: '#888', fontSize: 12 },
  emptyText: { color: '#555', textAlign: 'center', marginTop: 60, fontSize: 15 },
  newButton: {
    position: 'absolute',
    bottom: Platform.OS === 'ios' ? 32 : 16,
    left: 24,
    right: 24,
    backgroundColor: '#e53935',
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
  },
  newButtonText: { color: '#fff', fontWeight: 'bold', fontSize: 16 },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'flex-end',
  },
  modalCard: {
    backgroundColor: '#1a1a2e',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 24,
    paddingBottom: Platform.OS === 'ios' ? 40 : 24,
  },
  modalTitle: { color: '#fff', fontSize: 18, fontWeight: 'bold', marginBottom: 16 },
  modalInput: {
    borderWidth: 1,
    borderColor: '#333',
    borderRadius: 8,
    color: '#fff',
    padding: 12,
    fontSize: 15,
    marginBottom: 16,
    backgroundColor: '#111',
  },
  modalButtons: { flexDirection: 'row', gap: 12 },
  cancelButton: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 8,
    backgroundColor: '#333',
    alignItems: 'center',
  },
  cancelButtonText: { color: '#fff' },
  createButton: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 8,
    backgroundColor: '#e53935',
    alignItems: 'center',
  },
  createButtonText: { color: '#fff', fontWeight: 'bold' },
  buttonDisabled: { opacity: 0.5 },
});
