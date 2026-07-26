import { useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { colors } from "../../theme/colors";
import type { GradedQuiz, Quiz as QuizData } from "../../types/api";
import { Button } from "../Layout/Button";
import { Card } from "../Layout/Card";

interface QuizProps {
  quiz: QuizData;
  onSubmit: (answers: { questionId: string; selectedIndex: number }[]) => void;
  submitting?: boolean;
  result?: GradedQuiz;
}

export function Quiz({ quiz, onSubmit, submitting, result }: QuizProps) {
  const [selections, setSelections] = useState<Record<string, number>>({});

  const allAnswered = useMemo(
    () => quiz.questions.every((q) => selections[q.id] !== undefined),
    [quiz.questions, selections],
  );

  function select(questionId: string, index: number) {
    if (result) return; // already graded
    setSelections((prev) => ({ ...prev, [questionId]: index }));
  }

  function submit() {
    onSubmit(quiz.questions.map((q) => ({ questionId: q.id, selectedIndex: selections[q.id] })));
  }

  return (
    <View style={styles.container}>
      {quiz.questions.map((question, idx) => {
        const graded = result?.questions.find((q) => q.id === question.id);
        return (
          <Card key={question.id}>
            <Text style={styles.questionLabel}>
              Q{idx + 1} · {question.type.replace("_", " ")}
            </Text>
            <Text style={styles.questionPrompt}>{question.prompt}</Text>
            <View style={styles.choices}>
              {question.choices.map((choice, choiceIdx) => {
                const isSelected = selections[question.id] === choiceIdx;
                const isCorrect = graded && graded.correctIndex === choiceIdx;
                const isWrongSelected = graded && graded.selectedIndex === choiceIdx && !isCorrect;

                return (
                  <Pressable
                    key={choiceIdx}
                    onPress={() => select(question.id, choiceIdx)}
                    style={[
                      styles.choice,
                      isSelected && !graded && styles.choiceSelected,
                      isCorrect && styles.choiceCorrect,
                      isWrongSelected && styles.choiceWrong,
                    ]}
                  >
                    <Text style={styles.choiceText}>{choice}</Text>
                  </Pressable>
                );
              })}
            </View>
          </Card>
        );
      })}

      {!result ? (
        <Button label="Submit answers" onPress={submit} disabled={!allAnswered} loading={submitting} />
      ) : (
        <Card>
          <Text style={styles.resultText}>
            {result.correctCount}/{result.questions.length} correct {result.passed ? "🎉" : ""}
          </Text>
        </Card>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 12 },
  questionLabel: { color: colors.textMuted, fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5 },
  questionPrompt: { color: colors.text, fontSize: 16, fontWeight: "600" },
  choices: { gap: 8 },
  choice: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: colors.surfaceAlt,
  },
  choiceSelected: { borderColor: colors.primary, backgroundColor: colors.primaryDark },
  choiceCorrect: { borderColor: colors.success, backgroundColor: "#1F3A2A" },
  choiceWrong: { borderColor: colors.danger, backgroundColor: "#3A1F1F" },
  choiceText: { color: colors.text, fontSize: 14 },
  resultText: { color: colors.text, fontSize: 18, fontWeight: "700", textAlign: "center" },
});
