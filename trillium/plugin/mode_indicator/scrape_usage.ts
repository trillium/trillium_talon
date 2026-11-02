#!/usr/bin/env bun
/**
 * scrape_usage.ts — scrape claude.ai/settings/usage via Interceptor and write to data.json
 *
 * Usage:
 *   bun scrape_usage.ts <context-id> <account-name>
 *
 * account-name must match a name in accounts.json (e.g. acc1, acc2)
 */

import { execSync } from "child_process";
import { readFileSync, writeFileSync, existsSync } from "fs";
import { homedir } from "os";
import { join } from "path";

const DIR = import.meta.dir;
const PULSE_DATA = join(homedir(), "pulse-pages", "ccjuggler", "data.json");
const ACCOUNTS_FILE = join(DIR, "accounts.json");

const [contextId, accountName] = process.argv.slice(2);
if (!contextId || !accountName) {
    console.error("Usage: bun scrape_usage.ts <context-id> <account-name>");
    process.exit(1);
}

function run(cmd: string): string {
    return execSync(cmd, { encoding: "utf-8", timeout: 30000 }).trim();
}

function parseUsagePage(text: string): {
    sessionPct: number;
    weekPct: number;
    sessionResetsIn: string;
    weekResetsAt: string;
} | null {
    // Match patterns like "30% used", "11% used"
    const pcts = [...text.matchAll(/(\d+)%\s*used/g)].map((m) =>
        parseInt(m[1]),
    );
    // Match "Resets in X hr Y min" or "Resets in X min"
    const sessionReset =
        text.match(/Resets in ([\d]+ hr [\d]+ min|[\d]+ hr|[\d]+ min)/)?.[1] ??
        "";
    // Match "Resets Mon 5:00 PM" or "Resets Jul 1"
    const weekReset =
        text
            .match(/Resets (Mon|Tue|Wed|Thu|Fri|Sat|Sun)[^\n]*/)?.[0]
            ?.replace("Resets ", "") ?? "";

    if (pcts.length < 2) return null;
    return {
        sessionPct: pcts[0],
        weekPct: pcts[1],
        sessionResetsIn: sessionReset,
        weekResetsAt: weekReset,
    };
}

function loadData(): any {
    if (!existsSync(PULSE_DATA))
        return { accounts_config: [], accounts: {}, generated_at: "" };
    try {
        return JSON.parse(readFileSync(PULSE_DATA, "utf-8"));
    } catch {
        return { accounts_config: [], accounts: {}, generated_at: "" };
    }
}

function loadAccounts(): any[] {
    try {
        return JSON.parse(readFileSync(ACCOUNTS_FILE, "utf-8")).accounts ?? [];
    } catch {
        return [];
    }
}

// Scrape the usage page — reuse existing tab to keep session context,
// then wait for the async usage data to finish rendering
let text: string;
try {
    text = run(
        `interceptor --context ${contextId} open "https://claude.ai/settings/usage" --reuse --timeout 10000 --text-only --full`,
    );
    // If usage data is still loading, wait and re-read
    if (!text.includes("% used")) {
        Bun.sleepSync(4000);
        text = run(
            `interceptor --context ${contextId} read --text-only --full`,
        );
    }
} catch (e: any) {
    console.error(
        `[scrape_usage] ${accountName}: interceptor failed — ${e.message}`,
    );
    process.exit(1);
}

const parsed = parseUsagePage(text);
if (!parsed) {
    console.error(
        `[scrape_usage] ${accountName}: could not parse usage from page text`,
    );
    console.error(text.slice(0, 500));
    process.exit(1);
}

const { sessionPct, weekPct, sessionResetsIn, weekResetsAt } = parsed;
console.log(
    `[scrape_usage] ${accountName}: session=${sessionPct}% week=${weekPct}% (resets ${weekResetsAt})`,
);

// Write into data.json
const data = loadData();
const accounts = loadAccounts();
data.accounts_config = accounts.map((a: any) => {
    const { keychain_service, keychain_account, token_format, ...rest } = a;
    return rest;
});
data.accounts ??= {};
data.accounts[accountName] = {
    ...data.accounts[accountName],
    five_hour_percent: sessionPct,
    seven_day_percent: weekPct,
    week_remaining: weekResetsAt,
    session_resets_in: sessionResetsIn,
    last_updated: new Date().toISOString(),
    source: "interceptor",
};
data.generated_at = new Date().toISOString();

writeFileSync(PULSE_DATA, JSON.stringify(data, null, 2));
console.log(`[scrape_usage] ${accountName}: wrote to data.json`);
