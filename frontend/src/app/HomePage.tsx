import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { StyleSheet, Text } from "react-native";
import { useAuth } from "./AuthContext";
import type { MainStackParamList } from "./routes";
import { Avatar } from "../components/Avatar/Avatar";
import { Button } from "../components/Layout/Button";
import { Screen } from "../components/Layout/Screen";
import { colors } from "../theme/colors";

type Props = NativeStackScreenProps<MainStackParamList, "Home">;

export function HomePage({ navigation }: Props) {
  const { user, signOut } = useAuth();
  if (!user) return null;

  return (
    <Screen title={`Hey ${user.name.split(" ")[0]}`} subtitle="Ready to prove some work?">
      <Avatar name={user.name} level={user.level} xp={user.xp} stats={user.stats} streak={user.streak} />

      <Button label="Start a study run" onPress={() => navigation.navigate("Session")} />
      <Button label="I want a break" variant="secondary" onPress={() => navigation.navigate("Break")} />
      <Button label="View progress" variant="secondary" onPress={() => navigation.navigate("Progress")} />
      <Button label="Change coach persona" variant="secondary" onPress={() => navigation.navigate("Persona")} />
      <Text style={styles.signOut} onPress={signOut}>
        Log out
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  signOut: { color: colors.textMuted, textAlign: "center", marginTop: 12, textDecorationLine: "underline" },
});
