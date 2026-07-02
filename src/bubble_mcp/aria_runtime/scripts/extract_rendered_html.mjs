#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { extractRenderedHtml } from "./render_lib.mjs";

function parseArgs(argv) {
  const out = {
    selector: "body",
    timeout: 30000,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const k = argv[i];
    const v = argv[i + 1];
    if (k === "--url") {
      out.url = v;
      i += 1;
    } else if (k === "--selector") {
      out.selector = v || "body";
      i += 1;
    } else if (k === "--timeout") {
      const t = Number.parseInt(String(v || "30000"), 10);
      out.timeout = Number.isFinite(t) && t > 0 ? t : 30000;
      i += 1;
    } else if (k === "--output") {
      out.output = v;
      i += 1;
    }
  }
  return out;
}

function ensureParentDir(filePath) {
  const dir = path.dirname(filePath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.url || !args.output) {
    console.error("Missing required args. Usage: --url <url> --output <json> [--selector <css>] [--timeout <ms>]");
    process.exit(2);
  }

  const result = await extractRenderedHtml({
    url: args.url,
    selector: args.selector,
    timeout: args.timeout,
  });
  ensureParentDir(args.output);
  fs.writeFileSync(args.output, JSON.stringify(result, null, 2), "utf-8");
}

main().catch((err) => {
  const msg = String(err && err.message ? err.message : err);
  console.error(msg);
  process.exit(1);
});

