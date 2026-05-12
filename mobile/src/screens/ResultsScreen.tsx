/**
 * ResultsScreen — displays extractions for a session.
 * Groups by hour, shows confidence badges, keyword filter input, and export.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Platform,
  SectionList,
  Share,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RouteProp } from '@react-navigation/native';

import type { RootStackParamList } from '../App';
import storageService, { ExtractionData } from '../services/storage';
import { getExtractions } from '../services/api';

type ResultsNavigationProp = NativeStackNavigationProp<
  RootStackParamList,
  'Results'
>;

interface Props {
  navigation: ResultsNavigationProp;
  route: RouteProp<RootStackParamList, 'Results'>;
}

interface ExtractionSection {
  title: string;
  data: ExtractionData[];
}

function confidenceColor(confidence: number): string {
  if (confidence >= 0.85) return '#4caf50';
  if (confidence >= 0.65) return '#ff9800';
  return '#f44336';
}

function groupByHour(extractions: ExtractionData[]): ExtractionSection[] {
  const groups: Record<string, ExtractionData[]> = {};

  for (const ext of extractions) {
    const date = new Date(ext.timestamp);
    const key = date.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
    if (!groups[key]) {
      groups[key] = [];
    }
    groups[key].push(ext);
  }

  return Object.entries(groups).map(([title, data]) => ({ title, data }));
}

export default function ResultsScreen({ route }: Props): React.JSX.Element {
  const { sessionId, sessionTitle } = route.params;

  const [extractions, setExtractions] = useState<ExtractionData[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterText, setFilterText] = useState('');
  const [showDuplicates, setShowDuplicates] = useState(false);

  // ──────────────────────────────── Load data ───────────────────────────────

  const loadExtractions = useCallback(async () => {
    setLoading(true);
    try {
      // Try API first, fall back to local storage
      let data: ExtractionData[];
      try {
        const apiData = await getExtractions(sessionId);
        // Save to local storage for offline access
        for (const ext of apiData) {
          await storageService.saveExtraction(ext as ExtractionData);
        }
        data = apiData as ExtractionData[];
      } catch {
        data = await storageService.getExtractions(sessionId);
      }

      // Sort by timestamp ascending
      data.sort(
        (a, b) =>
          new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
      );
      setExtractions(data);
    } catch (err) {
      Alert.alert('Error', 'Failed to load extractions');
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    loadExtractions();
  }, [loadExtractions]);

  // ──────────────────────────────── Filtering ───────────────────────────────

  const filteredExtractions = useMemo(() => {
    let result = extractions.filter((e) => e.confidence > 0.80);

    if (!showDuplicates) {
      result = result.filter((e) => !e.is_duplicate);
    }

    if (filterText.trim()) {
      const lower = filterText.toLowerCase();
      result = result.filter((e) => e.content.toLowerCase().includes(lower));
    }

    return result;
  }, [extractions, showDuplicates, filterText]);

  const sections = useMemo(
    () => groupByHour(filteredExtractions),
    [filteredExtractions],
  );

  // ──────────────────────────────── Export ──────────────────────────────────

  const handleExport = useCallback(async () => {
    try {
      const payload = {
        session: { id: sessionId, title: sessionTitle },
        extractions: filteredExtractions.map((e) => ({
          content: e.content,
          confidence: e.confidence,
          timestamp: e.timestamp,
          latitude: e.latitude,
          longitude: e.longitude,
        })),
        exportedAt: new Date().toISOString(),
      };
      await Share.share({
        message: JSON.stringify(payload, null, 2),
        title: `SignReader — ${sessionTitle}`,
      });
    } catch (err) {
      Alert.alert('Export failed', String(err));
    }
  }, [sessionId, sessionTitle, filteredExtractions]);

  // ──────────────────────────────── Map placeholder ─────────────────────────

  const handleMapPress = useCallback(() => {
    Alert.alert(
      'Map View',
      'Map view will be available in a future update. GPS-tagged extractions can be exported as GeoJSON.',
    );
  }, []);

  // ──────────────────────────────── Render item ─────────────────────────────

  const renderExtraction = ({ item }: { item: ExtractionData }) => (
    <View style={styles.extractionRow}>
      <View style={styles.extractionContent}>
        <Text style={styles.extractionText}>{item.content}</Text>
        {item.latitude != null && (
          <Text style={styles.gpsText}>
            {item.latitude.toFixed(4)}, {item.longitude?.toFixed(4)}
          </Text>
        )}
      </View>
      <View
        style={[
          styles.confidenceBadge,
          { backgroundColor: confidenceColor(item.confidence) + '33' },
        ]}
      >
        <Text
          style={[
            styles.confidenceBadgeText,
            { color: confidenceColor(item.confidence) },
          ]}
        >
          {Math.round(item.confidence * 100)}%
        </Text>
      </View>
    </View>
  );

  const renderSectionHeader = ({ section }: { section: ExtractionSection }) => (
    <View style={styles.sectionHeader}>
      <Text style={styles.sectionTitle}>{section.title}</Text>
      <Text style={styles.sectionCount}>{section.data.length}</Text>
    </View>
  );

  // ──────────────────────────────── Render ──────────────────────────────────

  if (loading) {
    return (
      <View style={styles.loaderContainer}>
        <ActivityIndicator color="#4caf50" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Filter bar */}
      <View style={styles.filterBar}>
        <TextInput
          style={styles.filterInput}
          placeholder="Filter by keyword…"
          placeholderTextColor="#666"
          value={filterText}
          onChangeText={setFilterText}
          clearButtonMode="while-editing"
        />
        <TouchableOpacity
          style={[styles.dupToggle, showDuplicates && styles.dupToggleActive]}
          onPress={() => setShowDuplicates((v) => !v)}
        >
          <Text style={styles.dupToggleText}>Dups</Text>
        </TouchableOpacity>
      </View>

      {/* Stats row */}
      <View style={styles.statsRow}>
        <Text style={styles.statsText}>
          {filteredExtractions.length} result
          {filteredExtractions.length !== 1 ? 's' : ''}
          {filterText ? ` matching "${filterText}"` : ''}
        </Text>
        <View style={styles.statsButtons}>
          <TouchableOpacity onPress={handleMapPress} style={styles.iconButton}>
            <Text style={styles.iconButtonText}>Map</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={handleExport} style={styles.iconButton}>
            <Text style={styles.iconButtonText}>Export</Text>
          </TouchableOpacity>
        </View>
      </View>

      {sections.length === 0 ? (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyText}>
            {filterText
              ? `No results matching "${filterText}"`
              : 'No extractions in this session yet'}
          </Text>
        </View>
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(item) => item.id}
          renderItem={renderExtraction}
          renderSectionHeader={renderSectionHeader}
          contentContainerStyle={styles.list}
          stickySectionHeadersEnabled
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f1a' },
  loaderContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  filterBar: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    gap: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#222',
  },
  filterInput: {
    flex: 1,
    backgroundColor: '#1a1a2e',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    color: '#fff',
    fontSize: 14,
  },
  dupToggle: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: '#333',
  },
  dupToggleActive: { backgroundColor: '#4caf5033' },
  dupToggleText: { color: '#fff', fontSize: 12 },
  statsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  statsText: { color: '#666', fontSize: 12 },
  statsButtons: { flexDirection: 'row', gap: 8 },
  iconButton: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
    backgroundColor: '#1a1a2e',
  },
  iconButtonText: { color: '#aaa', fontSize: 12 },
  list: { paddingBottom: 32 },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#0a0a14',
    paddingHorizontal: 16,
    paddingVertical: 6,
  },
  sectionTitle: { color: '#555', fontSize: 11, fontWeight: '600' },
  sectionCount: {
    color: '#444',
    fontSize: 11,
    backgroundColor: '#1a1a2e',
    paddingHorizontal: 6,
    borderRadius: 8,
  },
  extractionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#151525',
  },
  extractionContent: { flex: 1 },
  extractionText: { color: '#fff', fontSize: 15 },
  gpsText: { color: '#555', fontSize: 10, marginTop: 2 },
  confidenceBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 10,
    marginLeft: 10,
  },
  confidenceBadgeText: { fontSize: 11, fontWeight: '600' },
  emptyContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  emptyText: { color: '#555', fontSize: 15, textAlign: 'center', padding: 24 },
});
