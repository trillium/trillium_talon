// DOM-level check for the palette page: runs the shipped <script> inside a real DOM
// (jsdom), with `fetch` stubbed, and drives the wiring the pure-logic check cannot
// reach — header from /state, search filtering, the slot form, the one POST, and the
// fix-guide a failed run shows.
//
//   npm install --prefix /tmp/palette-jsdom jsdom
//   NODE_PATH=/tmp/palette-jsdom/node_modules node test/palette_page_dom_check.mjs//
// Skips (exit 0) when jsdom is not installed: it is not a dependency of this repo.
// This is jsdom, not a phone — layout, touch and iOS behaviour stay unverified.

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const pagePath =
    process.argv[2] ??
    fileURLToPath(
        new URL("../trillium/palette_feed/page.html", import.meta.url),
    );

// jsdom is not a dependency of this repo, so it may be installed anywhere: next to this
// script (`npm install jsdom` in the repo) or under a NODE_PATH prefix.
let JSDOM;
try {
    JSDOM = createRequire(import.meta.url)("jsdom").JSDOM;
} catch {
    try {
        const fromCwd = createRequire(process.cwd() + "/noop.js");
        JSDOM = fromCwd("jsdom").JSDOM;
    } catch {
        console.log(
            "skip: jsdom not installed (npm install --prefix /tmp/palette-jsdom jsdom)",
        );
        process.exit(0);
    }
}

let checks = 0;
const failures = [];
const ok = (cond, what) => {
    checks += 1;
    if (!cond) failures.push(what);
};
const eq = (actual, expected, what) => {
    checks += 1;
    if (actual !== expected) {
        failures.push(
            `${what}: got ${JSON.stringify(actual)}, want ${JSON.stringify(expected)}`,
        );
    }
};

const TOKEN = "dom-check-token-" + "x".repeat(24);
const COMMANDS = [
    {
        id: "c1",
        rule: "playback now",
        kind: "literal",
        slots: [],
        context: "a.talon",
    },
    {
        id: "c2",
        rule: "play pause",
        kind: "literal",
        slots: [],
        context: "a.talon",
    },
    {
        id: "c3",
        rule: "(abbreviate | brief) {user.abbreviation}",
        kind: "list",
        slots: [{ name: "user.abbreviation", type: "list", n: 826 }],
        context: "b.talon",
    },
    {
        id: "c4",
        rule: "window snip",
        kind: "literal",
        slots: [],
        context: "c.talon",
    },
];
const STATE = {
    host: "mbp-test",
    app: { name: "Finder" },
    window: { title: "notes.md" },
    modes: ["all", "command"],
    language: "python",
    commands_rev: "rev1",
};

const requests = [];
let executeStatus = 200;
let executeBody = { ok: true, matched_rule: "playback now", path: "p" };

const dom = new JSDOM(readFileSync(pagePath, "utf8"), {
    url: "http://127.0.0.1:7399/",
    runScripts: "dangerously",
    pretendToBeVisual: true,
    beforeParse(window) {
        window.fetch = (url, init = {}) => {
            requests.push({ url, init });
            let status = 200,
                body = {};
            if (url.startsWith("/state")) body = STATE;
            else if (url.startsWith("/lists/"))
                body = { name: "x", entries: ["open", "close"] };
            else if (url.startsWith("/execute")) {
                status = executeStatus;
                body = executeBody;
            } else
                body = {
                    commands_rev: "rev1",
                    count: COMMANDS.length,
                    commands: COMMANDS,
                };
            return Promise.resolve({
                ok: status >= 200 && status < 300,
                status,
                headers: { get: () => (status === 429 ? "1" : null) },
                json: () => Promise.resolve(body),
                text: () => Promise.resolve(JSON.stringify(body)),
            });
        };
    },
});

const { window } = dom;
const doc = window.document;
const tick = (ms = 0) => new Promise((r) => window.setTimeout(r, ms));
const text = (id) => doc.getElementById(id).textContent;
const rows = () => [...doc.querySelectorAll("li.cmd")];
const search = (value) => {
    const box = doc.getElementById("q");
    box.value = value;
    box.dispatchEvent(new window.Event("input", { bubbles: true }));
};

await tick(20);
doc.dispatchEvent(new window.Event("DOMContentLoaded", { bubbles: true }));
await tick(20);

// ---- the header from /state -----------------------------------------------------
eq(text("host"), "mbp-test", "the header shows the host from /state");
eq(
    text("context"),
    "Finder \u2014 notes.md",
    "the header shows app and window title",
);
ok(text("chips").includes("command"), "the header shows the active modes");
ok(
    requests.some((r) => r.url.startsWith("/state")),
    "the page polls /state",
);
const stateReq = requests.find((r) => r.url.startsWith("/state"));
eq(
    stateReq.init.headers,
    undefined,
    "reads are made with no Authorization header",
);

// ---- search over /commands ------------------------------------------------------
eq(rows().length, 0, "no rows before a query");
search("play");
await tick(90);
eq(rows().length, 2, "search filters the command list");
search("playback");
await tick(90);
ok(
    rows()[0].querySelector(".rule").textContent.includes("playback now"),
    "the better hit is the first row",
);
eq(rows().length, 1, "a longer match drops the weaker rule");
search("pbnow");
await tick(90);
eq(rows().length, 1, "a subsequence query still finds a command");
search("window snip");
await tick(90);
ok(
    rows()[0].querySelector(".rule").textContent.includes("window snip"),
    "a literal rule renders",
);
eq(text("count"), "1 of 4 commands", "the count line reports the filter");

// ---- the page holds no credential at all ---------------------------------------
eq(doc.getElementById("token"), null, "the page has no token field");
eq(
    Object.keys(window.localStorage).length,
    0,
    "the page writes nothing to local storage before the intro is dismissed",
);
// ---- first-run block ------------------------------------------------------------
const intro = doc.getElementById("intro");
ok(!intro.hidden, "the first-run block shows on a first visit");
ok(
    intro.textContent.includes("voice commands") &&
        intro.textContent.includes("Tip:"),
    "the first-run block says what the page is and gives one search tip",
);
doc.getElementById("intro-dismiss").click();
ok(intro.hidden, "Got it hides the first-run block");
eq(
    window.localStorage.getItem("palette_intro_dismissed"),
    "1",
    "dismissal is remembered in local storage",
);
ok(stateReq.init.headers === undefined, "reads carry no headers");
ok(
    !/Authorization|Bearer/.test(readFileSync(pagePath, "utf8")),
    "the page sends no credentials",
);

// ---- tapping a literal rule runs it --------------------------------------------
search("window snip");
await tick(90);
rows()[0].querySelector(".tap").click();
await tick(30);
const run = requests.find((r) => r.url.startsWith("/execute"));
ok(run, "tapping a literal command POSTs /execute");
eq(run.init.method, "POST", "the run is a POST");
eq(run.init.headers.Authorization, undefined, "the run carries no token");
eq(
    Object.keys(run.init.headers).join(","),
    "Content-Type",
    "the run sends only a content type",
);
eq(run.url, "/execute", "the run URL carries nothing extra");
eq(JSON.parse(run.init.body).phrase, "window snip", "the run sends the phrase");
eq(JSON.parse(run.init.body).id, "c4", "the run sends the command id");
await tick(30);
ok(text("toast").includes("Ran:"), "a successful run is confirmed");
ok(!doc.getElementById("toast").hidden, "the confirmation is visible");

// ---- a slotted rule opens a form instead of a doomed request -------------------
const before = requests.filter((r) => r.url.startsWith("/execute")).length;
search("abbreviate");
await tick(90);
ok(
    rows()[0].querySelector(".sub").textContent.includes("needs a value"),
    "a slotted rule is marked as needing a value",
);
rows()[0].querySelector(".tap").click();
await tick(30);
eq(
    requests.filter((r) => r.url.startsWith("/execute")).length,
    before,
    "tapping a slotted rule does not fire a bare request",
);
const form = rows()[0].querySelector(".form");
ok(form, "a slotted rule opens a form");
eq(form.querySelectorAll("select").length, 1, "the (a | b) group is a select");
eq(form.querySelectorAll("input").length, 1, "the {list} slot is an input");
eq(
    form.querySelector("select").value,
    "abbreviate",
    "the first alternative is the default",
);
eq(
    form.querySelector("input").getAttribute("list"),
    form.querySelector("datalist").id,
    "the list slot is wired to its datalist suggestions",
);
eq(
    form.querySelector("datalist").options.length,
    2,
    "list suggestions are fetched",
);
ok(
    form.textContent.includes("abbreviate {user.abbreviation}"),
    "the form previews the phrase it would send",
);

form.querySelector("select").value = "brief";
form.querySelector("input").value = "b64";
form.querySelector(".primary").click();
await tick(30);
const filled = requests.filter((r) => r.url.startsWith("/execute")).pop();
eq(
    JSON.parse(filled.init.body).phrase,
    "brief b64",
    "the form fills the slots in order",
);

// ---- a failed run shows the fix-guide, never bare JSON -------------------------
executeStatus = 401;
executeBody = { ok: false, error: "unauthorized" };
search("play pause");
await tick(90);
rows()[0].querySelector(".tap").click();
await tick(30);
const guide = doc.getElementById("guide");
ok(
    guide.textContent.includes("will not run commands from this page"),
    "a 401 explains that the Mac still wants a token",
);
ok(
    guide.textContent.includes("palette_feed_open_execute"),
    "the guide names the Mac setting that opens /execute",
);
ok(
    !/paste|localStorage/i.test(guide.textContent),
    "the guide asks for no credential",
);
ok(!/unauthorized/.test(guide.textContent), "the guide never shows raw JSON");
ok(
    doc.querySelector("#guide .card .buttons"),
    "the guide offers the next action",
);

executeStatus = 503;
executeBody = {
    ok: false,
    error: "engine_inactive",
    hint: "The speech engine is not running on this machine.",
};
search("play pause");
await tick(90);
rows()[0].querySelector(".tap").click();
await tick(30);
ok(
    guide.textContent.includes("The speech engine is not running on this machine."),
    "engine_inactive shows the hint text",
);
ok(!/\bRan:/.test(text("toast")), "engine_inactive is not shown as success");

executeStatus = 423;
executeBody = { ok: false, error: "not_in_command_mode" };
search("play pause");
await tick(90);
rows()[0].querySelector(".tap").click();
await tick(30);
ok(guide.textContent.includes("not in command mode"), "423 explains the mode");
ok(guide.textContent.includes("Run anyway"), "423 offers Run anyway");
guide.querySelector("#guide .primary").click();
await tick(30);
const forced = requests.filter((r) => r.url.startsWith("/execute")).pop();
eq(forced.url, "/execute?force=1", "Run anyway retries with force=1");

executeStatus = 0;
search("play pause");
await tick(90);
// a dead feed: fetch rejects
window.fetch = (url, init = {}) => {
    requests.push({ url, init });
    if (url.startsWith("/state") || url.startsWith("/commands")) {
        return Promise.resolve({
            ok: true,
            status: 200,
            headers: { get: () => null },
            json: () =>
                Promise.resolve(
                    url.startsWith("/state")
                        ? STATE
                        : {
                              commands_rev: "rev1",
                              count: COMMANDS.length,
                              commands: COMMANDS,
                          },
                ),
            text: () => Promise.resolve("{}"),
        });
    }
    return Promise.reject(new TypeError("Failed to fetch"));
};
search("play pause");
await tick(90);
rows()[0].querySelector(".tap").click();
await tick(30);
ok(
    guide.textContent.includes("Cannot reach the Mac at 127.0.0.1:7399"),
    "a dead feed names the host it could not reach",
);
ok(
    guide.textContent.includes("tailnet"),
    "a dead feed says to check the tailnet",
);

if (failures.length) {
    console.log(
        `FAIL ${failures.length}/${checks} checks:\n- ${failures.join("\n- ")}`,
    );
    window.close();
    process.exit(1);
}
console.log(`ok: ${checks} DOM checks passed (jsdom, ${pagePath})`);
// The page polls /state on a timer, so the jsdom event loop never drains on its own.
window.close();
process.exit(0);
