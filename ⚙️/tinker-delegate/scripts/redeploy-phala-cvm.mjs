#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

function usage() {
  console.error(
    [
      "Usage:",
      "  node scripts/redeploy-phala-cvm.mjs \\",
      "    --app-id <phala-app-id> \\",
      "    --compose <docker-compose-file> \\",
      "    --runtime-env <env-file> \\",
      "    [--api-env .env] \\",
      "    [--wait-seconds 300]",
    ].join("\n"),
  );
}

function parseArgs(argv) {
  const args = {
    apiEnv: ".env",
    waitSeconds: 300,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (!arg.startsWith("--")) {
      throw new Error(`unexpected argument: ${arg}`);
    }

    const key = arg.slice(2);
    if (key === "help") {
      args.help = true;
      continue;
    }

    const value = argv[i + 1];
    if (!value || value.startsWith("--")) {
      throw new Error(`missing value for --${key}`);
    }
    i += 1;

    switch (key) {
      case "app-id":
        args.appId = value;
        break;
      case "compose":
        args.compose = value;
        break;
      case "runtime-env":
        args.runtimeEnv = value;
        break;
      case "api-env":
        args.apiEnv = value;
        break;
      case "wait-seconds":
        args.waitSeconds = Number(value);
        break;
      default:
        throw new Error(`unknown flag: --${key}`);
    }
  }

  return args;
}

function stripInlineComment(value) {
  let inSingle = false;
  let inDouble = false;

  for (let i = 0; i < value.length; i += 1) {
    const ch = value[i];
    if (ch === "'" && !inDouble) {
      inSingle = !inSingle;
      continue;
    }
    if (ch === '"' && !inSingle) {
      inDouble = !inDouble;
      continue;
    }
    if (ch === "#" && !inSingle && !inDouble) {
      const prev = i === 0 ? " " : value[i - 1];
      if (/\s/.test(prev)) {
        return value.slice(0, i).trimEnd();
      }
    }
  }

  return value;
}

function unquote(value) {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    const inner = trimmed.slice(1, -1);
    if (trimmed.startsWith('"')) {
      return inner
        .replace(/\\n/g, "\n")
        .replace(/\\r/g, "\r")
        .replace(/\\t/g, "\t")
        .replace(/\\"/g, '"')
        .replace(/\\\\/g, "\\");
    }
    return inner.replace(/\\'/g, "'");
  }
  return trimmed;
}

async function parseEnvFile(filePath) {
  const content = await readFile(filePath, "utf8");
  const env = new Map();

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }

    const normalized = line.startsWith("export ") ? line.slice(7).trim() : line;
    const eqIndex = normalized.indexOf("=");
    if (eqIndex <= 0) {
      continue;
    }

    const key = normalized.slice(0, eqIndex).trim();
    const rawValue = normalized.slice(eqIndex + 1);
    env.set(key, unquote(stripInlineComment(rawValue)));
  }

  return env;
}

async function loadCloudSdk() {
  const npmRoot = execFileSync("npm", ["root", "-g"], { encoding: "utf8" }).trim();
  const sdkPath = path.join(
    npmRoot,
    "phala",
    "node_modules",
    "@phala",
    "cloud",
    "dist",
    "index.mjs",
  );
  return import(pathToFileURL(sdkPath).href);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    usage();
    return;
  }

  if (!args.appId || !args.compose || !args.runtimeEnv) {
    usage();
    throw new Error("missing required arguments");
  }
  if (!Number.isFinite(args.waitSeconds) || args.waitSeconds < 0) {
    throw new Error("--wait-seconds must be a non-negative number");
  }

  const apiEnv = await parseEnvFile(args.apiEnv);
  const runtimeEnv = await parseEnvFile(args.runtimeEnv);
  const apiKey = process.env.PHALA_CLOUD_API_KEY || apiEnv.get("PHALA_CLOUD_API_KEY");

  if (!apiKey) {
    throw new Error(`PHALA_CLOUD_API_KEY not found in ${args.apiEnv} or process env`);
  }
  if (runtimeEnv.size === 0) {
    throw new Error(`no runtime env vars found in ${args.runtimeEnv}`);
  }

  const composeText = await readFile(args.compose, "utf8");
  const { createClient, encryptEnvVars } = await loadCloudSdk();
  const client = createClient({
    apiKey,
    version: "2026-01-21",
    baseURL: "https://cloud-api.phala.com/api/v1",
  });

  const currentInfo = await client.safeGetCvmInfo({ app_id: args.appId });
  if (!currentInfo.success) {
    throw new Error(`failed to fetch CVM info: ${JSON.stringify(currentInfo.error)}`);
  }

  const currentCompose = await client.getCvmComposeFile({ app_id: args.appId });
  const envPubkey =
    currentCompose.env_pubkey || currentInfo.data.kms_info?.encrypted_env_pubkey;
  if (!envPubkey) {
    throw new Error("current CVM info is missing the encrypted env public key");
  }

  const envEntries = [...runtimeEnv.entries()].map(([key, value]) => ({ key, value }));
  const nextCompose = {
    ...currentCompose,
    docker_compose_file: composeText,
    allowed_envs: envEntries.map((entry) => entry.key),
  };

  const provisioned = await client.provisionCvmComposeFileUpdate({
    app_id: args.appId,
    app_compose: nextCompose,
    update_env_vars: true,
  });

  const encryptedEnv = await encryptEnvVars(envEntries, envPubkey);
  await client.commitCvmComposeFileUpdate({
    app_id: args.appId,
    compose_hash: provisioned.compose_hash,
    encrypted_env: encryptedEnv,
    env_keys: envEntries.map((entry) => entry.key),
    update_env_vars: true,
  });

  console.log(`app_id=${args.appId}`);
  console.log(`cvm_id=${currentInfo.data.id}`);
  console.log(`compose_hash=${provisioned.compose_hash}`);
  console.log(`runtime_env_keys=${envEntries.map((entry) => entry.key).join(",")}`);

  if (args.waitSeconds === 0) {
    return;
  }

  const deadline = Date.now() + args.waitSeconds * 1000;
  while (Date.now() < deadline) {
    const compose = await client.safeGetCvmComposeFile({ app_id: args.appId });
    const state = await client.safeGetCvmState({ app_id: args.appId });

    const liveHash = compose.success ? compose.data.getHash() : "unavailable";
    const stateStatus = state.success ? state.data.status : "unavailable";
    const bootProgress = state.success ? state.data.boot_progress : "unavailable";

    console.log(
      `poll live_hash=${liveHash} state=${stateStatus} boot_progress=${bootProgress}`,
    );

    if (compose.success && liveHash === provisioned.compose_hash) {
      return;
    }

    await sleep(5000);
  }

  throw new Error(
    `timed out waiting for compose hash ${provisioned.compose_hash} to become active`,
  );
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exit(1);
});
