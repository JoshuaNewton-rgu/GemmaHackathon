import { useState } from "react";
import { Pressable, StyleSheet, Text } from "react-native";
import { useAuth } from "../../app/AuthContext";
import { Card } from "../../components/Layout/Card";
import { Screen } from "../../components/Layout/Screen";
import { colors } from "../../theme/colors";
import type { Persona } from "../../types/api";
import { updatePersona } from "./settings.api";

const PERSONAS: { id: Persona; label: string; description: string; emoji: string }[] = [
  { id: "scottish_granny", label: "Scottish Granny", description: "Warm but blunt. Cares about you, won't let you off easy.", emoji: "👵" },
  { id: "disappointed_mother", label: "Disappointed Mother", description: "Soft guilt, lots of care, quietly disappointed.", emoji: "🙍‍♀️" },
  { id: "angry_father", label: "Angry Father", description: "Strict, harsh but fair, believes you can do better.", emoji: "😠" },
];

export function PersonaPage() {
  const { user, refreshUser } = useAuth();
  const [saving, setSaving] = useState<Persona | null>(null);

  async function choose(persona: Persona) {
    setSaving(persona);
    try {
      await updatePersona(persona);
      await refreshUser();
    } finally {
      setSaving(null);
    }
  }

  return (
    <Screen title="Choose your coach" subtitle="This voice will react to every session and break request.">
      {PERSONAS.map((persona) => {
        const isActive = user?.persona === persona.id;
        return (
          <Pressable key={persona.id} onPress={() => choose(persona.id)}>
            <Card style={isActive ? styles.activeCard : undefined}>
              <Text style={styles.emoji}>{persona.emoji}</Text>
              <Text style={styles.label}>{persona.label}</Text>
              <Text style={styles.description}>{persona.description}</Text>
              {saving === persona.id ? <Text style={styles.saving}>Saving…</Text> : null}
              {isActive ? <Text style={styles.active}>Active</Text> : null}
            </Card>
          </Pressable>
        );
      })}
    </Screen>
  );
}

const styles = StyleSheet.create({
  activeCard: { borderColor: colors.primary, borderWidth: 2 },
  emoji: { fontSize: 28 },
  label: { color: colors.text, fontSize: 17, fontWeight: "700" },
  description: { color: colors.textMuted, fontSize: 13 },
  saving: { color: colors.textMuted, fontSize: 12 },
  active: { color: colors.success, fontSize: 12, fontWeight: "700" },
});
