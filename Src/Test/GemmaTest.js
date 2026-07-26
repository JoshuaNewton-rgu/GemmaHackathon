import { GoogleGenAI } from "@google/genai";

console.log("Connecting to Cloud. API Key found:", process.env.GEMINI_API_KEY ? "Yes" : "No");

// Trick the SDK into API-key mode, then force the correct header manually
const ai = new GoogleGenAI({
  apiKey: "AIza_dummy_key",
  httpOptions: {
    headers: {
      "x-goog-api-key": process.env.GEMINI_API_KEY
    }
  }
});

const response = await ai.models.generateContent({
  model: "gemma-4-26b-a4b-it",
  contents: "Explain what a mixture-of-experts model is, in two sentences.",
});

console.log("\n--- Response from Cloud ---");
console.log(response.text);