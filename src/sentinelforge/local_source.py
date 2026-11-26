"""Bounded reads of explicitly selected Python sources and evaluation JSON.

These checks are defensive intake validation, not an OS filesystem sandbox.
Windows cannot apply openat/O_NOFOLLOW to every ancestor through this API;
the caller must retain control of the authorized root during a scan.
"""

import errno
import os
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath

MAX_SOURCE_BYTES = 65_536
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in "123456789¹²³"
}


class LocalSourceError(ValueError):
    """Stable intake error without OS diagnostics or absolute path disclosure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _relative_parts(relative_path: str, suffix: str = ".py") -> tuple[str, ...]:
    if not isinstance(relative_path, str) or not relative_path or len(relative_path) > 1024:
        raise LocalSourceError("source_path_invalid")
    normalized = relative_path.replace("\\", "/")
    if (
        PurePosixPath(normalized).is_absolute()
        or PureWindowsPath(relative_path).drive
        or any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in normalized)
        or any(character in normalized for character in '<>:"|?*')
    ):
        raise LocalSourceError("source_path_invalid")
    parts = tuple(normalized.split("/"))
    if any(
        not part
        or part.startswith(".")
        or part.endswith((".", " "))
        or part.split(".", 1)[0].rstrip(" ").upper() in _RESERVED_NAMES
        for part in parts
    ):
        raise LocalSourceError("source_path_invalid")
    if PurePosixPath(parts[-1]).suffix.lower() != suffix:
        raise LocalSourceError("unsupported_file_type")
    return parts


def _is_link(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT
    )


def _signature(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_size,
        # Windows path/descriptor APIs disagree on legacy ctime semantics.
        metadata.st_mtime_ns, metadata.st_ctime_ns if os.name != "nt" else 0,
        getattr(metadata, "st_file_attributes", 0),
    )


def _checked_root(root: Path) -> tuple[Path, dict[Path, tuple[int, ...]]]:
    try:
        absolute = Path(os.path.abspath(root))
        # UNC/device roots may open a remote share; this adapter is local-only.
        if PureWindowsPath(str(absolute)).drive.startswith("\\\\"):
            raise LocalSourceError("root_invalid")
        snapshots = {}
        for directory in (*reversed(absolute.parents), absolute):
            metadata = directory.lstat()
            if _is_link(metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise LocalSourceError("root_invalid")
            # Directory size/time changes do not change path identity.
            snapshots[directory] = (metadata.st_dev, metadata.st_ino)
        return absolute, snapshots
    except (OSError, ValueError, TypeError) as error:
        raise LocalSourceError("root_invalid") from error


def normalize_source_label(relative_path: str) -> str:
    """Validate an artifact label without opening any host path."""
    return "/".join(_relative_parts(relative_path))


def _load_local_data(root: Path, relative_path: str, *, suffix: str,
                     max_bytes: int) -> tuple[str, bytes]:
    """Use trusted adapter limits; apply identical path/open guards to selected data."""
    parts = _relative_parts(relative_path, suffix)
    authorized_root, directories = _checked_root(root)
    candidate = authorized_root
    try:
        for index, part in enumerate(parts):
            candidate = candidate / part
            metadata = candidate.lstat()
            if _is_link(metadata):
                raise LocalSourceError("source_unsafe_path")
            if index < len(parts) - 1:
                if not stat.S_ISDIR(metadata.st_mode):
                    raise LocalSourceError("source_not_regular")
                directories[candidate] = (metadata.st_dev, metadata.st_ino)
            elif not stat.S_ISREG(metadata.st_mode):
                raise LocalSourceError("source_not_regular")
        if not candidate.resolve(strict=True).is_relative_to(authorized_root):
            raise LocalSourceError("source_unsafe_path")
    except FileNotFoundError as error:
        raise LocalSourceError("source_not_found") from error
    except OSError as error:
        raise LocalSourceError("source_read_failed") from error

    before = _signature(metadata)
    if metadata.st_size > max_bytes:
        raise LocalSourceError("source_too_large")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError as error:
        code = "source_unsafe_path" if error.errno == errno.ELOOP else "source_read_failed"
        raise LocalSourceError(code) from error
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _signature(opened) != before:
            raise LocalSourceError("source_changed")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > max_bytes:
            raise LocalSourceError("source_too_large")
        if _signature(os.fstat(descriptor)) != before:
            raise LocalSourceError("source_changed")
        if _signature(candidate.lstat()) != before:
            raise LocalSourceError("source_changed")
        for directory, identity in directories.items():
            current = directory.lstat()
            if (
                _is_link(current)
                or not stat.S_ISDIR(current.st_mode)
                or (current.st_dev, current.st_ino) != identity
            ):
                raise LocalSourceError("source_changed")
    except OSError as error:
        raise LocalSourceError("source_read_failed") from error
    finally:
        os.close(descriptor)
    return "/".join(parts), data


def load_local_source(root: Path, relative_path: str) -> tuple[str, bytes]:
    """Return one .py of up to 64 KiB without importing its code."""
    return _load_local_data(root, relative_path, suffix=".py", max_bytes=MAX_SOURCE_BYTES)
