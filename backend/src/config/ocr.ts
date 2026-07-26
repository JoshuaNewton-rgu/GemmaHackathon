import { getGemmaClient } from "./gemma.js";

export interface OcrResult {
  text: string;
  headings: string[];
  keywords: string[];
}

export interface OcrProvider {
  extractText(imageBase64: string, mimeType: string): Promise<OcrResult>;
}

/**
 * Default OCR provider: Gemma 4 is multimodal (text + image in), so instead
 * of wiring up a separate handwriting-OCR vendor (Mathpix, iWeaver, ...) we
 * ask Gemma 4 to transcribe the photo directly. This keeps the stack to a
 * single AI dependency for the hackathon; swap in a dedicated OCR vendor
 * later by implementing `OcrProvider` and changing `getOcrProvider()` below.
 */
class GemmaVisionOcrProvider implements OcrProvider {
  async extractText(imageBase64: string, mimeType: string): Promise<OcrResult> {
    const gemma = getGemmaClient();
    return gemma.generateJson<OcrResult>({
      imageBase64,
      mimeType,
      systemInstruction:
        "You transcribe photos of handwritten student notes into clean text. " +
        "Fix obvious OCR artefacts but do not invent content that isn't in the photo.",
      prompt:
        "Transcribe all handwritten and printed text visible in this photo of study notes. " +
        "Also list any headings or underlined/boxed section titles you can identify, and a " +
        "separate list of the key terms/concepts/formulas covered (short noun phrases, not full sentences).",
      schemaDescription: '{ "text": string, "headings": string[], "keywords": string[] }',
    });
  }
}

let cachedProvider: OcrProvider | undefined;

export function getOcrProvider(): OcrProvider {
  if (!cachedProvider) {
    cachedProvider = new GemmaVisionOcrProvider();
  }
  return cachedProvider;
}
