"""`POST /snippet`: audio validation, the recordings writer, the idempotency ledger, the service,
and the HTTP policy in front of them. No Talon, no real recordings folder: every folder is a pytest
temp dir and the key is a throwaway string.
"""

import hashlib
import http.client
import importlib.util
import io
import json
import os
import re
import shutil
import struct
import subprocess
import threading
import types
import wave

import pytest
import talon
from talon import Module

from trillium.palette_feed.limits import RateLimiter
from trillium.phone_receiver import (
    audio,
    keyfile,
    ledger,
    listener,
    metrics,
    recordings,
    snippet,
    snippet_ledger,
)
from trillium.phone_receiver.audio import AudioError

KEY = "k" * 43
OTHER_KEY = "z" * 43
KEYHDR = {keyfile.HEADER: KEY}
LOGIN = "trillium@example.com"


def uid(name="utt-1"):
    """A valid utterance id (hex, as `ledger.parse_id` wants) that differs per `name`."""
    return hashlib.sha256(name.encode()).hexdigest()[:32]


UID = uid()
NAME_RE = r"^phone-snippet-[A-Za-z0-9]{8}\.flac$"


def _ids(value):
    """Short test ids: a body's repr is kilobytes of bytes."""
    return f"{len(value)}B" if isinstance(value, bytes) else None


GLUE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "trillium",
    "phone_receiver",
    "phone_receiver_live.py",
)


def flac_bytes(
    samples=16000,
    rate=16000,
    channels=1,
    bits=16,
    min_block=4096,
    max_block=4096,
    total=None,
    audio_len=None,
    tail=b"",
    first=0x80,
    length=34,
):
    """A FLAC header with a real STREAMINFO and `audio_len` bytes that start like a frame."""
    total = samples if total is None else total
    packed = (rate << 44) | ((channels - 1) << 41) | ((bits - 1) << 36) | total
    si = (
        struct.pack(">HH", min_block, max_block)
        + b"\0" * 6
        + packed.to_bytes(8, "big")
        + b"\0" * 16
    )
    audio_len = max(samples, 8) if audio_len is None else audio_len
    frames = b"\xff\xf8" + b"\x01" * max(audio_len - 2, 0) if audio_len else b""
    return b"fLaC" + bytes([first]) + length.to_bytes(3, "big") + si + tail + frames


def wav_bytes(
    samples=16000,
    rate=16000,
    channels=1,
    bits=16,
    tag=1,
    data_size=None,
    pad_to=None,
    extra_chunks=b"",
    align=None,
):
    block = channels * bits // 8 if align is None else align
    data = b"\x01\x00" * samples
    size = len(data) if data_size is None else data_size
    fmt = struct.pack("<HHIIHH", tag, channels, rate, rate * block, block, bits)
    body = (
        b"WAVE"
        + b"fmt "
        + struct.pack("<I", len(fmt))
        + fmt
        + extra_chunks
        + b"data"
        + struct.pack("<I", size)
        + data
    )
    return b"RIFF" + struct.pack("<I", len(body)) + body


class TestFlac:
    def test_valid_header_reports_the_format(self):
        info = audio.parse_flac(flac_bytes(16000))
        assert (info.container, info.sample_rate, info.channels, info.bits) == (
            "flac",
            16000,
            1,
            16,
        )
        assert info.samples == 16000 and info.seconds == 1.0 and info.pcm is None

    @pytest.mark.parametrize(
        "body,code",
        [
            (b"RIFF" + b"\0" * 80, "not_flac"),
            (b"", "not_flac"),
            (b"fLaC" + b"\0" * 20, "truncated_audio"),
            (flac_bytes(rate=44100), "bad_sample_rate"),
            (flac_bytes(channels=2), "bad_channels"),
            (flac_bytes(bits=24), "bad_bit_depth"),
            (flac_bytes(total=0), "unfinalized_audio"),
            (flac_bytes(samples=800, total=800), "too_short"),
            (flac_bytes(samples=16000 * 31, total=16000 * 31), "too_long"),
            (flac_bytes(first=0x84), "bad_streaminfo"),  # block type 4, not STREAMINFO
            (flac_bytes(length=33), "bad_streaminfo"),
            (flac_bytes(min_block=8, max_block=4096), "bad_streaminfo"),
            (flac_bytes(min_block=4096, max_block=1024), "bad_streaminfo"),
            (flac_bytes(audio_len=0), "truncated_audio"),
            (flac_bytes(audio_len=1), "truncated_audio"),
        ],
        ids=_ids,
    )
    def test_rejects_with_a_stable_code(self, body, code):
        with pytest.raises(AudioError) as exc:
            audio.parse_flac(body)
        assert exc.value.code == code

    def test_audio_that_cannot_hold_the_claimed_length_is_refused(self):
        # 10 s claimed, 100 bytes of frames: below even 8 bytes per block
        with pytest.raises(AudioError) as exc:
            audio.parse_flac(flac_bytes(samples=160000, audio_len=8))
        assert exc.value.code == "truncated_audio"

    def test_audio_far_larger_than_the_claimed_length_is_refused(self):
        with pytest.raises(AudioError) as exc:
            audio.parse_flac(flac_bytes(samples=16000, audio_len=200_000))
        assert exc.value.code == "length_mismatch"

    def test_body_that_does_not_start_a_frame_after_the_header_is_refused(self):
        body = bytearray(flac_bytes(16000))
        body[8 + 34] = 0x00
        with pytest.raises(AudioError) as exc:
            audio.parse_flac(bytes(body))
        assert exc.value.code == "no_audio_frames"

    def test_metadata_blocks_after_streaminfo_are_skipped(self):
        # STREAMINFO no longer last (0x00); a 6 byte PADDING block (type 1) is.
        pad = bytes([0x81]) + (6).to_bytes(3, "big") + b"\0" * 6
        info = audio.parse_flac(flac_bytes(16000, first=0x00, tail=pad))
        assert info.samples == 16000

    def test_a_metadata_block_running_past_the_body_is_truncated(self):
        pad = bytes([0x81]) + (1 << 20).to_bytes(3, "big")
        with pytest.raises(AudioError) as exc:
            audio.parse_flac(flac_bytes(16000, first=0x00, tail=pad))
        assert exc.value.code == "truncated_audio"


class TestWav:
    def test_valid_wav_carries_its_pcm(self):
        info = audio.parse_wav(wav_bytes(16000))
        assert (info.container, info.sample_rate, info.samples) == ("wav", 16000, 16000)
        assert info.seconds == 1.0 and len(info.pcm) == 32000

    @pytest.mark.parametrize(
        "body,code",
        [
            (b"fLaC" + b"\0" * 60, "not_wav"),
            (b"RIFF\0\0\0\0AVI " + b"\0" * 40, "not_wav"),
            (wav_bytes(rate=48000), "bad_sample_rate"),
            (wav_bytes(channels=2), "bad_channels"),
            (wav_bytes(bits=8), "bad_bit_depth"),
            (wav_bytes(tag=3), "unsupported_wav_format"),  # IEEE float
            (wav_bytes(data_size=0), "unfinalized_audio"),
            (wav_bytes(data_size=0xFFFFFFFF), "unfinalized_audio"),
            (wav_bytes(data_size=40000), "truncated_audio"),
            (wav_bytes(samples=800), "too_short"),
            (wav_bytes(samples=16000 * 31), "too_long"),
            (wav_bytes(align=0), "bad_wav"),
            (wav_bytes(align=3), "bad_wav"),
            (
                wav_bytes(data_size=32001) + b"\0",
                "bad_wav",
            ),  # not a whole number of samples
        ],
        ids=_ids,
    )
    def test_rejects_with_a_stable_code(self, body, code):
        with pytest.raises(AudioError) as exc:
            audio.parse_wav(body)
        assert exc.value.code == code

    def test_data_before_fmt_is_refused(self):
        body = (
            b"RIFF"
            + struct.pack("<I", 20)
            + b"WAVEdata"
            + struct.pack("<I", 0)
            + b"\0" * 8
        )
        with pytest.raises(AudioError) as exc:
            audio.parse_wav(body)
        assert exc.value.code == "bad_wav"

    def test_chunks_between_fmt_and_data_are_walked_with_word_alignment(self):
        odd = (
            b"LIST" + struct.pack("<I", 3) + b"abc" + b"\0"
        )  # odd size, padded to even
        info = audio.parse_wav(wav_bytes(16000, extra_chunks=odd))
        assert info.samples == 16000

    def test_a_chunk_that_runs_off_the_body_is_refused(self):
        huge = b"LIST" + struct.pack("<I", 1 << 30)
        with pytest.raises(AudioError):
            audio.parse_wav(wav_bytes(16000, extra_chunks=huge))

    def test_an_endless_chunk_chain_is_cut_off(self):
        chain = (b"JUNK" + struct.pack("<I", 0)) * 200
        with pytest.raises(AudioError) as exc:
            audio.parse_wav(wav_bytes(16000, extra_chunks=chain))
        assert exc.value.code == "bad_wav"

    def test_extensible_pcm_is_accepted(self):
        fmt = struct.pack("<HHIIHH", 0xFFFE, 1, 16000, 32000, 2, 16)
        fmt += struct.pack("<HHI", 22, 16, 4) + struct.pack("<H", 1) + b"\0" * 14
        data = b"\x01\x00" * 16000
        body = (
            b"WAVE"
            + b"fmt "
            + struct.pack("<I", len(fmt))
            + fmt
            + b"data"
            + struct.pack("<I", len(data))
            + data
        )
        wav = b"RIFF" + struct.pack("<I", len(body)) + body
        assert audio.parse_wav(wav).samples == 16000


class TestInspect:
    def test_dispatches_on_the_container(self):
        assert audio.inspect("flac", flac_bytes()).container == "flac"
        assert audio.inspect("wav", wav_bytes()).container == "wav"

    def test_a_flac_body_under_a_wav_label_is_refused(self):
        with pytest.raises(AudioError) as exc:
            audio.inspect("wav", flac_bytes())
        assert exc.value.code == "not_wav"

    def test_nothing_but_audio_errors_escape(self, monkeypatch):
        monkeypatch.setattr(
            audio, "parse_flac", lambda body: (_ for _ in ()).throw(IndexError("boom"))
        )
        with pytest.raises(AudioError) as exc:
            audio.inspect("flac", b"x")
        assert exc.value.code == "bad_audio"

    def test_pcm_to_floats_scales_int16(self):
        pcm = struct.pack("<hhhh", 0, 16384, -32768, 32767)
        assert audio.pcm16_to_floats(pcm) == [0.0, 0.5, -1.0, 32767 / 32768]


def sine_wav(path, seconds=1.0):
    n = int(16000 * seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(
            b"".join(
                struct.pack("<h", int(8000 * ((i % 80) / 40 - 1))) for i in range(n)
            )
        )


class TestRealEncoders:
    """What the parsers read is what real tools write; skipped where the tool is absent."""

    @pytest.mark.skipif(shutil.which("flac") is None, reason="flac not installed")
    def test_flac_cli_output(self, tmp_path):
        sine_wav(tmp_path / "a.wav")
        subprocess.run(
            [
                "flac",
                "-s",
                "-f",
                str(tmp_path / "a.wav"),
                "-o",
                str(tmp_path / "a.flac"),
            ],
            check=True,
        )
        info = audio.inspect("flac", (tmp_path / "a.flac").read_bytes())
        assert info.samples == 16000 and info.sample_rate == 16000

    @pytest.mark.skipif(shutil.which("flac") is None, reason="flac not installed")
    def test_flac_cli_output_of_a_short_and_a_long_clip(self, tmp_path):
        for seconds in (0.2, 12.5):
            sine_wav(tmp_path / "a.wav", seconds)
            subprocess.run(
                [
                    "flac",
                    "-s",
                    "-f",
                    str(tmp_path / "a.wav"),
                    "-o",
                    str(tmp_path / "a.flac"),
                ],
                check=True,
            )
            info = audio.inspect("flac", (tmp_path / "a.flac").read_bytes())
            assert info.samples == int(16000 * seconds)

    @pytest.mark.skipif(
        shutil.which("afconvert") is None, reason="afconvert not installed"
    )
    def test_afconvert_flac_and_wav_output(self, tmp_path):
        sine_wav(tmp_path / "a.wav")
        subprocess.run(
            [
                "afconvert",
                "-f",
                "flac",
                "-d",
                "flac@16000",
                "-c",
                "1",
                str(tmp_path / "a.wav"),
                str(tmp_path / "b.flac"),
            ],
            check=True,
        )
        assert (
            audio.inspect("flac", (tmp_path / "b.flac").read_bytes()).samples == 16000
        )
        assert audio.inspect("wav", (tmp_path / "a.wav").read_bytes()).samples == 16000

    @pytest.mark.skipif(shutil.which("sox") is None, reason="sox not installed")
    def test_sox_streamed_flac_without_a_length_is_refused(self, tmp_path):
        # Piping out of sox leaves total_samples 0 in STREAMINFO: an unfinalized stream.
        sine_wav(tmp_path / "a.wav")
        raw = subprocess.run(
            ["sox", str(tmp_path / "a.wav"), "-t", "flac", "-"],
            check=True,
            capture_output=True,
        ).stdout
        try:
            info = audio.inspect("flac", raw)
        except AudioError as exc:
            assert exc.code == "unfinalized_audio"
        else:  # this sox rewound the header; then it must still read as the right length
            assert info.samples == 16000


def seq_suffix(*names):
    it = iter(names)
    return lambda: next(it)


class TestRecordingsWriter:
    def writer(self, tmp_path, *names):
        suffix = seq_suffix(*names) if names else recordings.random_suffix
        return recordings.RecordingsWriter(lambda: str(tmp_path), suffix)

    def test_writes_a_new_flac_named_like_talons(self, tmp_path):
        saved = self.writer(tmp_path).save(b"abc" * 100)
        assert re.match(NAME_RE, saved.name)
        assert saved.size == 300
        assert (tmp_path / saved.name).read_bytes() == b"abc" * 100

    def test_the_name_is_a_basename_only(self, tmp_path):
        saved = self.writer(tmp_path).save(b"x")
        assert os.path.basename(saved.name) == saved.name

    def test_no_temp_file_is_left_behind(self, tmp_path):
        self.writer(tmp_path).save(b"x" * 10)
        assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []
        assert len(list(tmp_path.iterdir())) == 1

    def test_the_file_is_synced_before_it_is_published_and_the_folder_after(
        self, tmp_path, monkeypatch
    ):
        events = []
        real_fsync, real_link = os.fsync, os.link
        monkeypatch.setattr(
            os, "fsync", lambda fd: (events.append("fsync"), real_fsync(fd))[1]
        )
        monkeypatch.setattr(
            os, "link", lambda a, b: (events.append("link"), real_link(a, b))[1]
        )
        self.writer(tmp_path).save(b"x" * 10)
        assert events == ["fsync", "link", "fsync"]  # file, publish, folder

    def test_a_taken_name_draws_a_new_one_and_the_existing_file_is_untouched(
        self, tmp_path
    ):
        taken = tmp_path / "phone-snippet-AAAAAAAA.flac"
        taken.write_bytes(b"precious")
        before = (taken.stat().st_mtime_ns, taken.stat().st_ino)
        # temp suffix, then the colliding final name, then a free one
        saved = self.writer(tmp_path, "TMPTMPTM", "AAAAAAAA", "BBBBBBBB").save(b"new")
        assert saved.name == "phone-snippet-BBBBBBBB.flac"
        assert taken.read_bytes() == b"precious"
        assert (taken.stat().st_mtime_ns, taken.stat().st_ino) == before

    def test_a_file_that_is_not_ours_is_never_replaced_even_with_the_same_name(
        self, tmp_path
    ):
        (tmp_path / "phone-snippet-AAAAAAAA.flac").write_bytes(b"theirs")
        self.writer(tmp_path, "TMPTMPTM", "AAAAAAAA", "CCCCCCCC").save(b"mine")
        assert (tmp_path / "phone-snippet-AAAAAAAA.flac").read_bytes() == b"theirs"

    def test_giving_up_after_too_many_collisions_leaves_the_folder_unchanged(
        self, tmp_path
    ):
        (tmp_path / "phone-snippet-AAAAAAAA.flac").write_bytes(b"theirs")
        w = recordings.RecordingsWriter(lambda: str(tmp_path), lambda: "AAAAAAAA")
        # the temp name `.phone-snippet-AAAAAAAA.tmp` is free; every final name is taken
        with pytest.raises(recordings.SaveError) as exc:
            w.save(b"x")
        assert exc.value.code == "save_failed"
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "phone-snippet-AAAAAAAA.flac"
        ]

    def test_a_write_failure_midway_leaves_nothing(self, tmp_path, monkeypatch):
        def boom(fd, data):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(os, "write", boom)
        with pytest.raises(recordings.SaveError) as exc:
            self.writer(tmp_path).save(b"x" * 10)
        assert exc.value.code == "save_failed"
        assert list(tmp_path.iterdir()) == []

    def test_a_short_write_is_continued_until_every_byte_is_out(
        self, tmp_path, monkeypatch
    ):
        real = os.write
        monkeypatch.setattr(os, "write", lambda fd, data: real(fd, bytes(data[:3])))
        saved = self.writer(tmp_path).save(b"0123456789")
        assert (tmp_path / saved.name).read_bytes() == b"0123456789"

    def test_an_fsync_failure_leaves_no_final_file(self, tmp_path, monkeypatch):
        def boom(fd):
            raise OSError(5, "I/O error")

        monkeypatch.setattr(os, "fsync", boom)
        with pytest.raises(recordings.SaveError):
            self.writer(tmp_path).save(b"x" * 10)
        assert list(tmp_path.iterdir()) == []

    def test_without_hard_links_it_falls_back_to_a_guarded_rename(
        self, tmp_path, monkeypatch
    ):
        import errno

        def nolink(a, b):
            raise OSError(errno.EPERM, "no links here")

        monkeypatch.setattr(os, "link", nolink)
        (tmp_path / "phone-snippet-AAAAAAAA.flac").write_bytes(b"theirs")
        saved = self.writer(tmp_path, "TMPTMPTM", "AAAAAAAA", "DDDDDDDD").save(b"mine")
        assert saved.name == "phone-snippet-DDDDDDDD.flac"
        assert (tmp_path / saved.name).read_bytes() == b"mine"
        assert (tmp_path / "phone-snippet-AAAAAAAA.flac").read_bytes() == b"theirs"
        assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]

    def test_other_link_errors_are_save_failures_not_renames(
        self, tmp_path, monkeypatch
    ):
        def deny(a, b):
            raise PermissionError(13, "denied")

        monkeypatch.setattr(os, "link", deny)
        with pytest.raises(recordings.SaveError):
            self.writer(tmp_path).save(b"x")
        assert list(tmp_path.iterdir()) == []

    def test_a_missing_folder_is_reported_and_not_created(self, tmp_path):
        missing = tmp_path / "recordings"
        w = recordings.RecordingsWriter(lambda: str(missing))
        with pytest.raises(recordings.SaveError) as exc:
            w.save(b"x")
        assert exc.value.code == "no_recordings_dir"
        assert not missing.exists()

    @pytest.mark.parametrize("value", [None, ""])
    def test_no_folder_from_the_provider_is_reported(self, value):
        w = recordings.RecordingsWriter(lambda: value)
        with pytest.raises(recordings.SaveError) as exc:
            w.save(b"x")
        assert exc.value.code == "no_recordings_dir"

    def test_a_read_only_folder_is_reported(self, tmp_path):
        ro = tmp_path / "ro"
        ro.mkdir()
        ro.chmod(0o500)
        try:
            if os.access(ro, os.W_OK):  # running as root
                pytest.skip("directory permissions are not enforced here")
            w = recordings.RecordingsWriter(lambda: str(ro))
            with pytest.raises(recordings.SaveError) as exc:
                w.save(b"x")
            assert exc.value.code == "no_recordings_dir"
        finally:
            ro.chmod(0o700)

    def test_it_never_lists_or_reads_or_removes_anything_but_its_own_temp(
        self, tmp_path, monkeypatch
    ):
        existing = tmp_path / "hello world-abcdefgh.flac"
        existing.write_bytes(b"theirs")
        seen = []
        for name in ("listdir", "scandir", "remove", "rmdir", "replace"):
            monkeypatch.setattr(os, name, lambda *a, _n=name, **k: seen.append(_n))
        real_unlink, real_open = os.unlink, os.open
        unlinked, opened = [], []
        monkeypatch.setattr(
            os, "unlink", lambda p: (unlinked.append(p), real_unlink(p))[1]
        )
        monkeypatch.setattr(
            os,
            "open",
            lambda p, flags, *a: (opened.append((p, flags)), real_open(p, flags, *a))[
                1
            ],
        )
        self.writer(tmp_path).save(b"x" * 10)
        assert seen == []
        assert [os.path.basename(p) for p in unlinked] == [
            os.path.basename(p) for p in unlinked
        ]
        assert all(
            os.path.basename(p).startswith(recordings.TMP_PREFIX) for p in unlinked
        )
        assert str(existing) not in [p for p, _ in opened]
        assert existing.read_bytes() == b"theirs"

    def test_the_final_file_is_world_readable_not_executable(self, tmp_path):
        saved = self.writer(tmp_path).save(b"x")
        mode = (tmp_path / saved.name).stat().st_mode & 0o777
        assert mode & 0o111 == 0 and mode & 0o400

    # --- reserve / confirm / first: the pending-entry handshake ---

    def test_reserve_gives_a_name_in_talons_shape_and_creates_nothing(self, tmp_path):
        name = self.writer(tmp_path).reserve()
        assert re.match(NAME_RE, name)
        assert list(tmp_path.iterdir()) == []

    def test_save_tries_the_reserved_name_first(self, tmp_path):
        w = self.writer(tmp_path)
        name = w.reserve()
        assert w.save(b"abc", name).name == name
        assert (tmp_path / name).read_bytes() == b"abc"

    def test_a_reserved_name_that_is_taken_is_not_replaced(self, tmp_path):
        (tmp_path / "phone-snippet-AAAAAAAA.flac").write_bytes(b"theirs")
        w = self.writer(tmp_path, "TMPTMPTM", "BBBBBBBB")
        saved = w.save(b"mine", "phone-snippet-AAAAAAAA.flac")
        assert saved.name == "phone-snippet-BBBBBBBB.flac"
        assert (tmp_path / "phone-snippet-AAAAAAAA.flac").read_bytes() == b"theirs"

    @pytest.mark.parametrize(
        "first",
        ["../x.flac", "other.flac", "phone-snippet-short.flac", "/etc/passwd", ""],
    )
    def test_a_first_name_that_is_not_ours_is_ignored(self, tmp_path, first):
        saved = self.writer(tmp_path).save(b"x", first)
        assert re.match(NAME_RE, saved.name) and saved.name != first
        assert [p.name for p in tmp_path.iterdir()] == [saved.name]

    def test_confirm_reports_the_size_of_a_file_it_can_stat(self, tmp_path):
        w = self.writer(tmp_path)
        saved = w.save(b"abc" * 10)
        assert w.confirm(saved.name) == 30

    def test_confirm_of_a_missing_file_is_none(self, tmp_path):
        assert self.writer(tmp_path).confirm("phone-snippet-ZZZZZZZZ.flac") is None

    @pytest.mark.parametrize(
        "name",
        [
            "../x.flac",
            "x.flac",
            "phone-snippet-ZZZZZZZZ.wav",
            "",
            "a/phone-snippet-ZZZZZZZZ.flac",
        ],
    )
    def test_confirm_refuses_names_it_did_not_hand_out_without_a_stat(
        self, tmp_path, monkeypatch, name
    ):
        monkeypatch.setattr(
            os, "stat", lambda *a, **k: pytest.fail("stat of a foreign name")
        )
        assert self.writer(tmp_path).confirm(name) is None

    def test_confirm_never_opens_the_file(self, tmp_path, monkeypatch):
        w = self.writer(tmp_path)
        saved = w.save(b"x" * 5)
        opened = []
        real_open = os.open
        monkeypatch.setattr(
            os,
            "open",
            lambda path, *a, **k: (opened.append(str(path)), real_open(path, *a, **k))[
                1
            ],
        )
        w.confirm(saved.name)
        assert opened == [str(tmp_path)]  # the folder, for its fsync; never the file

    def test_confirm_syncs_the_folder_and_fails_if_it_cannot(
        self, tmp_path, monkeypatch
    ):
        w = self.writer(tmp_path)
        saved = w.save(b"x")

        def boom(fd):
            raise OSError(5, "I/O error")

        monkeypatch.setattr(os, "fsync", boom)
        with pytest.raises(recordings.SaveError) as exc:
            w.confirm(saved.name)
        assert exc.value.code == "save_failed"

    def test_confirm_without_a_folder_is_reported(self, tmp_path):
        w = recordings.RecordingsWriter(lambda: str(tmp_path / "nope"))
        with pytest.raises(recordings.SaveError) as exc:
            w.confirm("phone-snippet-ZZZZZZZZ.flac")
        assert exc.value.code == "no_recordings_dir"


class TestLedger:
    def test_round_trip_and_persistence(self, tmp_path):
        path = tmp_path / "snippets.jsonl"
        a = snippet_ledger.SnippetLedger(str(path))
        assert a.get("one") is None
        a.put("one", {"ok": True, "name": "x.flac"})
        assert a.get("one") == {"ok": True, "name": "x.flac"}
        b = snippet_ledger.SnippetLedger(str(path))  # a restart
        assert b.get("one") == {"ok": True, "name": "x.flac"}

    def test_get_returns_a_copy(self, tmp_path):
        a = snippet_ledger.SnippetLedger(str(tmp_path / "l.jsonl"))
        a.put("one", {"ok": True})
        a.get("one")["ok"] = False
        assert a.get("one") == {"ok": True}

    def test_a_torn_last_line_is_skipped_and_the_rest_kept(self, tmp_path):
        path = tmp_path / "l.jsonl"
        path.write_text(
            json.dumps({"id": "a", "ack": {"n": 1}}) + "\n" + '{"id":"b","ack":{"n"'
        )
        l = snippet_ledger.SnippetLedger(str(path))
        assert l.get("a") == {"n": 1} and l.get("b") is None

    def test_garbled_rows_are_skipped(self, tmp_path):
        path = tmp_path / "l.jsonl"
        path.write_text(
            'nope\n[]\n{"id":1,"ack":{}}\n{"id":"ok","ack":{"n":2}}\n{"id":"x","ack":"s"}\n'
        )
        l = snippet_ledger.SnippetLedger(str(path))
        assert l.get("ok") == {"n": 2} and l.get("x") is None

    def test_oldest_entries_fall_out_past_capacity(self, tmp_path):
        l = snippet_ledger.SnippetLedger(str(tmp_path / "l.jsonl"), capacity=3)
        for i in range(5):
            l.put(f"id{i}", {"n": i})
        assert [l.get(f"id{i}") for i in range(5)] == [
            None,
            None,
            {"n": 2},
            {"n": 3},
            {"n": 4},
        ]

    def test_a_long_file_is_compacted_at_load(self, tmp_path):
        path = tmp_path / "l.jsonl"
        first = snippet_ledger.SnippetLedger(str(path), capacity=2)
        for i in range(7):
            first.put(f"id{i}", {"n": i})
        assert len(path.read_text().splitlines()) == 7
        second = snippet_ledger.SnippetLedger(str(path), capacity=2)
        assert second.get("id6") == {"n": 6}  # triggers the load and the rewrite
        assert len(path.read_text().splitlines()) == 2
        assert snippet_ledger.SnippetLedger(str(path), capacity=2).get("id5") == {
            "n": 5
        }

    def test_the_file_is_private_and_holds_no_audio_or_key(self, tmp_path):
        path = tmp_path / "sub" / "l.jsonl"
        l = snippet_ledger.SnippetLedger(str(path))
        l.put("one", {"ok": True, "name": "phone-snippet-AAAAAAAA.flac"})
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700

    def test_constructing_one_touches_no_disk(self, tmp_path):
        path = tmp_path / "nope" / "l.jsonl"
        snippet_ledger.SnippetLedger(str(path))
        assert not path.parent.exists()

    def test_an_unwritable_path_raises_but_keeps_the_entry_in_memory(self, tmp_path):
        blocker = tmp_path / "file"
        blocker.write_text("not a dir")
        l = snippet_ledger.SnippetLedger(str(blocker / "l.jsonl"))
        with pytest.raises(snippet_ledger.LedgerError):
            l.put("one", {"ok": True})
        assert l.get("one") == {"ok": True}

    def test_a_ledger_without_a_path_lives_in_memory(self):
        l = snippet_ledger.SnippetLedger(None)
        l.put("one", {"n": 1})
        assert l.get("one") == {"n": 1}


class FakeWriter:
    """Stands in for RecordingsWriter: records saves, can fail on demand."""

    def __init__(self, files=None):
        self.saved = []
        self.files = (
            {} if files is None else files
        )  # name -> size, shared across "restarts"
        self.fail = None
        self.gate = None
        self.reserved = 0

    def reserve(self):
        self.reserved += 1
        return f"phone-snippet-{self.reserved:08d}.flac"

    def save(self, data, first=None):
        if self.gate is not None:
            self.gate.wait(2)
        if self.fail:
            raise self.fail
        self.saved.append(data)
        name = first or f"phone-snippet-{len(self.saved):08d}.flac"
        self.files[name] = len(data)
        return recordings.Saved(name, len(data))

    def confirm(self, name):
        return self.files.get(name)


def make_service(tmp_path, enabled=True, encode=None, writer=None, led=None, log=None):
    return snippet.SnippetService(
        writer or FakeWriter(),
        led or snippet_ledger.SnippetLedger(str(tmp_path / "ledger.jsonl")),
        lambda: enabled,
        encode,
        log=log or (lambda *_: None),
    )


def headers(**extra):
    return {k.lower(): v for k, v in extra.items()}


def sha(body):
    return hashlib.sha256(body).hexdigest()


class TestSnippetService:
    def handle(self, svc, body, key=UID, container="flac", **extra):
        return svc.handle(container, key, body, headers(**extra), metrics.Trace())

    def test_saves_a_flac_byte_for_byte_and_acks_with_both_checksums(self, tmp_path):
        svc = make_service(tmp_path)
        body = flac_bytes(16000)
        out = self.handle(svc, body)
        assert out.status == 200
        assert svc._writer.saved == [body]
        ack = out.body
        assert ack["ok"] is True and ack["id"] == UID and ack["duplicate"] is False
        assert ack["name"] == "phone-snippet-00000001.flac"
        assert ack["received_bytes"] == ack["stored_bytes"] == len(body)
        assert ack["received_sha256"] == ack["stored_sha256"] == sha(body)
        assert (ack["container"], ack["converted"]) == ("flac", False)
        assert (ack["sample_rate"], ack["channels"], ack["seconds"]) == (16000, 1, 1.0)

    def test_the_ack_never_has_a_directory_in_it(self, tmp_path):
        out = self.handle(make_service(tmp_path), flac_bytes())
        assert os.sep not in json.dumps(out.body)

    def test_a_repeat_returns_the_stored_ack_and_writes_nothing(self, tmp_path):
        svc = make_service(tmp_path)
        body = flac_bytes()
        first = self.handle(svc, body)
        again = self.handle(svc, body)
        assert again.status == 200 and again.body["duplicate"] is True
        assert {k: v for k, v in again.body.items() if k != "duplicate"} == {
            k: v for k, v in first.body.items() if k != "duplicate"
        }
        assert len(svc._writer.saved) == 1

    def test_a_repeat_survives_a_restart(self, tmp_path):
        body = flac_bytes()
        first = make_service(tmp_path)
        a = self.handle(first, body)
        second = make_service(tmp_path)  # new process: same ledger file, new writer
        b = self.handle(second, body)
        assert b.body["duplicate"] is True and b.body["name"] == a.body["name"]
        assert second._writer.saved == []

    def test_a_repeat_is_answered_even_if_it_would_now_be_invalid_audio(self, tmp_path):
        svc = make_service(tmp_path)
        body = flac_bytes()
        self.handle(svc, body)
        assert self.handle(svc, body, **{snippet.RATE_HEADER: "44100"}).status == 200

    def test_the_same_id_with_different_bytes_is_a_conflict(self, tmp_path):
        svc = make_service(tmp_path)
        self.handle(svc, flac_bytes(16000))
        out = self.handle(svc, flac_bytes(24000))
        assert (out.status, out.body["error"]) == (409, "id_conflict")
        assert len(svc._writer.saved) == 1

    def test_different_ids_with_the_same_audio_are_two_files(self, tmp_path):
        svc = make_service(tmp_path)
        body = flac_bytes()
        self.handle(svc, body, uid("a"))
        self.handle(svc, body, uid("b"))
        assert len(svc._writer.saved) == 2

    def test_concurrent_uploads_of_one_id_write_one_file(self, tmp_path):
        svc = make_service(tmp_path)
        svc._writer.gate = threading.Event()
        body = flac_bytes()
        results = []
        threads = [
            threading.Thread(target=lambda: results.append(self.handle(svc, body)))
            for _ in range(5)
        ]
        for t in threads:
            t.start()
        svc._writer.gate.set()
        for t in threads:
            t.join(5)
        assert len(results) == 5 and all(r.status == 200 for r in results)
        assert len(svc._writer.saved) == 1
        assert sorted(r.body["duplicate"] for r in results) == [False] + [True] * 4

    def test_a_declared_checksum_that_matches_is_accepted(self, tmp_path):
        body = flac_bytes()
        out = self.handle(
            make_service(tmp_path), body, **{snippet.SHA_HEADER: sha(body).upper()}
        )
        assert out.status == 200

    def test_a_declared_checksum_that_does_not_match_is_refused(self, tmp_path):
        svc = make_service(tmp_path)
        out = self.handle(svc, flac_bytes(), **{snippet.SHA_HEADER: "0" * 64})
        assert (out.status, out.body["error"]) == (422, "checksum_mismatch")
        assert svc._writer.saved == []

    def test_a_malformed_checksum_header_is_refused(self, tmp_path):
        out = self.handle(
            make_service(tmp_path), flac_bytes(), **{snippet.SHA_HEADER: "abc"}
        )
        assert (out.status, out.body["error"]) == (400, "bad_checksum_header")

    def test_the_declared_sample_rate_must_agree_with_the_audio(self, tmp_path):
        svc = make_service(tmp_path)
        ok = self.handle(svc, flac_bytes(), uid("a"), **{snippet.RATE_HEADER: "16000"})
        bad = self.handle(svc, flac_bytes(), uid("b"), **{snippet.RATE_HEADER: "8000"})
        junk = self.handle(svc, flac_bytes(), uid("c"), **{snippet.RATE_HEADER: "fast"})
        assert ok.status == 200
        assert (bad.status, bad.body["error"], bad.body["want"]) == (
            422,
            "sample_rate_mismatch",
            16000,
        )
        assert (junk.status, junk.body["error"]) == (400, "bad_sample_rate_header")
        assert len(svc._writer.saved) == 1

    @pytest.mark.parametrize(
        "body,code",
        [
            (flac_bytes(rate=44100), "bad_sample_rate"),
            (flac_bytes(samples=800), "too_short"),
            (flac_bytes(samples=16000 * 31), "too_long"),
            (b"not audio at all", "not_flac"),
        ],
        ids=_ids,
    )
    def test_invalid_audio_is_422_and_writes_nothing(self, tmp_path, body, code):
        svc = make_service(tmp_path)
        out = self.handle(svc, body)
        assert (out.status, out.body["error"]) == (422, code)
        assert svc._writer.saved == []
        assert svc._ledger.get(UID) is None  # so a corrected upload can reuse the id

    def test_a_wav_is_converted_and_the_ack_says_so(self, tmp_path):
        seen = []

        def encode(pcm):
            seen.append(pcm)
            return flac_bytes(16000)

        svc = make_service(tmp_path, encode=encode)
        body = wav_bytes(16000)
        out = self.handle(svc, body, container="wav")
        assert out.status == 200 and out.body["converted"] is True
        assert out.body["container"] == "wav"
        assert len(seen[0]) == 32000
        assert svc._writer.saved == [flac_bytes(16000)]
        assert out.body["received_sha256"] == sha(body)
        assert out.body["stored_sha256"] == sha(flac_bytes(16000))
        assert out.body["received_bytes"] == len(body)
        assert out.body["stored_bytes"] == len(flac_bytes(16000))

    def test_a_wav_without_an_encoder_is_503(self, tmp_path):
        svc = make_service(tmp_path)
        out = self.handle(svc, wav_bytes(), container="wav")
        assert (out.status, out.body["error"]) == (503, "wav_unavailable")
        assert svc._writer.saved == []

    def test_an_encoder_that_fails_is_500_and_leaves_the_id_free(self, tmp_path):
        def encode(pcm):
            raise RuntimeError("encoder fell over")

        logged = []
        svc = make_service(tmp_path, encode=encode, log=lambda *a: logged.append(a))
        out = self.handle(svc, wav_bytes(), container="wav")
        assert (out.status, out.body["error"]) == (500, "encode_failed")
        assert svc._ledger.get(UID) is None
        assert "encoder fell over" not in repr(logged)

    @pytest.mark.parametrize(
        "code,status",
        [("no_recordings_dir", 503), ("save_failed", 500), ("other", 500)],
    )
    def test_a_failed_save_is_an_error_and_a_retry_saves_afresh(
        self, tmp_path, code, status
    ):
        svc = make_service(tmp_path)
        svc._writer.fail = recordings.SaveError(code)
        out = self.handle(svc, flac_bytes())
        assert out.status == status and out.body["ok"] is False
        pending = svc._ledger.get(UID)
        assert (
            pending["pending"] is True
        )  # the file may have landed: a retry checks first
        svc._writer.fail = None
        again = self.handle(svc, flac_bytes())  # no file under that name: saved afresh
        assert again.status == 200 and again.body["duplicate"] is False
        assert len(svc._writer.saved) == 1
        assert "pending" not in svc._ledger.get(UID)

    def test_an_unexpected_save_error_is_500_save_failed(self, tmp_path):
        svc = make_service(tmp_path)
        svc._writer.fail = ValueError("surprise")
        out = self.handle(svc, flac_bytes())
        assert (out.status, out.body["error"]) == (500, "save_failed")

    def test_a_ledger_that_cannot_be_written_saves_nothing(self, tmp_path):
        blocker = tmp_path / "file"
        blocker.write_text("x")
        logged = []
        svc = make_service(
            tmp_path,
            led=snippet_ledger.SnippetLedger(str(blocker / "l.jsonl")),
            log=lambda *a: logged.append(a),
        )
        out = self.handle(svc, flac_bytes())
        assert (out.status, out.body["error"]) == (500, "ledger_write_failed")
        assert svc._writer.saved == []  # no durable record to settle against, no file
        assert logged

    def test_a_ledger_that_fails_after_the_save_still_acks_and_the_retry_settles(
        self, tmp_path
    ):
        class Flaky(snippet_ledger.SnippetLedger):
            puts = 0

            def put(self, key, ack):
                self.puts += 1
                if self.puts == 2:  # the final entry, not the pending one
                    super().put(key, ack)  # keep it in memory...
                    raise snippet_ledger.LedgerError("ledger_write_failed")
                super().put(key, ack)

        logged = []
        led = Flaky(str(tmp_path / "l.jsonl"))
        svc = make_service(tmp_path, led=led, log=lambda *a: logged.append(a))
        body = flac_bytes()
        out = self.handle(svc, body)
        assert out.status == 200 and out.body["duplicate"] is False and logged
        again = self.handle(svc, body)
        assert again.body["duplicate"] is True and len(svc._writer.saved) == 1

    def test_the_ack_comes_after_the_file_and_the_ledger_entry(self, tmp_path):
        events = []

        class W(FakeWriter):
            def save(self, data, first=None):
                events.append("save")
                return super().save(data, first)

        class L(snippet_ledger.SnippetLedger):
            def put(self, key, ack):
                events.append("final" if "pending" not in ack else "pending")
                super().put(key, ack)

        svc = make_service(tmp_path, writer=W(), led=L(str(tmp_path / "x.jsonl")))
        self.handle(svc, flac_bytes())
        assert events == ["pending", "save", "final"]

    # --- the crash window: a pending entry names the file before it is written ---

    def test_a_crash_after_the_file_landed_is_settled_not_saved_twice(self, tmp_path):
        class Crash(BaseException):
            """Not an Exception: nothing in the service may swallow it, like a killed process."""

        folder = tmp_path / "recordings"
        folder.mkdir()

        class DiesAfterLanding(recordings.RecordingsWriter):
            def save(self, data, first=None):
                super().save(data, first)
                raise Crash

        def service(writer):
            return snippet.SnippetService(
                writer,
                snippet_ledger.SnippetLedger(str(tmp_path / "l.jsonl")),
                lambda: True,
                log=lambda *_: None,
            )

        body = flac_bytes()
        with pytest.raises(Crash):
            self.handle(service(DiesAfterLanding(lambda: str(folder))), body)
        (landed,) = [p.name for p in folder.iterdir()]

        out = self.handle(
            service(recordings.RecordingsWriter(lambda: str(folder))), body
        )
        assert out.status == 200 and out.body["duplicate"] is True
        assert out.body["name"] == landed
        assert [p.name for p in folder.iterdir()] == [landed]  # still the one file
        assert "pending" not in out.body
        # and it is now a plain stored ack
        again = self.handle(
            service(recordings.RecordingsWriter(lambda: str(folder))), body
        )
        assert again.body["duplicate"] is True and again.body["name"] == landed

    def test_a_crash_before_the_file_landed_saves_it_once_on_the_retry(self, tmp_path):
        led = snippet_ledger.SnippetLedger(str(tmp_path / "l.jsonl"))
        pending = {
            "ok": True,
            "id": UID,
            "name": "phone-snippet-ZZZZZZZZ.flac",
            "received_sha256": sha(flac_bytes()),
            "stored_bytes": len(flac_bytes()),
            "pending": True,
        }
        led.put(UID, pending)
        svc = make_service(tmp_path, led=led)
        out = self.handle(svc, flac_bytes())
        assert out.status == 200 and out.body["duplicate"] is False
        assert len(svc._writer.saved) == 1 and "pending" not in out.body

    def test_a_pending_file_of_the_wrong_size_is_not_trusted(self, tmp_path):
        body = flac_bytes()
        name = "phone-snippet-ZZZZZZZZ.flac"
        led = snippet_ledger.SnippetLedger(str(tmp_path / "l.jsonl"))
        led.put(
            UID,
            {
                "ok": True,
                "id": UID,
                "name": name,
                "received_sha256": sha(body),
                "stored_bytes": len(body),
                "pending": True,
            },
        )
        svc = make_service(tmp_path, led=led, writer=FakeWriter({name: len(body) - 1}))
        out = self.handle(svc, body)
        assert out.body["duplicate"] is False and len(svc._writer.saved) == 1

    def test_a_pending_entry_for_other_bytes_is_a_conflict(self, tmp_path):
        svc = make_service(tmp_path)
        svc._writer.fail = recordings.SaveError("save_failed")
        self.handle(svc, flac_bytes(16000))
        svc._writer.fail = None
        out = self.handle(svc, flac_bytes(24000))
        assert (out.status, out.body["error"]) == (409, "id_conflict")
        assert svc._writer.saved == []

    def test_a_confirm_that_cannot_sync_the_folder_is_an_error_and_keeps_the_entry(
        self, tmp_path
    ):
        class W(FakeWriter):
            def confirm(self, name):
                raise recordings.SaveError("save_failed")

        svc = make_service(tmp_path, writer=W())
        svc._writer.fail = recordings.SaveError("save_failed")
        self.handle(svc, flac_bytes())
        svc._writer.fail = None
        out = self.handle(svc, flac_bytes())
        assert (out.status, out.body["error"]) == (500, "save_failed")
        assert svc._ledger.get(UID)["pending"] is True and svc._writer.saved == []

    # --- the pieces the listener uses around the table ---

    def test_stored_gives_the_finished_ack_only(self, tmp_path):
        svc = make_service(tmp_path)
        assert svc.stored(UID) is None  # unknown
        svc._writer.fail = recordings.SaveError("save_failed")
        self.handle(svc, flac_bytes())
        assert svc.stored(UID) is None  # pending is not done
        svc._writer.fail = None
        self.handle(svc, flac_bytes())
        got = svc.stored(UID)
        assert got["ok"] is True and got["id"] == UID and "pending" not in got

    def test_stored_treats_an_unreadable_ledger_as_unknown(self, tmp_path):
        class Broken(snippet_ledger.SnippetLedger):
            def get(self, key):
                raise OSError("disk gone")

        assert make_service(tmp_path, led=Broken(None)).stored(UID) is None

    def test_replay_acks_the_same_bytes_and_conflicts_on_others(self, tmp_path):
        svc = make_service(tmp_path)
        body = flac_bytes()
        ack = self.handle(svc, body).body
        again = svc.replay(ack, body)
        assert again.status == 200 and again.body["duplicate"] is True
        other = svc.replay(ack, flac_bytes(24000))
        assert (other.status, other.body["error"]) == (409, "id_conflict")

    @pytest.mark.parametrize(
        "stored",
        [{"ok": False, "error": "not_flac"}, {"ok": True}, {}],
    )
    def test_replay_leaves_a_stored_refusal_to_the_caller(self, tmp_path, stored):
        assert make_service(tmp_path).replay(stored, flac_bytes()) is None

    def test_every_snippet_refusal_that_leaves_the_id_usable_is_retriable(self):
        for code in snippet.RETRIABLE_ERRORS:
            assert listener.retriable(
                listener.Response(500, {"ok": False, "error": code})
            )
        for code in ("checksum_mismatch", "not_flac", "sample_rate_mismatch"):
            # 422s are retriable on status; a 409 in_progress is not a refusal to reuse
            assert listener.retriable(
                listener.Response(422, {"ok": False, "error": code})
            )
        assert not listener.retriable(
            listener.Response(409, {"ok": False, "error": "in_progress"})
        )

    def test_the_trace_marks_decode_and_dispatch(self, tmp_path):
        ticks = iter([0.0, 0.010, 0.030, 0.080, 0.1, 0.2])
        trace = metrics.Trace(lambda: next(ticks))
        trace.mark("received")
        svc = make_service(tmp_path)
        svc.handle("flac", UID, flac_bytes(), headers(), trace)
        t = trace.timings()
        assert (
            t["receive_ms"] == 10.0
            and t["decode_ms"] == 20.0
            and t["dispatch_ms"] == 50.0
        )

    def test_a_disabled_service_reports_it(self, tmp_path):
        assert make_service(tmp_path, enabled=False).enabled() is False

    def test_a_setting_that_raises_counts_as_off(self, tmp_path):
        def boom():
            raise RuntimeError("settings gone")

        svc = snippet.SnippetService(
            FakeWriter(), snippet_ledger.SnippetLedger(None), boom
        )
        assert svc.enabled() is False

    def test_a_real_writer_end_to_end(self, tmp_path):
        folder = tmp_path / "recordings"
        folder.mkdir()
        existing = folder / "hello there-abcdefgh.flac"
        existing.write_bytes(b"theirs")
        svc = snippet.SnippetService(
            recordings.RecordingsWriter(lambda: str(folder)),
            snippet_ledger.SnippetLedger(str(tmp_path / "l.jsonl")),
            lambda: True,
            log=lambda *_: None,
        )
        body = flac_bytes()
        out = self.handle(svc, body)
        assert (folder / out.body["name"]).read_bytes() == body
        assert existing.read_bytes() == b"theirs"
        assert sorted(p.name for p in folder.iterdir()) == sorted(
            [existing.name, out.body["name"]]
        )
        assert self.handle(svc, body).body["duplicate"] is True
        assert len(list(folder.iterdir())) == 2


def make_api(tmp_path, *, key=KEY, enabled=True, snippets=True, met=True, **kw):
    svc = make_service(tmp_path, enabled=enabled, encode=lambda pcm: flac_bytes(16000))
    api = listener.ListenerApi(
        types.SimpleNamespace(),  # the emission backend: never reached by these tests
        lambda: "emission",
        lambda: LOGIN,
        key=(lambda: key) if key is not None else None,
        snippets=svc if snippets else None,
        metrics=metrics.Metrics() if met else None,
        limiter=RateLimiter(1000, 1.0),
        log=lambda *_: None,
        **kw,
    )
    return api, svc


FLAC = "audio/flac"


def post(
    api,
    body,
    ctype=FLAC,
    key=UID,
    auth=None,
    extra=None,
    length=None,
    path="/snippet",
):
    h = {"Content-Length": str(len(body) if length is None else length)}
    if ctype:
        h["Content-Type"] = ctype
    if key is not None:
        h[ledger.ID_HEADER] = key
    h.update(KEYHDR if auth is None else auth)
    h.update(extra or {})
    return api.handle("POST", path, h, io.BytesIO(body))


class TestSnippetHttp:
    def test_a_good_upload_is_200_with_the_ack(self, tmp_path):
        api, svc = make_api(tmp_path)
        r = post(api, flac_bytes())
        assert (
            r.status == 200
            and r.body["ok"]
            and r.body["name"].startswith("phone-snippet-")
        )
        assert len(svc._writer.saved) == 1

    @pytest.mark.parametrize(
        "ctype", ["audio/flac", "audio/x-flac", "AUDIO/FLAC; charset=x"]
    )
    def test_flac_content_types(self, tmp_path, ctype):
        api, _ = make_api(tmp_path)
        assert post(api, flac_bytes(), ctype=ctype).status == 200

    @pytest.mark.parametrize(
        "ctype", ["audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"]
    )
    def test_wav_content_types(self, tmp_path, ctype):
        api, _ = make_api(tmp_path)
        r = post(api, wav_bytes(), ctype=ctype)
        assert r.status == 200 and r.body["converted"] is True

    @pytest.mark.parametrize(
        "ctype", [None, "", "application/json", "audio/mpeg", "audio/L16"]
    )
    def test_other_content_types_are_415_and_say_what_is_wanted(self, tmp_path, ctype):
        api, svc = make_api(tmp_path)
        r = post(api, flac_bytes(), ctype=ctype)
        assert r.status == 415 and "audio/flac" in r.body["want"]
        assert svc._writer.saved == []

    def test_a_flac_body_labelled_wav_is_422(self, tmp_path):
        api, _ = make_api(tmp_path)
        r = post(api, flac_bytes(), ctype="audio/wav")
        assert (r.status, r.body["error"]) == (422, "not_wav")

    def test_header_names_are_case_insensitive(self, tmp_path):
        api, _ = make_api(tmp_path)
        h = {
            "CONTENT-LENGTH": str(len(flac_bytes())),
            "CONTENT-TYPE": FLAC,
            "X-TALON-UTTERANCE-ID": UID,
            "X-Talon-Phone-Key": KEY,
        }
        assert api.handle("POST", "/snippet", h, io.BytesIO(flac_bytes())).status == 200

    def test_a_query_string_is_ignored(self, tmp_path):
        api, _ = make_api(tmp_path)
        assert post(api, flac_bytes(), path="/snippet?x=1").status == 200

    def test_the_server_time_is_on_the_response(self, tmp_path):
        api, _ = make_api(tmp_path)
        r = post(api, flac_bytes())
        assert float(r.headers["X-Talon-Server-Ms"]) >= 0

    # --- auth ---

    @pytest.mark.parametrize(
        "auth",
        [
            {},
            {keyfile.HEADER: OTHER_KEY},
            {keyfile.HEADER: ""},
            {"Tailscale-User-Login": LOGIN},
        ],
    )
    def test_without_the_key_it_is_403_and_nothing_is_saved(self, tmp_path, auth):
        api, svc = make_api(tmp_path)
        r = post(api, flac_bytes(), auth=auth)
        assert (r.status, r.body["error"]) == (403, "forbidden")
        assert svc._writer.saved == []

    def test_no_key_loaded_denies_everyone(self, tmp_path):
        api, svc = make_api(tmp_path)
        api._get_key = lambda: None
        assert post(api, flac_bytes()).status == 403

    def test_identity_auth_works_the_same_on_loopback(self, tmp_path):
        api, svc = make_api(tmp_path, key=None)
        ok = post(api, flac_bytes(), auth={"Tailscale-User-Login": LOGIN})
        bad = post(
            api,
            flac_bytes(),
            key=uid("u2"),
            auth={"Tailscale-User-Login": "x@example.com"},
        )
        none = post(api, flac_bytes(), key=uid("u3"), auth={})
        assert (ok.status, bad.status, none.status) == (200, 403, 403)
        assert len(svc._writer.saved) == 1

    def test_auth_is_checked_before_the_body_is_read(self, tmp_path):
        api, _ = make_api(tmp_path)

        class Boom:
            def read(self, n):
                raise AssertionError("body read before auth")

        h = {"Content-Length": "10", "Content-Type": FLAC, ledger.ID_HEADER: UID}
        assert api.handle("POST", "/snippet", h, Boom()).status == 403

    # --- the switch, routing ---

    def test_a_listener_without_snippets_has_no_such_path(self, tmp_path):
        api, _ = make_api(tmp_path, snippets=False)
        assert post(api, flac_bytes()).status == 404

    def test_a_disabled_snippet_setting_is_503_even_with_a_good_key(self, tmp_path):
        api, svc = make_api(tmp_path, enabled=False)
        r = post(api, flac_bytes())
        assert (r.status, r.body["error"]) == (503, "snippets_disabled")
        assert svc._writer.saved == []

    def test_a_disabled_snippet_setting_still_refuses_without_auth_first(
        self, tmp_path
    ):
        api, _ = make_api(tmp_path, enabled=False)
        assert post(api, flac_bytes(), auth={}).status == 403

    @pytest.mark.parametrize("method", ["GET", "PUT", "DELETE", "HEAD"])
    def test_only_post_is_allowed(self, tmp_path, method):
        api, _ = make_api(tmp_path)
        r = api.handle(method, "/snippet", dict(KEYHDR), io.BytesIO(b""))
        assert r.status == 405 and r.headers["Allow"] == "POST"

    # --- body caps ---

    def test_the_cap_is_a_documented_one_mebibyte_above_the_emission_cap(
        self, tmp_path
    ):
        assert snippet.MAX_BYTES == 1 << 20
        assert snippet.MAX_BYTES > listener.wire.MAX_PAYLOAD_BYTES

    def test_an_oversize_body_is_413_and_never_read(self, tmp_path):
        api, svc = make_api(tmp_path)

        class Boom:
            def read(self, n):
                raise AssertionError("an oversize body was read")

        h = {
            "Content-Length": str(snippet.MAX_BYTES + 1),
            "Content-Type": FLAC,
            ledger.ID_HEADER: UID,
            **KEYHDR,
        }
        r = api.handle("POST", "/snippet", h, Boom())
        assert (r.status, r.body["error"]) == (413, "body_too_large")

    def test_a_body_at_the_cap_is_read_and_judged_on_its_audio(self, tmp_path):
        api, _ = make_api(tmp_path)
        r = post(api, b"\0" * snippet.MAX_BYTES)
        assert (r.status, r.body["error"]) == (422, "not_flac")

    def test_a_thirty_second_wav_fits_under_the_cap(self):
        assert len(wav_bytes(16000 * 30)) < snippet.MAX_BYTES

    @pytest.mark.parametrize(
        "length,status,code",
        [
            (None, 411, "length_required"),
            ("abc", 400, "bad_content_length"),
            ("-5", 400, "bad_content_length"),
        ],
    )
    def test_bad_length_headers(self, tmp_path, length, status, code):
        api, _ = make_api(tmp_path)
        h = {"Content-Type": FLAC, ledger.ID_HEADER: UID, **KEYHDR}
        if length is not None:
            h["Content-Length"] = length
        r = api.handle("POST", "/snippet", h, io.BytesIO(b"x"))
        assert (r.status, r.body["error"]) == (status, code)

    def test_chunked_uploads_are_refused(self, tmp_path):
        api, _ = make_api(tmp_path)
        r = post(api, flac_bytes(), extra={"Transfer-Encoding": "chunked"})
        assert (r.status, r.body["error"]) == (411, "length_required")

    def test_a_body_shorter_than_its_length_is_400(self, tmp_path):
        api, svc = make_api(tmp_path)
        r = post(api, flac_bytes(), length=len(flac_bytes()) + 50)
        assert (r.status, r.body["error"]) == (400, "truncated_body")
        assert svc._writer.saved == []

    def test_a_missing_id_is_400_through_http(self, tmp_path):
        api, _ = make_api(tmp_path)
        r = post(api, flac_bytes(), key=None)
        assert (r.status, r.body["error"]) == (400, "missing_utterance_id")

    @pytest.mark.parametrize(
        "bad", ["", "abc", "x" * 20, "a" * 65, "12345678-1234", "g1" * 10]
    )
    def test_an_unusable_id_is_400_and_nothing_is_saved(self, tmp_path, bad):
        api, svc = make_api(tmp_path)
        r = post(api, flac_bytes(), key=bad)
        assert (r.status, r.body["error"]) == (400, "bad_utterance_id")
        assert svc._writer.saved == []

    # --- the id table shared with /emission ---

    def test_an_id_is_canonical_however_the_phone_writes_it(self, tmp_path):
        api, svc = make_api(tmp_path)
        body = flac_bytes()
        first = post(api, body, key="A1B2C3D4-E5F6-47A8-9B0C-1D2E3F405162")
        assert first.body["id"] == "a1b2c3d4e5f647a89b0c1d2e3f405162"
        again = post(api, body, key="a1b2c3d4e5f647a89b0c1d2e3f405162")
        assert again.body["duplicate"] is True
        assert len(svc._writer.saved) == 1

    def test_a_retry_is_replayed_from_the_table_and_says_so(self, tmp_path):
        api, svc = make_api(tmp_path)
        body = flac_bytes()
        first = post(api, body)
        again = post(api, body)
        assert again.status == 200 and again.body["duplicate"] is True
        assert again.headers[ledger.REPLAYED_HEADER] == "1"
        assert ledger.REPLAYED_HEADER not in first.headers
        assert again.body["name"] == first.body["name"]
        assert again.body["seq"] == first.body["seq"]  # the first attempt's stamp
        assert len(svc._writer.saved) == 1

    def test_a_replay_with_other_bytes_is_a_conflict_and_saves_nothing(self, tmp_path):
        api, svc = make_api(tmp_path)
        post(api, flac_bytes(16000))
        r = post(api, flac_bytes(24000))
        assert (r.status, r.body["error"]) == (409, "id_conflict")
        assert len(svc._writer.saved) == 1

    def test_a_retry_after_the_table_forgot_is_answered_from_the_durable_ledger(
        self, tmp_path
    ):
        api, svc = make_api(tmp_path)
        body = flac_bytes()
        first = post(api, body)
        api._ledger = ledger.Ledger()  # ten minutes later, or a restart
        again = post(api, body)
        assert again.status == 200 and again.body["duplicate"] is True
        assert again.body["name"] == first.body["name"]
        assert len(svc._writer.saved) == 1

    def test_the_same_id_while_the_first_is_saving_is_409_in_progress(self, tmp_path):
        api, svc = make_api(tmp_path)
        svc._writer.gate = threading.Event()
        body = flac_bytes()
        out = []
        t = threading.Thread(target=lambda: out.append(post(api, body)))
        t.start()
        try:
            for _ in range(200):
                if api._ledger.lookup(UID) is not None:
                    break
                threading.Event().wait(0.01)
            busy = post(api, body)
            assert (busy.status, busy.body["error"]) == (409, "in_progress")
            assert busy.headers["Retry-After"] == "1"
        finally:
            svc._writer.gate.set()
            t.join(5)
        assert out[0].status == 200 and len(svc._writer.saved) == 1

    def test_a_failed_save_frees_the_id_for_the_retry(self, tmp_path):
        api, svc = make_api(tmp_path)
        svc._writer.fail = recordings.SaveError("save_failed")
        assert post(api, flac_bytes()).status == 500
        svc._writer.fail = None
        r = post(api, flac_bytes())
        assert r.status == 200 and r.body["duplicate"] is False
        assert ledger.REPLAYED_HEADER not in r.headers
        assert len(svc._writer.saved) == 1

    def test_a_refused_upload_can_be_fixed_and_resent_under_the_same_id(self, tmp_path):
        api, svc = make_api(tmp_path)
        assert post(api, b"junk").status == 422
        assert post(api, flac_bytes()).status == 200

    # --- GET /result/<id> for snippets ---

    def result(self, api, key=UID):
        return api.handle("GET", f"/result/{key}", dict(KEYHDR), io.BytesIO(b""))

    def test_the_result_of_a_saved_snippet_is_its_ack(self, tmp_path):
        api, _ = make_api(tmp_path)
        ack = post(api, flac_bytes()).body
        r = self.result(api)
        assert (r.status, r.body["state"]) == (200, "done")
        assert r.body["reply"]["name"] == ack["name"]
        assert "stored" not in r.body

    def test_the_result_outlives_the_memory_table(self, tmp_path):
        api, _ = make_api(tmp_path)
        ack = post(api, flac_bytes()).body
        api._ledger = ledger.Ledger()
        r = self.result(api)
        assert (r.status, r.body["state"], r.body["stored"]) == (200, "done", True)
        assert r.body["id"] == UID and r.body["retriable"] is False
        assert r.body["reply"]["name"] == ack["name"]
        assert r.body["reply"]["duplicate"] is False
        assert r.body["instance"] == api._ledger.instance

    def test_the_result_of_an_id_never_seen_is_404(self, tmp_path):
        api, _ = make_api(tmp_path)
        assert self.result(api, uid("never")).status == 404

    def test_a_pending_entry_is_not_a_result(self, tmp_path):
        api, svc = make_api(tmp_path)
        svc._writer.fail = recordings.SaveError("save_failed")
        post(api, flac_bytes())
        api._ledger = ledger.Ledger()
        assert self.result(api).status == 404  # not acked, so not done

    def test_a_result_lookup_is_authenticated(self, tmp_path):
        api, _ = make_api(tmp_path)
        post(api, flac_bytes())
        r = api.handle("GET", f"/result/{UID}", {}, io.BytesIO(b""))
        assert r.status == 403

    def test_a_listener_without_snippets_still_has_result_lookups(self, tmp_path):
        api, _ = make_api(tmp_path, snippets=False)
        assert self.result(api).status == 404

    # --- rate ---

    def test_uploads_are_rate_limited_with_retry_after(self, tmp_path):
        api, svc = make_api(tmp_path, snippet_limiter=RateLimiter(2, 60.0))
        statuses = [post(api, flac_bytes(), key=uid(f"u{i}")) for i in range(4)]
        assert [r.status for r in statuses] == [200, 200, 429, 429]
        assert int(statuses[2].headers["Retry-After"]) >= 1
        assert statuses[2].body["error"] == "rate_limited"
        assert len(svc._writer.saved) == 2

    def test_a_refused_upload_does_not_spend_the_emission_budget_and_vice_versa(
        self, tmp_path
    ):
        emission = RateLimiter(1, 60.0)
        api, _ = make_api(tmp_path, snippet_limiter=RateLimiter(1, 60.0))
        api._limiter = emission
        assert post(api, flac_bytes(), key=uid("a")).status == 200
        assert post(api, flac_bytes(), key=uid("b")).status == 429
        assert emission.check()[0] is True  # snippet traffic never touched it

    def test_a_retry_of_a_saved_upload_still_counts_against_the_rate(self, tmp_path):
        api, svc = make_api(tmp_path, snippet_limiter=RateLimiter(1, 60.0))
        assert post(api, flac_bytes()).status == 200
        assert post(api, flac_bytes()).status == 429
        assert len(svc._writer.saved) == 1

    # --- the metrics a snippet request leaves ---

    def test_requests_land_in_the_metrics_with_status_and_bytes(self, tmp_path):
        api, _ = make_api(tmp_path)
        body = flac_bytes()
        ok = post(api, body)
        post(api, body, auth={})
        summary = api._metrics.summary()["snippet"]["last_n"]
        assert summary["n"] == 2 and summary["by_status"] == {"200": 1, "403": 1}
        assert summary["bytes_in"] == len(body)  # the refused one read no body
        assert summary["bytes_out"] == len(ok.payload()) + len(
            json.dumps({"ok": False, "error": "forbidden"}, separators=(",", ":"))
        )

    def test_a_truncated_body_counts_the_bytes_actually_read(self, tmp_path):
        api, _ = make_api(tmp_path)
        post(api, b"abc", length=500)
        assert api._metrics.summary()["snippet"]["last_n"]["bytes_in"] == 0

    def test_the_client_round_trip_header_is_taken_for_snippets(self, tmp_path):
        api, _ = make_api(tmp_path)
        post(api, flac_bytes(), extra={listener.RTT_HEADER: "123.5"})
        rtt = api._metrics.summary()["snippet"]["client_rtt_ms"]["last_n"]
        assert rtt["n"] == 1 and rtt["p50"] == 123.5

    def test_a_metrics_failure_never_fails_the_upload(self, tmp_path):
        api, _ = make_api(tmp_path)
        api._metrics.record = lambda s: (_ for _ in ()).throw(
            RuntimeError("metrics down")
        )
        assert post(api, flac_bytes()).status == 200


class TestSnippetRealSocket:
    @pytest.fixture
    def server(self, tmp_path):
        folder = tmp_path / "recordings"
        folder.mkdir()
        svc = snippet.SnippetService(
            recordings.RecordingsWriter(lambda: str(folder)),
            snippet_ledger.SnippetLedger(str(tmp_path / "l.jsonl")),
            lambda: True,
            log=lambda *_: None,
        )
        api = listener.ListenerApi(
            types.SimpleNamespace(),
            lambda: "emission",
            lambda: "",
            key=lambda: KEY,
            snippets=svc,
            metrics=metrics.Metrics(),
            limiter=RateLimiter(1000, 1.0),
            snippet_limiter=RateLimiter(1000, 1.0),
            log=lambda *_: None,
        )
        srv, _ = listener.start(api, 0)
        try:
            yield srv, folder
        finally:
            listener.stop(srv)

    def call(self, srv, body, headers, method="POST", path="/snippet"):
        conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        out = (resp.status, json.loads(data), dict(resp.getheaders()))
        conn.close()
        return out

    def test_upload_retry_and_the_file_on_disk(self, server):
        srv, folder = server
        body = flac_bytes()
        h = {"Content-Type": FLAC, ledger.ID_HEADER: uid("real-1"), **KEYHDR}
        status, ack, hdrs = self.call(srv, body, h)
        assert status == 200 and ack["duplicate"] is False
        assert "X-Talon-Server-Ms" in hdrs or "x-talon-server-ms" in {
            k.lower() for k in hdrs
        }
        assert (folder / ack["name"]).read_bytes() == body
        status2, ack2, _ = self.call(srv, body, h)
        assert (
            status2 == 200 and ack2["duplicate"] is True and ack2["name"] == ack["name"]
        )
        assert len(list(folder.iterdir())) == 1

    def test_wrong_key_oversize_and_junk_leave_the_folder_empty_and_the_server_up(
        self, server
    ):
        srv, folder = server
        base = {"Content-Type": FLAC, ledger.ID_HEADER: uid("real-2")}
        assert (
            self.call(srv, flac_bytes(), {**base, keyfile.HEADER: OTHER_KEY})[0] == 403
        )
        assert self.call(srv, flac_bytes(), base)[0] == 403
        # Declare an oversize body and send none of it: the refusal comes from the header alone.
        conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
        conn.putrequest("POST", "/snippet")
        for k, v in {
            **base,
            **KEYHDR,
            "Content-Length": str(snippet.MAX_BYTES + 10),
        }.items():
            conn.putheader(k, v)
        conn.endheaders()
        resp = conn.getresponse()
        assert (resp.status, json.loads(resp.read())["error"]) == (
            413,
            "body_too_large",
        )
        conn.close()
        junk = self.call(srv, b"junk", {**base, **KEYHDR})
        assert (junk[0], junk[1]["error"]) == (422, "not_flac")
        assert list(folder.iterdir()) == []
        assert self.call(srv, flac_bytes(), {**base, **KEYHDR})[0] == 200

    def test_metrics_over_the_wire_carries_no_phrase_or_audio(self, server):
        srv, _ = server
        self.call(
            srv,
            flac_bytes(),
            {"Content-Type": FLAC, ledger.ID_HEADER: uid("m-1"), **KEYHDR},
        )
        status, summary, _ = self.call(
            srv, None, dict(KEYHDR), method="GET", path="/metrics"
        )
        assert status == 200 and summary["snippet"]["last_n"]["n"] == 1
        text = json.dumps(summary)
        assert (
            uid("m-1") not in text and "phone-snippet" not in text and KEY not in text
        )


class TestGlueSnippets:
    def load(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            Module, "setting", lambda self, name, **kw: calls.append((name, kw))
        )
        spec = importlib.util.spec_from_file_location(
            "trillium.phone_receiver._glue_probe_snippets", GLUE_PATH
        )
        glue = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(glue)
        return glue, {n: kw for n, kw in calls}

    def test_the_snippet_setting_is_declared_and_off_by_default(self, monkeypatch):
        _, decl = self.load(monkeypatch)
        assert decl["phone_receiver_snippets_enabled"]["default"] is False
        assert decl["phone_receiver_snippets_enabled"]["type"] is bool

    def test_snippets_need_both_settings(self, monkeypatch):
        glue, _ = self.load(monkeypatch)
        try:
            assert glue._snippets_enabled() is False
            talon.Settings.set("user.phone_receiver_snippets_enabled", True)
            assert glue._snippets_enabled() is False  # the listener itself is still off
            talon.Settings.set("user.phone_receiver_enabled", True)
            assert glue._snippets_enabled() is True
            talon.Settings.set("user.phone_receiver_snippets_enabled", False)
            assert glue._snippets_enabled() is False
        finally:
            talon.Settings.reset()

    def test_the_folder_comes_from_talons_home_not_a_literal(
        self, monkeypatch, tmp_path
    ):
        glue, _ = self.load(monkeypatch)
        talon.actions.reset_test_actions()
        talon.actions.register_test_action("path", "talon_home", lambda: str(tmp_path))
        try:
            assert glue._recordings_dir() == os.path.join(str(tmp_path), "recordings")
        finally:
            talon.actions.reset_test_actions()

    def test_the_wav_encoder_uses_talons_flac_with_its_defaults(self, monkeypatch):
        glue, _ = self.load(monkeypatch)
        seen = {}

        def fake_encode(samples, **kw):
            seen["n"], seen["kw"] = len(samples), kw
            return b"fLaC"

        monkeypatch.setattr(glue, "flac", types.SimpleNamespace(encode=fake_encode))
        assert glue._encode_wav(struct.pack("<hh", 0, 1)) == b"fLaC"
        assert seen == {"n": 2, "kw": {"sample_rate": 16000, "channels": 1}}

    def test_without_talons_flac_library_a_wav_is_refused_not_crashed(
        self, monkeypatch
    ):
        glue, _ = self.load(monkeypatch)
        assert glue.flac is None  # the test stubs have no flac library
        assert glue._snippets._encode is None

    def test_the_listener_is_wired_with_snippets_and_metrics(
        self, monkeypatch, tmp_path
    ):
        glue, _ = self.load(monkeypatch)
        monkeypatch.setattr(glue.listener, "DEFAULT_PORT", 0)
        talon.Settings.set("user.phone_receiver_enabled", True)
        try:
            glue.start_listener()
            srv = glue._holder.server
            conn = http.client.HTTPConnection(
                "127.0.0.1", srv.server_address[1], timeout=5
            )
            conn.request("GET", "/metrics")
            assert conn.getresponse().status == 403  # routed, and key/identity-gated
            conn.close()
            conn = http.client.HTTPConnection(
                "127.0.0.1", srv.server_address[1], timeout=5
            )
            conn.request("POST", "/snippet", body=b"x", headers={"Content-Type": FLAC})
            assert conn.getresponse().status == 403
            conn.close()
            assert glue._holder.metrics_job is not None
        finally:
            talon.Settings.reset()
            if glue._holder.server is not None:
                glue.listener.stop(glue._holder.server)
            glue._holder.server = None
            talon.speech_system.reset()
