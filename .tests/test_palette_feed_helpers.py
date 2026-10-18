"""Tests for the pure palette_feed helpers (no Talon needed)."""

import io
import os
import threading

import pytest

from trillium.palette_feed import (
    auth,
    denylist,
    dispatch,
    limits,
    options,
    serialize,
    simparse,
)

TOKEN = "t" * 43


class TestAuth:
    def test_accepts_matching_bearer(self):
        assert auth.is_authorized(f"Bearer {TOKEN}", TOKEN)

    def test_scheme_is_case_insensitive(self):
        assert auth.is_authorized(f"bearer {TOKEN}", TOKEN)

    @pytest.mark.parametrize(
        "header",
        [
            None,
            "",
            "Bearer",
            "Bearer ",
            "Basic abc",
            TOKEN,
            f"Bearer {TOKEN}x",
            "Bearer wrong",
        ],
    )
    def test_rejects_everything_else(self, header):
        assert not auth.is_authorized(header, TOKEN)

    def test_non_ascii_credential_does_not_raise(self):
        assert not auth.is_authorized("Bearer tökén", TOKEN)

    def test_load_token_reads_private_file(self, tmp_path):
        path = tmp_path / "token"
        path.write_text(TOKEN + "\n")
        path.chmod(0o600)
        assert auth.load_token(str(path)) == TOKEN

    def test_load_token_rejects_world_readable(self, tmp_path):
        path = tmp_path / "token"
        path.write_text(TOKEN)
        path.chmod(0o644)
        with pytest.raises(auth.TokenError, match="chmod 600"):
            auth.load_token(str(path))

    def test_load_token_rejects_missing_file(self, tmp_path):
        with pytest.raises(auth.TokenError):
            auth.load_token(str(tmp_path / "nope"))

    def test_load_token_rejects_short_token(self, tmp_path):
        path = tmp_path / "token"
        path.write_text("short")
        path.chmod(0o600)
        with pytest.raises(auth.TokenError, match="shorter"):
            auth.load_token(str(path))

    def test_load_token_rejects_directory(self, tmp_path):
        with pytest.raises(auth.TokenError, match="regular file"):
            auth.load_token(str(tmp_path))

    def test_is_within(self, tmp_path):
        inside = tmp_path / "repo" / "token"
        assert auth.is_within(str(inside), str(tmp_path / "repo"))
        assert not auth.is_within(
            str(tmp_path / "other" / "token"), str(tmp_path / "repo")
        )

    def test_find_repo_root_finds_git_dir_and_worktree_file(self, tmp_path):
        (tmp_path / "repo" / ".git").mkdir(parents=True)
        (tmp_path / "wt").mkdir()
        (tmp_path / "wt" / ".git").write_text("gitdir: elsewhere")
        deep = tmp_path / "repo" / "a" / "b"
        deep.mkdir(parents=True)
        (tmp_path / "wt" / "x").mkdir()
        assert auth.find_repo_root(str(deep / "mod.py")) == str(tmp_path / "repo")
        assert auth.find_repo_root(str(tmp_path / "wt" / "x" / "mod.py")) == str(
            tmp_path / "wt"
        )

    def test_find_repo_root_is_none_outside_a_repo(self, tmp_path):
        # tmp_path lives under the system temp dir, which is not inside a git repo.
        assert auth.find_repo_root(str(tmp_path / "mod.py")) is None

    def test_is_within_follows_symlinks(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        link = tmp_path / "link"
        os.symlink(repo, link)
        assert auth.is_within(str(link / "token"), str(repo))


class TestBodyBounds:
    def test_accepts_within_limit(self):
        assert limits.parse_content_length("10", 100) == 10
        assert limits.parse_content_length("100", 100) == 100

    @pytest.mark.parametrize(
        "value, status, code",
        [
            (None, 411, "length_required"),
            ("", 411, "length_required"),
            ("abc", 400, "bad_content_length"),
            ("-1", 400, "bad_content_length"),
            ("101", 413, "body_too_large"),
        ],
    )
    def test_rejects_bad_lengths(self, value, status, code):
        with pytest.raises(limits.BodyError) as err:
            limits.parse_content_length(value, 100)
        assert (err.value.status, err.value.code) == (status, code)

    def test_read_body_reads_exact_length(self):
        assert limits.read_body(io.BytesIO(b"hello world"), 5) == b"hello"

    def test_read_body_rejects_truncated(self):
        with pytest.raises(limits.BodyError) as err:
            limits.read_body(io.BytesIO(b"hi"), 5)
        assert err.value.status == 400


class TestRateLimiter:
    def make(self, max_calls=2, window=1.0):
        now = [0.0]
        limiter = limits.RateLimiter(max_calls, window, clock=lambda: now[0])
        return limiter, now

    def test_blocks_after_limit(self):
        limiter, _ = self.make()
        assert limiter.check()[0]
        assert limiter.check()[0]
        allowed, retry_after = limiter.check()
        assert not allowed
        assert retry_after == pytest.approx(1.0)

    def test_window_slides(self):
        limiter, now = self.make()
        limiter.check()
        now[0] = 0.5
        limiter.check()
        now[0] = 0.9
        allowed, retry_after = limiter.check()
        assert not allowed and retry_after == pytest.approx(0.1)
        now[0] = 1.0
        assert limiter.check()[0]

    def test_rejected_calls_do_not_extend_the_block(self):
        limiter, now = self.make(max_calls=1)
        limiter.check()
        now[0] = 0.5
        limiter.check()
        now[0] = 1.0
        assert limiter.check()[0]


class TestDenylist:
    @pytest.mark.parametrize(
        "text",
        [
            "sudo restart talon",
            "SUDO wifi off",
            "restart talon",
            "talon restart",
            "shut her down",
            "shutdown",
            "reboot",
            "kill all",
            "sudo (restart talon|talon restart)",
        ],
    )
    def test_blocks(self, text):
        assert denylist.denied_by(text)

    @pytest.mark.parametrize(
        "text",
        ["playback now", "word hello", "sudoku", "go to line five", "restart program"],
    )
    def test_allows(self, text):
        assert denylist.denied_by(text) is None

    def test_any_text_blocks(self):
        assert denylist.denied_by("playback now", "sudo wifi off")

    def test_punctuation_cannot_split_a_pattern(self):
        assert denylist.denied_by("restart,   talon!")


class TestRunScheduled:
    def test_returns_result_of_scheduled_call(self):
        assert dispatch.run_scheduled(lambda job: job(), lambda: 42, 1.0) == 42

    def test_runs_on_the_scheduling_thread(self):
        seen = []

        def schedule(job):
            t = threading.Thread(target=job)
            seen.append(t)
            t.start()

        main = threading.get_ident()
        assert dispatch.run_scheduled(schedule, threading.get_ident, 1.0) != main

    def test_reraises_errors(self):
        def boom():
            raise ValueError("nope")

        with pytest.raises(ValueError, match="nope"):
            dispatch.run_scheduled(lambda job: job(), boom, 1.0)

    def test_times_out_when_never_run(self):
        with pytest.raises(dispatch.DispatchTimeout):
            dispatch.run_scheduled(lambda job: None, lambda: 1, 0.01)

    def test_a_job_run_after_the_timeout_does_nothing(self):
        pending = []
        ran = []
        with pytest.raises(dispatch.DispatchTimeout):
            dispatch.run_scheduled(pending.append, lambda: ran.append(1), 0.01)
        pending[0]()  # Talon's cron thread frees up and finally picks the job up
        assert ran == []

    def test_a_job_that_already_started_is_not_cancelled(self):
        started, release, ran = threading.Event(), threading.Event(), []

        def slow():
            started.set()
            release.wait(2)
            ran.append(1)

        t = None

        def schedule(job):
            nonlocal t
            t = threading.Thread(target=job)
            t.start()

        with pytest.raises(dispatch.DispatchTimeout):
            dispatch.run_scheduled(schedule, slow, 0.05)
        assert started.is_set()
        release.set()
        t.join(2)
        assert ran == [1]


SIM_SIMPLE = (
    '[1] "playback now"\n'
    "   path: user/most_recent_command_playback/most_recent_command_playback.talon\n"
    '   rule: "playback now"'
)
SIM_CAPTURE = (
    '[1] "word hello"\n'
    "   path: user/trillium_talon/core/text/text.talon\n"
    '   rule: "{user.word_formatter} <user.word>"\n'
    "   [1] {user.word_formatter} word\n"
    "   [2] <user.word> hello\n"
    "     [1] <word> hello"
)


class TestSimParse:
    def test_simple(self):
        assert simparse.parse_sim(SIM_SIMPLE) == [
            simparse.SimMatch(
                "playback now",
                "user/most_recent_command_playback/most_recent_command_playback.talon",
            )
        ]

    def test_nested_capture_lines_are_not_extra_commands(self):
        matches = simparse.parse_sim(SIM_CAPTURE)
        assert [m.rule for m in matches] == ["{user.word_formatter} <user.word>"]

    def test_chained_commands(self):
        text = SIM_SIMPLE + '\n[2] "other"\n   path: user/a.talon\n   rule: "other"'
        assert [m.rule for m in simparse.parse_sim(text)] == ["playback now", "other"]

    def test_garbage_yields_nothing(self):
        assert simparse.parse_sim("nothing here") == []

    def test_normalize_rule_ignores_anchors_and_spacing(self):
        assert simparse.normalize_rule("^sudo (restart talon | talon restart)$") == (
            simparse.normalize_rule("sudo (restart talon|talon restart)")
        )


def impl(trigger, context="user.a.talon", lineno=1, score=(0,)):
    return serialize.RawImpl(trigger, context, lineno, score)


# The two live CommandImpl shapes, 2026-10-18 (task-ykd7c). `_Impl040` has no `trigger` and no
# `lineno` at all, exactly like Talon 0.4.0; `_ImplRefactored` is CommandImpl(ScriptImpl).
PARROT_CONTEXT = "user.trillium_talon.trillium.plugin.parrot.parrot_always.talon"
PARROT_RULE = "parrot on"
PARROT_LINENO = 4
# The id the newer build reports for that rule, live from the MacBook's feed.
PARROT_ID = "00de4484b8"


class _Rule:
    def __init__(self, text):
        self.rule = text


class _Script:
    def __init__(self, start_line):
        self.start_line = start_line
        self.filename = "user/parrot_always.talon"
        self.code = "user.parrot_enable()"


class _Ctx:
    def __init__(self, path, scores=None):
        self.path = path
        if scores is not None:
            self._active_scores = scores


class _Impl040:
    """Talon 0.4.0: ctx/rule/script/experiments, and no `trigger`, `lineno` or `_active_scores`."""

    def __init__(self, ctx, rule, script=None):
        self.ctx = ctx
        self.rule = rule
        self.script = script or _Script(PARROT_LINENO)
        self.experiments = set()


class _ImplRefactored:
    """0.4.0-1561-9c3d: CommandImpl(ScriptImpl), answering `trigger` and `lineno` directly."""

    def __init__(self, ctx, rule, lineno):
        self.ctx = ctx
        self.rule = rule
        self.script = _Script(lineno)
        self.trigger = rule.rule
        self.lineno = lineno
        self.experiments = set()


def _parrot_040():
    return _Impl040(_Ctx(PARROT_CONTEXT), _Rule(PARROT_RULE))


def _parrot_refactored():
    return _ImplRefactored(
        _Ctx(PARROT_CONTEXT, (1, 0)), _Rule(PARROT_RULE), PARROT_LINENO
    )


class TestImplToRaw:
    """impl_to_raw: the 0.4.0 shape must reduce to exactly what the newer build reports."""

    def test_the_0_4_0_fixture_really_lacks_trigger_and_lineno(self):
        # Without this the test below could pass by accident on a newer-shaped object.
        impl040 = _parrot_040()
        assert not hasattr(impl040, "trigger")
        assert not hasattr(impl040, "lineno")
        assert not hasattr(impl040.ctx, "_active_scores")

    def test_both_shapes_reduce_to_the_same_values(self):
        old = serialize.impl_to_raw(_parrot_040())
        new = serialize.impl_to_raw(_parrot_refactored())
        assert old.trigger == new.trigger == PARROT_RULE
        assert old.context == new.context == PARROT_CONTEXT
        assert old.lineno == new.lineno == PARROT_LINENO

    def test_0_4_0_shape_reproduces_the_id_the_newer_build_reports(self):
        for shape in (_parrot_040(), _parrot_refactored()):
            out = serialize.serialize_commands(
                [[serialize.impl_to_raw(shape)]], lambda name: 0
            )
            (entry,) = out["commands"]
            assert entry["id"] == PARROT_ID
            assert entry["rule"] == PARROT_RULE
            assert entry["lineno"] == PARROT_LINENO
            assert entry["context"] == PARROT_CONTEXT

    def test_newer_build_scores_survive_and_0_4_0_degrades_to_empty(self):
        assert serialize.impl_to_raw(_parrot_refactored()).score == (1, 0)
        assert serialize.impl_to_raw(_parrot_040()).score == ()

    def test_absent_scores_keep_the_first_registered_winner(self):
        first = _Impl040(_Ctx("first.talon"), _Rule("west"))
        last = _Impl040(_Ctx("last.talon"), _Rule("west"))
        out = serialize.serialize_commands(
            [[serialize.impl_to_raw(first), serialize.impl_to_raw(last)]], lambda n: 0
        )
        (entry,) = out["commands"]
        assert entry["context"] == "first.talon"
        assert entry["shadowed"] == 1

    def test_a_bare_object_never_raises(self):
        raw = serialize.impl_to_raw(object())
        assert (raw.trigger, raw.lineno, raw.score) == ("", 0, ())

    def test_a_falsy_trigger_falls_back_to_the_rule_text(self):
        bare = _ImplRefactored(_Ctx(PARROT_CONTEXT), _Rule(PARROT_RULE), PARROT_LINENO)
        bare.trigger = ""
        assert serialize.impl_to_raw(bare).trigger == PARROT_RULE


class TestSerialize:
    def test_classify(self):
        assert serialize.classify("playback now") == "literal"
        assert serialize.classify("tab {user.tab_action}") == "list"
        assert serialize.classify("say <user.text>") == "capture"
        assert serialize.classify("{user.fmt} <user.word>") == "capture"

    def test_slots(self):
        slots = serialize.describe_slots("{user.fmt} <user.text> <number>", lambda n: 7)
        assert slots == [
            {"name": "user.fmt", "type": "list", "n": 7},
            {"name": "user.text", "type": "capture", "open": True},
            {"name": "number", "type": "capture", "open": True},
        ]

    def test_closed_capture_is_not_open(self):
        slots = serialize.describe_slots("<user.letter>", lambda n: 0)
        assert slots[0]["open"] is False

    def test_winner_is_highest_score_not_first(self):
        low = impl("x", "low.talon", score=(1, 0, 0))
        high = impl("x", "high.talon", score=(2, 0, 0))
        assert serialize.pick_winner([low, high]) is high

    def test_tie_goes_to_first_registered(self):
        first, second = impl("x", "a.talon"), impl("x", "b.talon")
        assert serialize.pick_winner([first, second]) is first

    def test_serialize_commands_shape(self):
        out = serialize.serialize_commands(
            [
                [impl("b rule", "b.talon", 3)],
                [
                    impl("a rule", "low.talon", score=(1,)),
                    impl("a rule", "high.talon", score=(2,)),
                ],
            ],
            lambda n: 0,
        )
        assert out["count"] == 2
        assert [c["rule"] for c in out["commands"]] == ["a rule", "b rule"]
        first = out["commands"][0]
        assert first["context"] == "high.talon"
        assert first["shadowed"] == 1
        assert first["kind"] == "literal"
        assert set(first) == {
            "id",
            "rule",
            "kind",
            "slots",
            "context",
            "lineno",
            "shadowed",
        }

    def test_commands_rev_tracks_content(self):
        a = serialize.serialize_commands([[impl("one")]], lambda n: 0)["commands_rev"]
        same = serialize.serialize_commands([[impl("one")]], lambda n: 0)[
            "commands_rev"
        ]
        other = serialize.serialize_commands([[impl("two")]], lambda n: 0)[
            "commands_rev"
        ]
        assert a == same != other

    def test_command_id_is_stable_and_distinct(self):
        assert serialize.command_id("a", 1, "r") == serialize.command_id("a", 1, "r")
        assert serialize.command_id("a", 1, "r") != serialize.command_id("a", 2, "r")

    def test_referenced_lists(self):
        out = serialize.serialize_commands(
            [[impl("tab {user.tab_action}")], [impl("say <user.text>")]], lambda n: 3
        )
        assert serialize.referenced_lists(out["commands"]) == {"user.tab_action"}

    def test_serialize_state(self):
        kwargs = dict(
            host="h",
            ts="2026-10-17T00:00:00Z",
            app={"name": "WezTerm", "bundle": "b", "exe": "dropped"},
            window={"title": "t", "doc": "dropped"},
            modes={"command", "all"},
            tags={"user.b", "user.a"},
            language="",
            commands_rev="rev1",
        )
        state = serialize.serialize_state(**kwargs)
        assert state["app"] == {"name": "WezTerm", "bundle": "b"}
        assert state["window"] == {"title": "t", "filename": "", "file_ext": ""}
        assert state["modes"] == ["all", "command"]
        assert state["tags"] == ["user.a", "user.b"]
        later = serialize.serialize_state(**{**kwargs, "ts": "2026-10-17T00:00:09Z"})
        assert later["rev"] == state["rev"]  # rev ignores ts
        changed = serialize.serialize_state(**{**kwargs, "app": {"name": "Other"}})
        assert changed["rev"] != state["rev"]


class TestTokenPlan:
    """`plan_token` is the feed's whole start/disable decision."""

    @staticmethod
    def private_token(tmp_path):
        path = tmp_path / "token"
        path.write_text(TOKEN)
        path.chmod(0o600)
        return str(path)

    def test_private_token_is_used_for_both_sides(self, tmp_path):
        plan = auth.plan_token(self.private_token(tmp_path), None, False)
        assert plan == auth.TokenPlan(TOKEN, False, "token loaded")

    def test_missing_token_is_fatal_while_reads_are_authenticated(self, tmp_path):
        plan = auth.plan_token(str(tmp_path / "absent"), None, False)
        assert plan.fatal and plan.token is None
        assert "not starting" in plan.message

    def test_missing_token_still_serves_open_reads(self, tmp_path):
        """The one asymmetric case: reads open means no token is not fatal."""
        plan = auth.plan_token(str(tmp_path / "absent"), None, True)
        assert not plan.fatal and plan.token is None
        assert "/execute disabled" in plan.message

    def test_missing_token_is_not_fatal_when_execute_is_open(self, tmp_path):
        plan = auth.plan_token(str(tmp_path / "absent"), None, False, True)
        assert not plan.fatal and plan.token is None
        assert "reads token-gated, /execute open" in plan.message

    def test_both_routes_open_needs_no_token_at_all(self, tmp_path):
        plan = auth.plan_token(str(tmp_path / "absent"), None, True, True)
        assert not plan.fatal
        assert "reads open, /execute open" in plan.message

    def test_an_open_execute_still_refuses_a_repo_local_token(self, tmp_path):
        assert auth.plan_token(
            self.private_token(tmp_path), str(tmp_path), True, True
        ).fatal

    def test_unusable_token_is_fatal_only_when_reads_are_authenticated(self, tmp_path):
        path = tmp_path / "token"
        path.write_text(TOKEN)
        path.chmod(0o644)
        assert auth.plan_token(str(path), None, False).fatal
        assert not auth.plan_token(str(path), None, True).fatal

    def test_token_inside_the_repo_is_fatal_either_way(self, tmp_path):
        path = self.private_token(tmp_path)
        for open_reads in (False, True):
            plan = auth.plan_token(path, str(tmp_path), open_reads)
            assert plan.fatal and plan.token is None
            assert "inside the repo" in plan.message


class TestOptions:
    def test_defaults_are_the_old_behavior(self):
        opts = options.resolve({}, lambda name, default=None: default)
        assert opts == options.Options(bind="127.0.0.1", open_reads=False)
        assert not opts.allow_non_loopback

    @pytest.mark.parametrize(
        "host", ["0.0.0.0", "100.64.0.1", "192.168.1.5", "macbook", ""]
    )
    def test_only_a_real_loopback_address_is_loopback(self, host):
        assert not options.is_loopback(host)
        assert options.Options(bind=host).allow_non_loopback

    @pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.53", "::1", " ::1 "])
    def test_loopback_addresses_do_not_allow_the_exposed_bind(self, host):
        assert options.is_loopback(host)
        assert not options.Options(bind=host).allow_non_loopback

    def test_env_beats_the_talon_setting(self):
        opts = options.resolve(
            {"TALON_PALETTE_BIND": "0.0.0.0", "TALON_PALETTE_OPEN_READS": "1"},
            lambda name, default=None: "127.0.0.1",
        )
        assert opts == options.Options(bind="0.0.0.0", open_reads=True)
        assert opts.allow_non_loopback

    def test_the_talon_setting_is_used_when_the_env_is_unset(self):
        values = {
            "user.palette_feed_bind": "100.64.0.1",
            "user.palette_feed_open_reads": True,
        }
        opts = options.resolve({}, lambda name, default=None: values.get(name, default))
        assert opts.bind == "100.64.0.1" and opts.open_reads

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("1", True),
            ("on", True),
            (" yes ", True),
            ("0", False),
            ("off", False),
            ("NO", False),
            (True, True),
            (False, False),
        ],
    )
    def test_switch_values(self, value, expected):
        assert options.parse_bool(value) is expected

    @pytest.mark.parametrize("value", ["maybe", "", 3, None, []])
    def test_unrecognized_switches_are_not_booleans(self, value):
        assert options.parse_bool(value) is None

    def test_an_unrecognized_env_switch_warns_and_falls_back(self):
        opts = options.resolve(
            {"TALON_PALETTE_OPEN_READS": "maybe"}, lambda name, default=None: default
        )
        assert not opts.open_reads
        assert opts.warnings and "TALON_PALETTE_OPEN_READS" in opts.warnings[0]

    def test_empty_env_values_fall_through_to_the_setting(self):
        opts = options.resolve(
            {"TALON_PALETTE_BIND": "   ", "TALON_PALETTE_OPEN_READS": ""},
            lambda name, default=None: (
                "100.64.0.1" if name == "user.palette_feed_bind" else True
            ),
        )
        assert opts.bind == "100.64.0.1" and opts.open_reads

    def test_describe_names_every_axis(self):
        assert options.Options().describe() == (
            "loopback only, reads token-gated, /execute token-gated"
        )
        assert options.Options(bind="0.0.0.0", open_reads=True).describe() == (
            "tailnet/network, reads open, /execute token-gated"
        )
        assert options.Options(open_execute=True).describe() == (
            "loopback only, reads token-gated, /execute open to any caller"
        )

    def test_open_execute_is_off_by_default(self):
        opts = options.resolve({}, lambda name, default=None: default)
        assert not opts.open_execute
        assert options.Options().open_execute is False

    def test_open_execute_comes_from_the_env_and_the_talon_setting(self):
        env = options.resolve({"TALON_PALETTE_OPEN_EXECUTE": "1"}, lambda n, d=None: d)
        assert env.open_execute
        setting = options.resolve(
            {}, lambda name, default=None: name == options.SETTING_OPEN_EXECUTE
        )
        assert setting.open_execute

    def test_the_env_beats_the_talon_setting_for_execute(self):
        opts = options.resolve(
            {"TALON_PALETTE_OPEN_EXECUTE": "off"},
            lambda name, default=None: name == options.SETTING_OPEN_EXECUTE,
        )
        assert not opts.open_execute

    def test_an_unrecognized_execute_switch_warns_and_stays_closed(self):
        opts = options.resolve(
            {"TALON_PALETTE_OPEN_EXECUTE": "maybe"}, lambda n, d=None: d
        )
        assert not opts.open_execute
        assert opts.warnings and "TALON_PALETTE_OPEN_EXECUTE" in opts.warnings[0]
