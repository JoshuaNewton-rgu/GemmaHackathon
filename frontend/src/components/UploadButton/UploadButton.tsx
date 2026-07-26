import * as ImagePicker from "expo-image-picker";
import { useState } from "react";
import { Alert, StyleSheet, View } from "react-native";
import { Button } from "../Layout/Button";

export interface PickedImage {
  uri: string;
  mimeType: string;
  fileName: string;
}

interface UploadButtonProps {
  onPicked: (image: PickedImage) => void;
  disabled?: boolean;
}

function toPickedImage(asset: ImagePicker.ImagePickerAsset): PickedImage {
  return {
    uri: asset.uri,
    mimeType: asset.mimeType ?? "image/jpeg",
    fileName: asset.fileName ?? `notes-${Date.now()}.jpg`,
  };
}

export function UploadButton({ onPicked, disabled }: UploadButtonProps) {
  const [busy, setBusy] = useState(false);

  async function fromCamera() {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      Alert.alert("Camera permission needed", "Enable camera access to photograph your notes.");
      return;
    }
    setBusy(true);
    try {
      const result = await ImagePicker.launchCameraAsync({ quality: 0.7 });
      if (!result.canceled) onPicked(toPickedImage(result.assets[0]));
    } finally {
      setBusy(false);
    }
  }

  async function fromLibrary() {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert("Photo library permission needed", "Enable photo access to upload a picture of your notes.");
      return;
    }
    setBusy(true);
    try {
      const result = await ImagePicker.launchImageLibraryAsync({ quality: 0.7, mediaTypes: ["images"] });
      if (!result.canceled) onPicked(toPickedImage(result.assets[0]));
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.row}>
      <View style={styles.flex}>
        <Button label="Take photo" onPress={fromCamera} disabled={disabled} loading={busy} />
      </View>
      <View style={styles.flex}>
        <Button label="Choose from library" variant="secondary" onPress={fromLibrary} disabled={disabled} loading={busy} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", gap: 12 },
  flex: { flex: 1 },
});
