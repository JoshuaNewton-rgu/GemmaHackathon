/**
 * Smoke test for the Gemma 4 connection - migrated from the original
 * Src/Test/GemmaTest.js hackathon spike into the real provider abstraction.
 * Run with: npm run test:gemma --workspace backend
 */
import "../src/config/env.js";
import { getGemmaClient } from "../src/config/gemma.js";
import { env } from "../src/config/env.js";

async function main() {
  console.log(`Connecting via provider: ${env.gemma.provider} (model=${env.gemma.model})`);
  const gemma = getGemmaClient();

  const text = await gemma.generateText({
    prompt: "Explain what a mixture-of-experts model is, in two sentences.",
  });

  console.log("\n--- Response from Gemma 4 ---");
  console.log(text);
}

main().catch((err) => {
  console.error("Gemma 4 smoke test failed:", err);
  process.exit(1);
});
