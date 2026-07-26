import { useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";
import { useAuth } from "../../app/AuthContext";
import { Button } from "../../components/Layout/Button";
import { Screen } from "../../components/Layout/Screen";
import { colors } from "../../theme/colors";
import { login } from "./auth.api";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import type { AuthStackParamList } from "../../app/routes";

type Props = NativeStackScreenProps<AuthStackParamList, "Login">;

export function LoginPage({ navigation }: Props) {
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleLogin() {
    setError(null);
    setLoading(true);
    try {
      const { token, user } = await login(email.trim(), password);
      await signIn(token, user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Screen title="Welcome back" subtitle="Log in to keep your streak alive.">
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
        placeholder="Password"
        placeholderTextColor={colors.textMuted}
        secureTextEntry
        value={password}
        onChangeText={setPassword}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Button label="Log in" onPress={handleLogin} loading={loading} disabled={!email || !password} />
      <Button label="Need an account? Sign up" variant="secondary" onPress={() => navigation.navigate("Signup")} />
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
