import { writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import openapiTS, { astToString, COMMENT_HEADER } from "openapi-typescript";

const schemaUrl = process.env.OPENAPI_SCHEMA_URL ?? "http://localhost:8080/openapi.json";
const outPath = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src/schema.ts");

try {
  const ast = await openapiTS(schemaUrl);
  const output = `${COMMENT_HEADER}${astToString(ast)}`;
  await writeFile(outPath, output, "utf8");
  console.log(`Generated schema to ${outPath}`);
} catch (error) {
  console.error("Failed to generate schema.");
  console.error(error);
  process.exit(1);
}
