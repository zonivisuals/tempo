// Tempo auth schema migration (replaces `npx @better-auth/cli migrate`).
// The standalone CLI is version-diverged (1.4.x, deprecated) from the
// library (1.7.5); this script uses the INSTALLED library's own
// getMigrations(), so generated tables always match the running code.
// Docs: better-auth getMigrations (db/get-migration in the package).
// Usage: node migrate.mjs [--print]  (--print shows SQL without applying)
import "dotenv/config";
import { getMigrations } from "better-auth/db/migration";
import { auth } from "./auth.mjs";

const printOnly = process.argv.includes("--print");
const plan = await getMigrations(auth.options);
console.log("tables to create:", plan.toBeCreated.map((t) => t.table).join(", ") || "(none)");
for (const u of plan.unsafeChanges) console.log("UNSAFE:", u);
if (printOnly) {
  console.log(await plan.compileMigrations());
  process.exit(0);
}
await plan.runMigrations();
console.log("migrations applied");
process.exit(0);
