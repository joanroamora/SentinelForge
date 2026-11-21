"""Local intake is bounded, path-contained, and never executes its bytes."""

import os
from types import SimpleNamespace

import pytest

from sentinelforge import local_source
from sentinelforge.local_source import MAX_SOURCE_BYTES, LocalSourceError, load_local_source


def test_reads_one_explicit_file_without_executing_or_decoding_it(tmp_path) -> None:
    directory = tmp_path / "source"
    directory.mkdir()
    data = b"raise RuntimeError('never execute this file')\n\xff"
    (directory / "example.py").write_bytes(data)
    assert load_local_source(tmp_path, "source\\example.py") == ("source/example.py", data)


@pytest.mark.parametrize(
    "path",
    [
        "", "../outside.py", "nested/../outside.py", "./example.py", "/outside.py",
        "C:\\outside.py", "C:outside.py", "\\\\server\\share\\outside.py",
        "file.py:stream", "file\x00.py", "line\n.py", "nested//file.py",
        ".git/file.py", ".venv/file.py", "nested/.hidden.py", "NUL.py", "COM1.py",
        "nested/LPT².py", "NUL .py", "file.py ", "directory./file.py", "wild*.py", "wild?.py",
    ],
)
def test_rejects_ambiguous_special_hidden_and_traversing_paths(tmp_path, path) -> None:
    with pytest.raises(LocalSourceError, match="^source_path_invalid$") as captured:
        load_local_source(tmp_path, path)
    assert captured.value.code == "source_path_invalid"
    assert str(tmp_path) not in str(captured.value)


def test_requires_supported_file_type_and_existing_regular_file(tmp_path) -> None:
    for path, code in (("file.zip", "unsupported_file_type"), ("absent.py", "source_not_found")):
        with pytest.raises(LocalSourceError, match=f"^{code}$"):
            load_local_source(tmp_path, path)
    (tmp_path / "directory.py").mkdir()
    with pytest.raises(LocalSourceError, match="^source_not_regular$"):
        load_local_source(tmp_path, "directory.py")


def test_accepts_size_limit_and_rejects_larger_files(tmp_path) -> None:
    path = tmp_path / "bounded.py"
    path.write_bytes(b"#" * MAX_SOURCE_BYTES)
    assert len(load_local_source(tmp_path, "bounded.py")[1]) == MAX_SOURCE_BYTES
    path.write_bytes(b"#" * (MAX_SOURCE_BYTES + 1))
    with pytest.raises(LocalSourceError, match="^source_too_large$"):
        load_local_source(tmp_path, "bounded.py")


def test_rejects_missing_or_file_roots(tmp_path) -> None:
    file_root = tmp_path / "file.py"
    file_root.write_bytes(b"pass")
    for root in (tmp_path / "missing", file_root):
        with pytest.raises(LocalSourceError, match="^root_invalid$"):
            load_local_source(root, "file.py")


@pytest.mark.parametrize("reparse_target", ["root", "directory", "file"])
def test_rejects_reparse_points_without_opening_them(tmp_path, monkeypatch, reparse_target) -> None:
    directory = tmp_path / "source"
    directory.mkdir()
    source = directory / "example.py"
    source.write_bytes(b"pass")
    target = {"root": tmp_path, "directory": directory, "file": source}[reparse_target]
    original_lstat = local_source.Path.lstat

    def reparse_lstat(path, *args, **kwargs):
        original = original_lstat(path, *args, **kwargs)
        if path != target:
            return original
        fields = {name: getattr(original, name) for name in dir(original) if name.startswith("st_")}
        fields["st_file_attributes"] = getattr(original, "st_file_attributes", 0) | 0x400
        return SimpleNamespace(**fields)

    def never_open(*args, **kwargs):
        pytest.fail("A reparse point must not be opened")

    monkeypatch.setattr(local_source.Path, "lstat", reparse_lstat)
    monkeypatch.setattr(local_source.os, "open", never_open)
    code = "root_invalid" if reparse_target == "root" else "source_unsafe_path"
    with pytest.raises(LocalSourceError, match=f"^{code}$"):
        load_local_source(tmp_path, "source/example.py")


def test_rejects_symbolic_files_and_parent_directories(tmp_path) -> None:
    target = tmp_path / "target.py"
    target.write_bytes(b"pass")
    linked = tmp_path / "linked.py"
    linked_directory = tmp_path / "linked-directory"
    try:
        linked.symlink_to(target)
        linked_directory.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symbolic links requires an unavailable OS permission")
    for path in ("linked.py", "linked-directory/target.py"):
        with pytest.raises(LocalSourceError, match="^source_unsafe_path$"):
            load_local_source(tmp_path, path)
    with pytest.raises(LocalSourceError, match="^root_invalid$"):
        load_local_source(linked_directory, "target.py")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="OS has no FIFO API")
def test_rejects_fifo_before_opening(tmp_path) -> None:
    os.mkfifo(tmp_path / "pipe.py")
    with pytest.raises(LocalSourceError, match="^source_not_regular$"):
        load_local_source(tmp_path, "pipe.py")


def test_rejects_file_changed_during_read(tmp_path, monkeypatch) -> None:
    path = tmp_path / "changing.py"
    path.write_bytes(b"pass\n")
    original_read = local_source.os.read

    def changing_read(descriptor, count):
        data = original_read(descriptor, count)
        if data:
            path.write_bytes(b"replacement\n")
        return data

    monkeypatch.setattr(local_source.os, "read", changing_read)
    with pytest.raises(LocalSourceError, match="^source_changed$"):
        load_local_source(tmp_path, "changing.py")


def test_hides_os_error_details(tmp_path, monkeypatch) -> None:
    (tmp_path / "unreadable.py").write_bytes(b"pass")

    def fail_open(*args, **kwargs):
        raise PermissionError("sensitive absolute OS error details")

    monkeypatch.setattr(local_source.os, "open", fail_open)
    with pytest.raises(LocalSourceError, match="^source_read_failed$") as captured:
        load_local_source(tmp_path, "unreadable.py")
    assert captured.value.code == "source_read_failed"
