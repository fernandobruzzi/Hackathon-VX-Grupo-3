import fs from "node:fs/promises";
import openapiTS, { astToString } from "openapi-typescript";
import { format, resolveConfig } from "prettier";

const output = new URL("../src/types/api.generated.ts", import.meta.url);
const schema = new URL("../../api/contracts/openapi.json", import.meta.url);
const generated = await format(astToString(await openapiTS(schema)), {
  ...(await resolveConfig(output.pathname)),
  filepath: output.pathname,
});

if (process.argv.includes("--check")) {
  if ((await fs.readFile(output, "utf8")) !== generated) {
    throw new Error("Tipos desatualizados: execute npm run api:generate.");
  }
} else {
  await fs.writeFile(output, generated);
}
