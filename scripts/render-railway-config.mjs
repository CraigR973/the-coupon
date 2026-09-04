#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

import ts from "typescript";
import { createRailwayContext, project } from "railway/iac";

const root = new URL("../", import.meta.url);
const configUrl = new URL(".railway/railway.ts", root);
const source = readFileSync(configUrl, "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
  fileName: pathToFileURL(configUrl.pathname).href,
  reportDiagnostics: true,
});

if (transpiled.diagnostics?.length) {
  const messages = transpiled.diagnostics.map((diagnostic) =>
    ts.flattenDiagnosticMessageText(diagnostic.messageText, "\n"),
  );
  throw new Error(`Could not transpile Railway IaC:\n${messages.join("\n")}`);
}

const railwayIacUrl = import.meta.resolve("railway/iac");
const runnable = transpiled.outputText.replace('"railway/iac"', JSON.stringify(railwayIacUrl));
if (runnable === transpiled.outputText) {
  throw new Error("Could not resolve the railway/iac import in .railway/railway.ts");
}

const moduleUrl = `data:text/javascript;base64,${Buffer.from(runnable).toString("base64")}`;
const config = await import(moduleUrl);
const projectId = process.argv[2] ?? "e030ebe3-e7fc-43c9-9478-4e80cafaa126";
const environmentId = process.argv[3] ?? "8f18cb49-5137-4557-900a-031bcab4ac38";
const graph = await config.default(
  createRailwayContext({
    command: "plan",
    projectId,
    environmentId,
    environment: "production",
  }),
  project,
);

process.stdout.write(`${JSON.stringify({ partial: config.partial ?? null, graph })}\n`);
