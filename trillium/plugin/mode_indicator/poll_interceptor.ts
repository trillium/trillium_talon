#!/usr/bin/env bun
/**
 * poll_interceptor.ts — poll claude.ai usage for all accounts with an interceptor_context
 * Run via Pulse cron every 5 minutes.
 */

import { execSync } from "child_process";
import { readFileSync } from "fs";
import { join } from "path";

const DIR = import.meta.dir;
const ACCOUNTS_FILE = join(DIR, "accounts.json");
const SCRAPER = join(DIR, "scrape_usage.ts");

function run(cmd: string): { out: string; ok: boolean } {
  try {
    return { out: execSync(cmd, { encoding: "utf-8", timeout: 30000 }).trim(), ok: true };
  } catch (e: any) {
    return { out: e.stderr ?? e.message ?? "", ok: false };
  }
}

const accounts: any[] = JSON.parse(readFileSync(ACCOUNTS_FILE, "utf-8")).accounts ?? [];

// Check which contexts are live
const { out: ctxOut } = run("interceptor contexts");
const liveContexts = new Set(ctxOut.split("\n").map(s => s.trim()).filter(Boolean));

for (const acct of accounts) {
  const ctx = acct.interceptor_context;
  if (!ctx) continue;

  if (!liveContexts.has(ctx)) {
    console.log(`[poll_interceptor] ${acct.name}: context '${ctx}' not connected, skipping`);
    continue;
  }

  console.log(`[poll_interceptor] ${acct.name}: scraping via context '${ctx}'`);
  const { out, ok } = run(`bun ${SCRAPER} ${ctx} ${acct.name}`);
  console.log(out);
  if (!ok) console.error(`[poll_interceptor] ${acct.name}: scrape failed`);
}
