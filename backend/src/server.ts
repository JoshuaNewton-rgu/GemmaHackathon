import { createApp } from "./app.js";
import { connectDb } from "./config/db.js";
import { env } from "./config/env.js";
import { logger } from "./utils/logger.js";

async function main() {
  await connectDb();

  const app = createApp();
  app.listen(env.port, () => {
    logger.info(`ProofStudy backend listening on http://localhost:${env.port}`);
  });
}

main().catch((err) => {
  logger.error("Fatal startup error", { message: err instanceof Error ? err.message : String(err) });
  process.exit(1);
});
