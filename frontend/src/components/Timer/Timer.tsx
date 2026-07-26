import { useEffect, useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { colors } from "../../theme/colors";

interface TimerProps {
  durationMinutes: number;
  isRunning: boolean;
  onComplete: () => void;
}

function formatTime(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60)
    .toString()
    .padStart(2, "0");
  const seconds = Math.floor(totalSeconds % 60)
    .toString()
    .padStart(2, "0");
  return `${minutes}:${seconds}`;
}

export function Timer({ durationMinutes, isRunning, onComplete }: TimerProps) {
  const [secondsLeft, setSecondsLeft] = useState(durationMinutes * 60);
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    setSecondsLeft(durationMinutes * 60);
  }, [durationMinutes]);

  useEffect(() => {
    if (!isRunning) return;

    const interval = setInterval(() => {
      setSecondsLeft((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          onCompleteRef.current();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [isRunning]);

  const progress = 1 - secondsLeft / (durationMinutes * 60);

  return (
    <View style={styles.container}>
      <Text style={styles.time}>{formatTime(secondsLeft)}</Text>
      <View style={styles.track}>
        <View style={[styles.fill, { width: `${Math.min(100, Math.max(0, progress * 100))}%` }]} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: "center", gap: 12 },
  time: { fontSize: 56, fontWeight: "800", color: colors.text, fontVariant: ["tabular-nums"] },
  track: { width: "100%", height: 10, borderRadius: 6, backgroundColor: colors.surfaceAlt, overflow: "hidden" },
  fill: { height: "100%", backgroundColor: colors.primary },
});
