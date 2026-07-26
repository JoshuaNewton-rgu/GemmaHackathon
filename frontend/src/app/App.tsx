import { NavigationContainer, DarkTheme } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { ActivityIndicator, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import { AuthProvider, useAuth } from "./AuthContext";
import { HomePage } from "./HomePage";
import type { AuthStackParamList, MainStackParamList } from "./routes";
import { LoginPage } from "../modules/Auth/LoginPage";
import { SignupPage } from "../modules/Auth/SignupPage";
import { BreakPage } from "../modules/Break/BreakPage";
import { ProgressPage } from "../modules/Progress/ProgressPage";
import { PersonaPage } from "../modules/Settings/PersonaPage";
import { SessionPage } from "../modules/Session/SessionPage";
import { colors } from "../theme/colors";

const AuthStack = createNativeStackNavigator<AuthStackParamList>();
const MainStack = createNativeStackNavigator<MainStackParamList>();

const navTheme = {
  ...DarkTheme,
  colors: { ...DarkTheme.colors, background: colors.background, card: colors.surface, primary: colors.primary, text: colors.text, border: colors.border },
};

function RootNavigator() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background }}>
        <ActivityIndicator color={colors.primary} size="large" />
      </View>
    );
  }

  if (!user) {
    return (
      <AuthStack.Navigator screenOptions={{ headerShown: false }}>
        <AuthStack.Screen name="Login" component={LoginPage} />
        <AuthStack.Screen name="Signup" component={SignupPage} />
      </AuthStack.Navigator>
    );
  }

  return (
    <MainStack.Navigator screenOptions={{ headerStyle: { backgroundColor: colors.surface }, headerTintColor: colors.text }}>
      <MainStack.Screen name="Home" component={HomePage} options={{ headerShown: false }} />
      <MainStack.Screen name="Session" component={SessionPage} options={{ title: "Study run" }} />
      <MainStack.Screen name="Break" component={BreakPage} options={{ title: "Break" }} />
      <MainStack.Screen name="Progress" component={ProgressPage} options={{ title: "Progress" }} />
      <MainStack.Screen name="Persona" component={PersonaPage} options={{ title: "Coach persona" }} />
    </MainStack.Navigator>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <NavigationContainer theme={navTheme}>
        <StatusBar style="light" />
        <RootNavigator />
      </NavigationContainer>
    </AuthProvider>
  );
}
