import glob
import ipaddress
import os
import re
import subprocess
import tempfile
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


WINDOWS = os.name == "nt"
if WINDOWS:
    import msvcrt
else:
    import fcntl


ALIAS = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
USER = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.@-]*(?:\\[A-Za-z0-9_][A-Za-z0-9_.@-]*)?")
DIRECTIVE = re.compile(r"^[ \t]*([A-Za-z][A-Za-z0-9]*)(?=[ \t=]|$)[ \t]*=?[ \t]*")


@dataclass(frozen=True)
class Argument:
    value: str
    start: int
    end: int


def arguments(line, start):
    index = start
    while index < len(line):
        if line[index] in " \t":
            index += 1
            continue
        if line[index] == "#":
            break
        start = index
        value = []
        quote = None
        while index < len(line):
            char = line[index]
            following = line[index + 1:index + 2]
            if quote is None and char in " \t":
                break
            escaped = following in ('"', "'", "\\") or (quote is None and following == " ")
            if char == "\\" and escaped:
                index += 1
                value.append(following)
            elif char == quote:
                quote = None
            elif quote is None and char in "\"'":
                quote = char
            else:
                value.append(char)
            index += 1
        if quote is not None:
            raise ValueError("Unterminated quote")
        yield Argument("".join(value), start, index)


def require_alias(alias):
    if not ALIAS.fullmatch(alias):
        raise ValueError("Use letters, numbers, underscores, dots, or hyphens for the alias. "
                         "Start with a letter, number, or underscore.")


def host_entry(alias, host, user, port, identity):
    require_alias(alias)
    if ":" in host:
        try:
            address = ipaddress.IPv6Address(host)
        except ValueError:
            raise ValueError("Enter a hostname or IP address.") from None
        if address.scope_id and not ALIAS.fullmatch(address.scope_id):
            raise ValueError("Enter a valid IPv6 scope.")
    elif not ALIAS.fullmatch(host):
        raise ValueError("Enter a hostname or IP address.")
    if not USER.fullmatch(user):
        raise ValueError("Enter a valid SSH username.")
    if not re.fullmatch(r"[0-9]{1,5}", str(port)) or not 1 <= int(port) <= 65535:
        raise ValueError("Enter a port from 1 to 65535.")

    hostname = host.replace("%", "%%")
    lines = [f"Host {alias}", f"    HostName {hostname}", f"    User {user}", f"    Port {int(port)}"]
    if identity:
        path = Path(identity).expanduser().absolute().as_posix()
        if any(ord(char) < 32 or ord(char) == 127 for char in path) or "${" in path:
            raise ValueError("Enter a local key path without control characters or variable references.")
        quoted = path.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
        lines.extend([f'    IdentityFile "{quoted}"', "    IdentitiesOnly yes"])
    return "\n".join(lines) + "\n\n"


@dataclass
class ConfigFile:
    path: Path
    original: str

    def __post_init__(self):
        lines = self.original.split("\n")
        self.lines = [line + "\n" for line in lines[:-1]]
        if lines[-1]:
            self.lines.append(lines[-1])
        self.sections = {}
        self.includes = []
        self.first_directive = None
        for index, line in enumerate(self.lines):
            line = line.rstrip("\r\n")
            match = DIRECTIVE.match(line)
            if match is None:
                continue
            keyword = match[1].lower()
            if self.first_directive is None:
                self.first_directive = keyword
            try:
                if keyword in ("host", "match"):
                    self.sections[index] = list(arguments(line, match.end())) if keyword == "host" else []
                elif keyword == "include":
                    self.includes.extend(arg.value for arg in arguments(line, match.end()))
            except ValueError as error:
                raise ValueError(f"{self.path}:{index + 1}: {error}") from error

    def aliases(self):
        return {
            arg.value
            for group in self.sections.values()
            for arg in group
            if ALIAS.fullmatch(arg.value)
        }

    def replace_alias(self, alias, replacement):
        ends = [*self.sections.keys(), len(self.lines)]
        for start, end in reversed(list(zip(ends, ends[1:]))):
            group = self.sections[start]
            matches = [arg for arg in group if arg.value == alias]
            if not matches:
                continue
            other_positive = any(arg.value != alias and not arg.value.startswith("!") for arg in group)
            if replacement is None and not other_positive:
                tail = end
                while tail > start + 1:
                    line = self.lines[tail - 1].lstrip()
                    if line and not line.startswith("#"):
                        break
                    tail -= 1
                if any(line.lstrip().startswith("#") for line in self.lines[tail:end]):
                    end = tail
                del self.lines[start:end]
                continue

            header = self.lines[start]
            for arg in reversed(matches):
                header = header[:arg.start] + (replacement or "") + header[arg.end:]
            self.lines[start] = header

    def save(self, content):
        with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix=".ssh-aliases-", delete=False) as staged:
            pending = Path(staged.name)
        try:
            if WINDOWS:
                restrict_windows_file(pending)
            with pending.open("wb") as temp:
                temp.write(content.encode("utf-8", errors="surrogateescape"))
                temp.flush()
                os.fsync(temp.fileno())
            if read_config(self.path) != self.original:
                raise ValueError(f"{self.path} changed. Try again.")
            pending.replace(self.path)
        finally:
            pending.unlink(missing_ok=True)


def restrict_windows_file(path):
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        raise OSError("Could not locate the Windows system directory.")
    system = Path(system_root) / "System32"
    try:
        result = subprocess.run([system / "whoami.exe", "/user", "/fo", "csv", "/nh"],
                                capture_output=True, check=True, timeout=10)
        sid = result.stdout.strip().rsplit(b",", 1)[-1].strip(b' "')
        if not re.fullmatch(rb"S-[0-9]+(?:-[0-9]+)+", sid):
            raise OSError("Could not identify the current Windows user.")
        subprocess.run([system / "icacls.exe", path, "/inheritance:r", "/grant:r", f"*{sid.decode('ascii')}:F"],
                       capture_output=True, check=True, timeout=10)
    except subprocess.SubprocessError as error:
        raise OSError("Could not restrict the Windows SSH config permissions.") from error


def read_config(path):
    try:
        return path.read_bytes().decode("utf-8", errors="surrogateescape")
    except FileNotFoundError:
        return ""


class SSHConfig:
    def __init__(self, root):
        self.root = root.expanduser().resolve()
        self.path = self.root / "config"

    def files(self):
        main = self.path.resolve()
        if main.exists() and not main.is_file():
            raise ValueError(f"{self.path} must be a regular file.")
        files = {main: ConfigFile(main, read_config(main))}
        pending = [files[main]]
        while pending:
            for pattern in pending.pop().includes:
                path = Path(pattern).expanduser()
                if not path.is_absolute():
                    path = self.root / path
                for name in sorted(glob.glob(str(path))):
                    target = Path(name).resolve()
                    if target not in files and target.is_file():
                        document = ConfigFile(target, read_config(target))
                        files[target] = document
                        pending.append(document)
        return files

    def editable(self, path):
        return path.is_relative_to(self.root) and (
            WINDOWS or not path.exists() or path.stat().st_uid == os.geteuid()
        )

    def list_aliases(self):
        entries = [(alias, file.path) for file in self.files().values() for alias in file.aliases()]
        counts = Counter(alias for alias, _ in entries)
        return sorted(
            (alias, path, counts[alias] == 1 and self.editable(path))
            for alias, path in entries
        )

    @contextmanager
    def locked(self):
        if WINDOWS:
            with (self.root / ".ssh-aliases.lock").open("a+b") as lock:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            return

        directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(directory, fcntl.LOCK_EX)
            yield
        finally:
            os.close(directory)

    def add(self, alias, host, user, port=22, identity=None):
        content = host_entry(alias, host, user, port, identity)
        self.root.mkdir(mode=0o700, exist_ok=True)
        with self.locked():
            files = self.files()
            document = files[self.path.resolve()]
            if not self.editable(document.path):
                raise ValueError("The main SSH config is read-only in this tool.")
            if any(alias in file.aliases() for file in files.values()):
                raise ValueError(f"Alias '{alias}' already exists.")
            if document.first_directive not in (None, "host", "match"):
                content += "Host *\n\n"
            if "\r\n" in document.original or (WINDOWS and not document.original):
                content = content.replace("\n", "\r\n")
            document.save(content + document.original)

    def change(self, alias, replacement=None):
        require_alias(alias)
        if replacement is not None:
            require_alias(replacement)
        if not self.root.exists():
            raise ValueError(f"Alias '{alias}' was not found.")
        with self.locked():
            files = self.files()
            matches = [file for file in files.values() if alias in file.aliases()]
            if not matches:
                raise ValueError(f"Alias '{alias}' was not found.")
            if len(matches) != 1:
                raise ValueError(f"Alias '{alias}' is defined in multiple files.")
            document = matches[0]
            if not self.editable(document.path):
                raise ValueError(f"Alias '{alias}' is read-only in this tool.")
            if replacement == alias:
                return
            if replacement is not None and any(replacement in file.aliases() for file in files.values()):
                raise ValueError(f"Alias '{replacement}' already exists.")
            document.replace_alias(alias, replacement)
            document.save("".join(document.lines))
