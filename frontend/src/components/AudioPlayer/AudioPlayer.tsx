import { Audio } from "expo-av";
import { useEffect, useRef } from "react";
import { StyleSheet, Text, View } from "react-native";
import { speakCoachLine, stopSpeaking } from "../../services/speech";
import { colors } from "../../theme/colors";
import type { CoachMessage } from "../../types/api";

const PERSONA_LABEL: Record<CoachMessage["persona"], string> = {
  scottish_granny: "Scottish Granny",
  disappointed_mother: "Disappointed Mother",
  angry_father: "Angry Father",
};

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:4000";

interface AudioPlayerProps {
  message: CoachMessage;
  autoPlay?: boolean;
}

export function AudioPlayer({ message, autoPlay = true }: AudioPlayerProps) {
  const soundRef = useRef<Audio.Sound | null>(null);

  useEffect(() => {
    if (!autoPlay) return;

    if (message.useDeviceTts || !message.audioUrl) {
      speakCoachLine(message.text, message.persona);
      return () => stopSpeaking();
    }

    let cancelled = false;
    Audio.Sound.createAsync({ uri: `${API_URL}${message.audioUrl}` }, { shouldPlay: true }).then(({ sound }) => {
      if (cancelled) {
        sound.unloadAsync();
        return;
      }
      soundRef.current = sound;
    });

    return () => {
      cancelled = true;
      soundRef.current?.unloadAsync();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [message.text, message.audioUrl]);

  return (
    <View style={styles.bubble}>
      <Text style={styles.persona}>{PERSONA_LABEL[message.persona]}</Text>
      <Text style={styles.text}>&ldquo;{message.text}&rdquo;</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  bubble: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: 16,
    borderTopLeftRadius: 4,
    padding: 14,
    gap: 4,
  },
  persona: { color: colors.primary, fontSize: 12, fontWeight: "700", textTransform: "uppercase" },
  text: { color: colors.text, fontSize: 15, fontStyle: "italic" },
});
