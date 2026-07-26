import { useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";
import { useAuth } from "../../app/AuthContext";
import { AudioPlayer } from "../../components/AudioPlayer/AudioPlayer";
import { Button } from "../../components/Layout/Button";
import { Card } from "../../components/Layout/Card";
import { Screen } from "../../components/Layout/Screen";
import { Quiz } from "../../components/Quiz/Quiz";
import { Timer } from "../../components/Timer/Timer";
import { UploadButton, type PickedImage } from "../../components/UploadButton/UploadButton";
import { submitQuizAnswers } from "../../services/quiz";
import { colors } from "../../theme/colors";
import type { GradedQuiz, NotesUploadResult, StudySession } from "../../types/api";
import { startSession, uploadNotes } from "./session.api";

const DURATIONS = [30, 45];

type Phase = "setup" | "running" | "uploading" | "result";

export function SessionPage() {
  const { refreshUser } = useAuth();
  const [subject, setSubject] = useState("");
  const [duration, setDuration] = useState(DURATIONS[0]);
  const [session, setSession] = useState<StudySession | null>(null);
  const [phase, setPhase] = useState<Phase>("setup");
  const [result, setResult] = useState<NotesUploadResult | null>(null);
  const [quizResult, setQuizResult] = useState<GradedQuiz | undefined>();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleStart() {
    setError(null);
    setBusy(true);
    try {
      const { session: created } = await startSession(subject.trim(), duration);
      setSession(created);
      setPhase("running");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start session");
    } finally {
      setBusy(false);
    }
  }

  function handleTimerComplete() {
    setPhase("uploading");
  }

  async function handleImagePicked(image: PickedImage) {
    if (!session) return;
    setError(null);
    setBusy(true);
    try {
      const uploadResult = await uploadNotes(session._id, image);
      setResult(uploadResult);
      setPhase("result");
      await refreshUser();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleQuizSubmit(answers: { questionId: string; selectedIndex: number }[]) {
    if (!result) return;
    setBusy(true);
    try {
      const { quiz } = await submitQuizAnswers(result.quiz.id, answers);
      setQuizResult(quiz);
      await refreshUser();
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setSession(null);
    setResult(null);
    setQuizResult(undefined);
    setSubject("");
    setPhase("setup");
  }

  if (phase === "setup") {
    return (
      <Screen title="Start a study run" subtitle="Pick a subject and a block length.">
        <TextInput
          style={styles.input}
          placeholder="Subject (e.g. Organic Chemistry)"
          placeholderTextColor={colors.textMuted}
          value={subject}
          onChangeText={setSubject}
        />
        <View style={styles.durationRow}>
          {DURATIONS.map((d) => (
            <View key={d} style={styles.durationOption}>
              <Button label={`${d} min`} variant={d === duration ? "primary" : "secondary"} onPress={() => setDuration(d)} />
            </View>
          ))}
        </View>
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <Button label="Start run" onPress={handleStart} disabled={!subject.trim()} loading={busy} />
      </Screen>
    );
  }

  if (phase === "running" && session) {
    return (
      <Screen title={session.subject} subtitle="Stay heads down. Notes go up when the timer ends.">
        <Timer durationMinutes={session.plannedDurationMinutes} isRunning onComplete={handleTimerComplete} />
        <Button label="Time's up early - upload now" variant="secondary" onPress={() => setPhase("uploading")} />
      </Screen>
    );
  }

  if (phase === "uploading" && session) {
    return (
      <Screen title="Show your notes" subtitle="Photograph or upload the notes you just wrote.">
        <UploadButton onPicked={handleImagePicked} disabled={busy} />
        {busy ? <Text style={styles.muted}>Analysing your notes with Gemma 4…</Text> : null}
        {error ? <Text style={styles.error}>{error}</Text> : null}
      </Screen>
    );
  }

  if (phase === "result" && result) {
    return (
      <Screen title="Session complete" subtitle={`Progress Score: ${result.progressBreakdown.score}/100`}>
        <AudioPlayer message={result.coachMessage} />
        <Card>
          <Text style={styles.scoreLine}>+{result.xpAwarded} XP</Text>
          <Text style={styles.muted}>
            Volume {result.progressBreakdown.volumeScore} · New concepts {result.progressBreakdown.newConceptsScore} ·
            Completion {result.progressBreakdown.completionScore}
          </Text>
        </Card>

        <Text style={styles.quizHeading}>Quick recall check</Text>
        <Quiz quiz={result.quiz} onSubmit={handleQuizSubmit} submitting={busy} result={quizResult} />

        {quizResult ? <Button label="Start another run" onPress={reset} /> : null}
      </Screen>
    );
  }

  return null;
}

const styles = StyleSheet.create({
  input: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    padding: 14,
    color: colors.text,
    fontSize: 15,
  },
  durationRow: { flexDirection: "row", gap: 12 },
  durationOption: { flex: 1 },
  error: { color: colors.danger, fontSize: 13 },
  muted: { color: colors.textMuted, fontSize: 13, textAlign: "center" },
  scoreLine: { color: colors.success, fontSize: 20, fontWeight: "700" },
  quizHeading: { color: colors.text, fontSize: 18, fontWeight: "700", marginTop: 8 },
});
