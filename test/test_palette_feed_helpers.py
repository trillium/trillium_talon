"""Tests for the pure palette_feed helpers (no Talon needed)."""

import io
import os
import threading

import pytest

from trillium.palette_feed import auth, denylist, dispatch, limits, serialize, simparse

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
