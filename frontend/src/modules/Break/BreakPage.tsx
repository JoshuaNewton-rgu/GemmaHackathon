import { useState } from "react";
import { StyleSheet, Text, TextInput } from "react-native";
import { useAuth } from "../../app/AuthContext";
import { AudioPlayer } from "../../components/AudioPlayer/AudioPlayer";
import { Button } from "../../components/Layout/Button";
import { Card } from "../../components/Layout/Card";
import { Screen } from "../../components/Layout/Screen";
import { Quiz } from "../../components/Quiz/Quiz";
import { colors } from "../../theme/colors";
import type { BreakAnswerResult, Quiz as QuizData } from "../../types/api";
import { generateBreakQuiz, submitBreakAnswers } from "./break.api";

type Phase = "request" | "quiz" | "result";

export function BreakPage() {
  const { refreshUser } = useAuth();
  const [subject, setSubject] = useState("");
  const [quiz, setQuiz] = useState<QuizData | null>(null);
  const [phase, setPhase] = useState<Phase>("request");
  const [outcome, setOutcome] = useState<BreakAnswerResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleRequestBreak() {
    setError(null);
    setBusy(true);
    try {
      const { quiz: created } = await generateBreakQuiz(subject.trim());
      setQuiz(created);
      setPhase("quiz");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start break quiz");
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit(answers: { questionId: string; selectedIndex: number }[]) {
    if (!quiz) return;
    setBusy(true);
    try {
      const submitted = await submitBreakAnswers(quiz.id, answers);
      setOutcome(submitted);
      setPhase("result");
      await refreshUser();
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setSubject("");
    setQuiz(null);
    setOutcome(null);
    setPhase("request");
  }

  if (phase === "request") {
    return (
      <Screen title="Want a break?" subtitle="Answer 5 questions from your own notes to earn it.">
        <TextInput
          style={styles.input}
          placeholder="Which subject's notes should we quiz you on?"
          placeholderTextColor={colors.textMuted}
          value={subject}
          onChangeText={setSubject}
        />
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <Button label="Generate break quiz" onPress={handleRequestBreak} disabled={!subject.trim()} loading={busy} />
      </Screen>
    );
  }

  if (phase === "quiz" && quiz) {
    return (
      <Screen title="Earn your break" subtitle="Need at least 3/5 correct.">
        <Quiz quiz={quiz} onSubmit={handleSubmit} submitting={busy} />
      </Screen>
    );
  }

  if (phase === "result" && outcome) {
    return (
      <Screen title={outcome.passed ? "Break unlocked!" : "Not yet"}>
        <AudioPlayer message={outcome.coachMessage} />
        <Card>
          <Text style={[styles.resultHeading, { color: outcome.passed ? colors.success : colors.danger }]}>
            {outcome.quiz.correctCount}/{outcome.quiz.questions.length} correct
          </Text>
          <Text style={styles.muted}>
            {outcome.passed
              ? `Enjoy your ${outcome.breakMinutes} minute break.`
              : `Take a ${outcome.breakMinutes} minute review break, then try again.`}
          </Text>
          <Text style={styles.muted}>+{outcome.xpAwarded} XP</Text>
        </Card>
        <Button label="Done" onPress={reset} />
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
  error: { color: colors.danger, fontSize: 13 },
  muted: { color: colors.textMuted, fontSize: 13 },
  resultHeading: { fontSize: 22, fontWeight: "800" },
});
