import type { PropsWithChildren } from "react";
import { SafeAreaView, ScrollView, StyleSheet, Text, View } from "react-native";
import { colors } from "../../theme/colors";

interface ScreenProps extends PropsWithChildren {
  title?: string;
  subtitle?: string;
  scroll?: boolean;
}

export function Screen({ title, subtitle, scroll = true, children }: ScreenProps) {
  const Container = scroll ? ScrollView : View;

  return (
    <SafeAreaView style={styles.safeArea}>
      <Container contentContainerStyle={scroll ? styles.scrollContent : undefined} style={styles.flex}>
        {title ? (
          <View style={styles.header}>
            <Text style={styles.title}>{title}</Text>
            {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
          </View>
        ) : null}
        {children}
      </Container>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.background },
  flex: { flex: 1 },
  scrollContent: { padding: 20, paddingBottom: 48, gap: 16 },
  header: { marginBottom: 8, gap: 4 },
  title: { color: colors.text, fontSize: 26, fontWeight: "700" },
  subtitle: { color: colors.textMuted, fontSize: 14 },
});
