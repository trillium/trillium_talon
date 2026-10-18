// JS-level check for the palette page: runs the page's real <script> in a sandbox with
// no DOM and exercises its pure logic (search ranking, rule templates, fix-guides,
// request shaping). Run: node test/palette_page_check.mjs [path/to/page.html]
//
// This is not a browser: it proves the logic the page depends on, not that a phone
// renders it.

import { readFileSync } from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const pagePath =
    process.argv[2] ??
    fileURLToPath(
        new URL("../trillium/palette_feed/page.html", import.meta.url),
    );

let checks = 0;
const failures = [];

function ok(condition, what) {
    checks += 1;
    if (!condition) failures.push(what);
}

function eq(actual, expected, what) {
    checks += 1;
    if (actual !== expected) {
        failures.push(
            `${what}: got ${JSON.stringify(actual)}, want ${JSON.stringify(expected)}`,
        );
    }
}

const html = readFileSync(pagePath, "utf8");

// ---- the script is self-contained and extractable -------------------------------
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(
    (m) => m[1],
);
eq(scripts.length, 1, "exactly one inline <script>");
ok(!/<script[^>]+src=/i.test(html), "no external script src");
ok(!/<link[^>]+href="https?:/i.test(html), "no external stylesheet/icon link");

// ---- run it with no document ----------------------------------------------------
const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(scripts[0], sandbox, { filename: "page.html:script" });
const P = sandbox.Palette;
ok(
    P && typeof P === "object",
    "the page exposes its pure logic on globalThis.Palette",
);
if (!P) {
    console.log(
        `FAIL ${failures.length}/${checks} checks:\n- ${failures.join("\n- ")}`,
    );
    process.exit(1);
}

// ---- fuzzy search ---------------------------------------------------------------
const commands = [
    {
        id: "a",
        rule: "playback now",
        kind: "literal",
        context: "user.pb.talon",
    },
    { id: "b", rule: "play pause", kind: "literal", context: "user.pb.talon" },
    {
        id: "c",
        rule: "(abbreviate | brief) {user.abbreviation}",
        kind: "list",
        slots: [{ name: "user.abbreviation", type: "list", n: 826 }],
        context: "user.text.talon",
    },
    {
        id: "d",
        rule: "say <user.text>",
        kind: "capture",
        slots: [{ name: "user.text", type: "capture", open: true }],
        context: "user.say.talon",
    },
    {
        id: "e",
        rule: "tab {user.tab_action}",
        kind: "list",
        slots: [{ name: "user.tab_action", type: "list", n: 6 }],
        context: "user.tabs.talon",
    },
];

eq(
    P.fuzzy("playback", "playback now") > 0,
    true,
    "substring match scores positive",
);
eq(
    P.fuzzy("pbnow", "playback now") > 0,
    true,
    "subsequence across words matches",
);
eq(P.fuzzy("zzz", "playback now"), -1, "a non-subsequence does not match");
eq(
    P.fuzzy("playback now", "playback now") >
        P.fuzzy("playback", "playback now"),
    true,
    "an exact query beats a prefix",
);
eq(
    P.fuzzy("abbreviate", "(abbreviate | brief) {user.abbreviation}") > 0,
    true,
    "punctuation in a rule is ignored",
);

const ranked = P.rank(commands, "pb now");
eq(ranked[0].command.id, "a", "the best hit ranks first");
eq(ranked.length < commands.length, true, "non-hits are dropped");
eq(P.rank(commands, "tab")[0].command.id, "e", "a list rule is searchable");
eq(P.rank(commands, "").length, 0, "an empty query matches nothing");
eq(P.rank(commands, "play", 1).length, 1, "the row cap is honoured");

// ---- rule templates ------------------------------------------------------------
const abbr = commands[2];
const abbrParts = P.partsOf(abbr);
eq(abbrParts.length, 2, "alternation + list are two parts");
eq(abbrParts[0].kind, "choice", "an (a | b) group is a choice");
eq(
    abbrParts[0].options.join("/"),
    "abbreviate/brief",
    "the alternatives are the options",
);
eq(abbrParts[1].kind, "list", "the {list} slot is a list part");
eq(abbrParts[1].n, 826, "list size comes from the payload slot");
eq(P.needsInput(abbr), true, "a slotted rule needs input");
eq(
    P.buildPhrase(abbr, null),
    "abbreviate {user.abbreviation}",
    "unfilled slots stay visible in the phrase",
);
eq(
    P.buildPhrase(abbr, { 0: "brief", 1: "b64" }),
    "brief b64",
    "slots fill in order",
);

const say = commands[3];
eq(P.partsOf(say).length, 1, "a capture rule has one part");
eq(P.partsOf(say)[0].open, true, "an open capture is marked open");
eq(
    P.buildPhrase(say, { 0: "hello there" }),
    "say hello there",
    "a capture fills in",
);

eq(P.needsInput(commands[0]), false, "a literal rule needs no input");
eq(
    P.buildPhrase(commands[0], null),
    "playback now",
    "a literal phrase is the rule",
);
eq(P.needsInput(commands[4]), true, "a bare {list} rule needs input");

// ---- the fix-guide is never bare JSON ------------------------------------------
const guides = [
    P.fixGuide(401, { ok: false, error: "unauthorized" }, { host: "mbp:7399" }),
    P.fixGuide(
        423,
        { ok: false, error: "not_in_command_mode" },
        { host: "mbp:7399" },
    ),
    P.fixGuide(
        429,
        { ok: false, error: "rate_limited" },
        { retryAfter: "1", host: "m" },
    ),
    P.fixGuide(
        422,
        { ok: false, error: "no_match" },
        { phrase: "pb now", host: "m" },
    ),
    P.fixGuide(
        422,
        { ok: false, error: "not_single_command", count: 2 },
        { host: "m" },
    ),
    P.fixGuide(
        409,
        { ok: false, error: "rule_mismatch", would_run: { rule: "other" } },
        { host: "m" },
    ),
    P.fixGuide(404, { ok: false, error: "unknown_command" }, { host: "m" }),
    P.fixGuide(403, { ok: false, error: "denied" }, { host: "m" }),
    P.fixGuide(504, { ok: false, error: "execute_timeout" }, { host: "m" }),
    P.fixGuide(500, null, { host: "m" }),
    P.fixGuide(0, null, { host: "mbp.tail:7399" }),
    P.fixGuide(418, null, { host: "m" }),
    P.fixGuide(
        503,
        { ok: false, error: "engine_inactive", hint: "ENGINE HINT TEXT" },
        { host: "m" },
    ),
];
const guideText = guides.map((g) => [g.title, ...g.steps].join(" ")).join(" ");
for (const guide of guides) {
    ok(
        typeof guide.title === "string" && guide.title.length > 5,
        "every guide has a title",
    );
    ok(
        Array.isArray(guide.steps) && guide.steps.length > 0,
        "every guide has next steps",
    );
    ok(
        guide.steps.every((s) => typeof s === "string" && s.length > 0),
        "steps are non-empty text",
    );
    ok(!/^\s*[{[]/.test(guide.title), "a guide title is never raw JSON");
}

// The page has no credential of its own, so no failure may ask for one.
ok(
    !/paste|localStorage|Authorization/i.test(guideText),
    "no guide asks for a credential",
);
ok(
    guides[0].steps.join(" ").includes("palette_feed_open_execute"),
    "a 401 says which Mac setting opens /execute",
);
ok(
    guides[0].steps.join(" ").includes("palette_feed.py"),
    "a 401 says how to reload the feed",
);
ok(
    guides[guides.length - 1].steps.join(" ") === "ENGINE HINT TEXT",
    "engine_inactive shows the feed's hint verbatim",
);
ok(
    guides[guides.length - 1].title.includes("Nothing ran"),
    "engine_inactive says nothing ran",
);
ok(guides[1].action.kind === "force", "not-in-command-mode offers Run anyway");
ok(guides[2].action.kind === "retry", "rate limiting offers a retry");
ok(
    guides[3].steps.join(" ").includes("pb now"),
    "no_match shows the phrase that was sent",
);
ok(
    guides[9].title.includes("500") ||
        guides[9].title.toLowerCase().includes("errored"),
    "a 5xx says the feed errored",
);
ok(
    guides[8].title.toLowerCase().includes("5s"),
    "a 504 says the run timed out",
);
ok(
    guides[10].title.includes("mbp.tail:7399"),
    "an unreachable host names the host",
);
ok(
    guides[10].steps.join(" ").toLowerCase().includes("tailscale"),
    "an unreachable host mentions the tailnet",
);
ok(
    guides[10].steps.join(" ").toLowerCase().includes("is talon running"),
    "an unreachable host says to check Talon is running",
);
ok(!/undefined|NaN/.test(guideText), "no guide leaks undefined/NaN");

// ---- request shaping: a plain JSON POST, no credentials -------------------------
const plain = P.executeRequest("playback now", "abc123", false);
eq(plain.url, "/execute", "execute is posted to /execute");
eq(plain.init.method, "POST", "execute is a POST");
eq(
    Object.keys(plain.init.headers).join(","),
    "Content-Type",
    "no Authorization header is sent",
);
eq(plain.init.headers["Content-Type"], "application/json", "the body is JSON");
const sent = JSON.parse(plain.init.body);
eq(sent.phrase, "playback now", "the phrase is in the body");
eq(sent.id, "abc123", "the command id is in the body");
eq(
    P.executeRequest("x", null, true).url,
    "/execute?force=1",
    "Run anyway adds force=1",
);
eq(
    JSON.parse(P.executeRequest("x", null, true).init.body).id,
    undefined,
    "no id is sent when there is none",
);
ok(
    !JSON.stringify(plain).includes("Bearer"),
    "no request carries a bearer token",
);

// ---- header from /state --------------------------------------------------------
const line = P.stateLine({
    host: "mbp",
    app: { name: "Finder" },
    window: { title: "notes.md" },
    modes: ["all", "command"],
    language: "python",
});
eq(line.host, "mbp", "the header shows the host");
eq(line.context, "Finder \u2014 notes.md", "the header shows app and window");
eq(
    line.chips.find((c) => c.text === "command").on,
    true,
    "command mode is highlighted",
);
eq(P.stateLine(null).ok, false, "a missing state reads as not connected");

// ---- the page carries no credential and no external asset ----------------------
ok(
    html.split("localStorage").length - 1 === 2 &&
        html.includes('INTRO_KEY = "palette_intro_dismissed"'),
    "the only thing the page stores on the phone is the intro flag",
);
ok(!html.includes("Authorization"), "the page sends no Authorization header");
ok(!html.includes("Bearer"), "the page has no bearer-token concept at all");
ok(!/paste/i.test(html), "the page never asks anyone to paste a secret");
ok(!/id="token"/.test(html), "the page has no token field");

if (failures.length) {
    console.log(
        `FAIL ${failures.length}/${checks} checks:\n- ${failures.join("\n- ")}`,
    );
    process.exit(1);
}
console.log(`ok: ${checks} page checks passed (${pagePath})`);
