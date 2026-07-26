import { useState } from "react";
import { StyleSheet, Text, TextInput } from "react-native";
import { useAuth } from "../../app/AuthContext";
import { Button } from "../../components/Layout/Button";
import { Screen } from "../../components/Layout/Screen";
import { colors } from "../../theme/colors";
import { register } from "./auth.api";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import type { AuthStackParamList } from "../../app/routes";

type Props = NativeStackScreenProps<AuthStackParamList, "Signup">;

export function SignupPage({ navigation }: Props) {
  const { signIn } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSignup() {
    setError(null);
    setLoading(true);
    try {
      const { token, user } = await register(email.trim(), password, name.trim());
      await signIn(token, user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign up failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Screen title="Create your account" subtitle="Pick a coach persona once you're in.">
      <TextInput style={styles.input} placeholder="Name" placeholderTextColor={colors.textMuted} value={name} onChangeText={setName} />
      <TextInput
        style={styles.input}
        placeholder="Email"
        placeholderTextColor={colors.textMuted}
        autoCapitalize="none"
        keyboardType="email-address"
        value={email}
        onChangeText={setEmail}
      />
      <TextInput
        style={styles.input}
        placeholder="Password (min 8 characters)"
        placeholderTextColor={colors.textMuted}
        secureTextEntry
        value={password}
        onChangeText={setPassword}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Button label="Sign up" onPress={handleSignup} loading={loading} disabled={!email || !password || !name} />
      <Button label="Already have an account? Log in" variant="secondary" onPress={() => navigation.navigate("Login")} />
    </Screen>
  );
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
});
