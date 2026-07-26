import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useAuth } from "../../app/AuthContext";
import { Avatar } from "../../components/Avatar/Avatar";
import { Card } from "../../components/Layout/Card";
import { Screen } from "../../components/Layout/Screen";
import { colors } from "../../theme/colors";
import type { StudySession } from "../../types/api";
import { listSessions } from "./progress.api";

function ScoreBar({ score }: { score: number | null }) {
  return (
    <View style={styles.barTrack}>
      <View style={[styles.barFill, { height: `${score ?? 0}%`, backgroundColor: barColor(score) }]} />
    </View>
  );
}

function barColor(score: number | null): string {
  if (score === null) return colors.border;
  if (score >= 70) return colors.success;
  if (score >= 40) return colors.warning;
  return colors.danger;
}

export function ProgressPage() {
  const { user } = useAuth();
  const [sessions, setSessions] = useState<StudySession[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listSessions()
      .then(({ sessions: s }) => setSessions(s))
      .finally(() => setLoading(false));
  }, []);

  const completed = sessions.filter((s) => s.status === "completed");
  const totalMinutes = completed.reduce((sum, s) => sum + s.plannedDurationMinutes, 0);
  const recentForChart = [...completed].slice(0, 10).reverse();

  if (!user) return null;

  return (
    <Screen title="Your progress" subtitle="Levels, streaks, and receipts.">
      <Avatar name={user.name} level={user.level} xp={user.xp} stats={user.stats} streak={user.streak} />

      <Card>
        <View style={styles.summaryRow}>
          <View>
            <Text style={styles.summaryValue}>{completed.length}</Text>
            <Text style={styles.summaryLabel}>Sessions completed</Text>
          </View>
          <View>
            <Text style={styles.summaryValue}>{(totalMinutes / 60).toFixed(1)}h</Text>
            <Text style={styles.summaryLabel}>Total study time</Text>
          </View>
          <View>
            <Text style={styles.summaryValue}>{user.streak.longest}</Text>
            <Text style={styles.summaryLabel}>Longest streak</Text>
          </View>
        </View>
      </Card>

      <Card>
        <Text style={styles.cardTitle}>Progress Score - last {recentForChart.length} sessions</Text>
        {loading ? (
          <Text style={styles.muted}>Loading…</Text>
        ) : recentForChart.length === 0 ? (
          <Text style={styles.muted}>Complete a session to see your first bar here.</Text>
        ) : (
          <View style={styles.chartRow}>
            {recentForChart.map((s) => (
              <ScoreBar key={s._id} score={s.progressScore} />
            ))}
          </View>
        )}
      </Card>

      <Card>
        <Text style={styles.cardTitle}>Achievements</Text>
        {user.achievements.length === 0 ? (
          <Text style={styles.muted}>No achievements unlocked yet - keep proving your work.</Text>
        ) : (
          user.achievements.map((a) => (
            <Text key={a} style={styles.achievement}>
              🏆 {a}
            </Text>
          ))
        )}
      </Card>
    </Screen>
  );
}

const styles = StyleSheet.create({
  summaryRow: { flexDirection: "row", justifyContent: "space-between" },
  summaryValue: { color: colors.text, fontSize: 22, fontWeight: "800" },
  summaryLabel: { color: colors.textMuted, fontSize: 12 },
  cardTitle: { color: colors.text, fontSize: 15, fontWeight: "700" },
  muted: { color: colors.textMuted, fontSize: 13 },
  chartRow: { flexDirection: "row", alignItems: "flex-end", gap: 6, height: 100 },
  barTrack: { flex: 1, height: "100%", justifyContent: "flex-end", backgroundColor: colors.surfaceAlt, borderRadius: 4, overflow: "hidden" },
  barFill: { width: "100%", borderRadius: 4 },
  achievement: { color: colors.text, fontSize: 14 },
});
