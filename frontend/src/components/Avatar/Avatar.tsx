import { StyleSheet, Text, View } from "react-native";
import { colors } from "../../theme/colors";
import type { Stats, Streak } from "../../types/api";
import { Card } from "../Layout/Card";

interface AvatarProps {
  name: string;
  level: number;
  xp: number;
  stats: Stats;
  streak: Streak;
}

const XP_PER_LEVEL = 100;

const STAT_LABELS: { key: keyof Stats; label: string }[] = [
  { key: "focus", label: "Focus" },
  { key: "discipline", label: "Discipline" },
  { key: "knowledge", label: "Knowledge" },
  { key: "consistency", label: "Consistency" },
];

export function Avatar({ name, level, xp, stats, streak }: AvatarProps) {
  const xpIntoLevel = xp % XP_PER_LEVEL;

  return (
    <Card>
      <View style={styles.headerRow}>
        <View style={styles.avatarCircle}>
          <Text style={styles.avatarInitial}>{name.charAt(0).toUpperCase()}</Text>
        </View>
        <View style={styles.headerText}>
          <Text style={styles.name}>{name}</Text>
          <Text style={styles.level}>Level {level}</Text>
        </View>
        <View style={styles.streakBadge}>
          <Text style={styles.streakEmoji}>🔥</Text>
          <Text style={styles.streakCount}>{streak.current}</Text>
        </View>
      </View>

      <View style={styles.xpTrack}>
        <View style={[styles.xpFill, { width: `${xpIntoLevel}%` }]} />
      </View>
      <Text style={styles.xpLabel}>
        {xpIntoLevel}/{XP_PER_LEVEL} XP to level {level + 1}
      </Text>

      <View style={styles.statsGrid}>
        {STAT_LABELS.map(({ key, label }) => (
          <View key={key} style={styles.statItem}>
            <Text style={styles.statValue}>{stats[key]}</Text>
            <Text style={styles.statLabel}>{label}</Text>
          </View>
        ))}
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  headerRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  avatarCircle: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarInitial: { color: colors.text, fontSize: 22, fontWeight: "700" },
  headerText: { flex: 1 },
  name: { color: colors.text, fontSize: 18, fontWeight: "700" },
  level: { color: colors.textMuted, fontSize: 13 },
  streakBadge: { flexDirection: "row", alignItems: "center", gap: 4 },
  streakEmoji: { fontSize: 18 },
  streakCount: { color: colors.text, fontSize: 16, fontWeight: "700" },
  xpTrack: { height: 8, borderRadius: 5, backgroundColor: colors.surfaceAlt, overflow: "hidden" },
  xpFill: { height: "100%", backgroundColor: colors.success },
  xpLabel: { color: colors.textMuted, fontSize: 12 },
  statsGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12, marginTop: 4 },
  statItem: { flexBasis: "45%", flexGrow: 1 },
  statValue: { color: colors.text, fontSize: 20, fontWeight: "700" },
  statLabel: { color: colors.textMuted, fontSize: 12 },
});
