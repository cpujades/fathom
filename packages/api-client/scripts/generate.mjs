import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import openapiTS, { astToString, COMMENT_HEADER } from "openapi-typescript";

const packagePath = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const schemaPath = path.resolve(process.env.OPENAPI_SCHEMA_PATH ?? path.join(packagePath, "openapi.json"));
const outPath = path.join(packagePath, "src/schema.ts");
const checkOnly = process.argv.includes("--check");

try {
  const schemaSource = process.env.OPENAPI_SCHEMA_URL ?? JSON.parse(await readFile(schemaPath, "utf8"));
  const ast = await openapiTS(schemaSource);
  const output = `${COMMENT_HEADER}${astToString(ast)}`;
  if (checkOnly) {
    const current = await readFile(outPath, "utf8");
    if (current !== output) {
      console.error(`Generated API client is stale: ${outPath}`);
      console.error("Run `pnpm generate:api-client` and commit the generated changes.");
      process.exit(1);
    }
    console.log(`Generated API client is current: ${outPath}`);
    process.exit(0);
  }
  await writeFile(outPath, output, "utf8");
  console.log(`Generated schema to ${outPath}`);
} catch (error) {
  console.error(checkOnly ? "Failed to verify generated schema." : "Failed to generate schema.");
  console.error(error);
  process.exit(1);
}
