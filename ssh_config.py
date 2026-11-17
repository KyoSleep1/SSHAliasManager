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


def identity_options(identity):
    path = Path(identity).expanduser().absolute().as_posix()
    if any(ord(char) < 32 or ord(char) == 127 for char in path) or "${" in path:
        raise ValueError("Enter a local key path without control characters or variable references.")
    quoted = path.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return [f'    IdentityFile "{quoted}"', "    IdentitiesOnly yes"]


def connection_options(host, user, port):
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
    return [f"HostName {hostname}", f"User {user}", f"Port {int(port)}"]


def host_entry(alias, host, user, port, identity):
    require_alias(alias)
    lines = [f"Host {alias}"]
    lines.extend(f"    {option}" for option in connection_options(host, user, port))
    if identity:
        lines.extend(identity_options(identity))
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

    def section_ranges(self):
        boundaries = [*self.sections, len(self.lines)]
        return zip(boundaries, boundaries[1:])

    def import_sections(self):
        for start, end in self.section_ranges():
            group = self.sections[start]
            excluded = [
                re.compile(re.escape(arg.value[1:]).replace(r"\*", ".*").replace(r"\?", "."))
                for arg in group
                if arg.value.startswith("!")
            ]
            aliases = dict.fromkeys(
                arg.value
                for arg in group
                if ALIAS.fullmatch(arg.value) and not any(pattern.fullmatch(arg.value) for pattern in excluded)
            )
            if aliases:
                yield start, end, aliases

    def import_block(self, start, end, aliases):
        lines = ["Host " + " ".join(aliases)]
        for index in range(start + 1, end):
            line = self.lines[index].rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            directive = DIRECTIVE.match(line)
            if directive is None or directive[1].lower() == "include":
                raise ValueError(f"{self.path}:{index + 1} is not a standalone host option.")
            lines.append(line)
        return "\n".join(lines) + "\n\n"

    def prepend(self, content):
        if self.first_directive not in (None, "host", "match"):
            content += "Host *\n\n"
        if "\r\n" in self.original or (WINDOWS and not self.original):
            content = content.replace("\n", "\r\n")
        self.save(content + self.original)

    def replace_alias(self, alias, replacement):
        for start, end in reversed(list(self.section_ranges())):
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


def config_contents(files):
    return {path: document.original for path, document in files.items()}


def require_unchanged(files, snapshot):
    if snapshot is not None and config_contents(files) != snapshot:
        raise ValueError("The SSH config changed during setup. Try again.")


def validate_import(content, aliases):
    with tempfile.TemporaryDirectory(prefix="ssh-alias-import-") as directory:
        path = Path(directory) / "config"
        path.write_bytes(content.encode("utf-8", errors="surrogateescape"))
        for alias in aliases:
            try:
                subprocess.run(
                    ["ssh", "-T", "-G", "-F", str(path), "-o", "CanonicalizeHostname=no", "--", alias],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    errors="replace",
                    check=True,
                    timeout=10,
                )
            except subprocess.CalledProcessError as error:
                raise ValueError(f"OpenSSH rejected alias '{alias}'.\n{error.stderr.strip()}") from error
            except subprocess.TimeoutExpired as error:
                raise ValueError(f"OpenSSH timed out while checking alias '{alias}'.") from error


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

    def add_destination(self, alias, files):
        document = files[self.path.resolve()]
        if not self.editable(document.path):
            raise ValueError("The main SSH config is read-only in this tool.")
        if any(alias in file.aliases() for file in files.values()):
            raise ValueError(f"Alias '{alias}' already exists.")
        return document

    def add(self, alias, host, user, port=22, identity=None, *, snapshot=None):
        content = host_entry(alias, host, user, port, identity)
        self.root.mkdir(mode=0o700, exist_ok=True)
        with self.locked():
            files = self.files()
            require_unchanged(files, snapshot)
            document = self.add_destination(alias, files)
            document.prepend(content)

    def import_file(self, path):
        path = path.expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError("Choose a regular OpenSSH config file.")
        content = path.read_bytes().decode("utf-8-sig", errors="surrogateescape")
        content = content.replace("\r\n", "\n")
        if any(ord(char) < 32 and char not in "\n\t" for char in content):
            raise ValueError("Choose a text OpenSSH config file.")
        source = ConfigFile(path, content)
        sections = list(source.import_sections())
        incoming = {alias for _, _, aliases in sections for alias in aliases}
        if not incoming:
            raise ValueError("No named SSH aliases were found in the source file.")

        self.root.mkdir(mode=0o700, exist_ok=True)
        with self.locked():
            files = self.files()
            existing = {alias for file in files.values() for alias in file.aliases()}
            added = sorted(incoming - existing)
            skipped = sorted(incoming & existing)
            if added:
                destination = files[self.path.resolve()]
                if not self.editable(destination.path):
                    raise ValueError("The main SSH config is read-only in this tool.")
                blocks = []
                for start, end, aliases in sections:
                    new_aliases = [alias for alias in aliases if alias not in existing]
                    if new_aliases:
                        blocks.append(source.import_block(start, end, new_aliases))
                content = "".join(blocks)
                validate_import(content, added)
                destination.prepend(content)
            return added, skipped

    def editable_alias(self, alias, files):
        require_alias(alias)
        matches = [file for file in files.values() if alias in file.aliases()]
        if not matches:
            raise ValueError(f"Alias '{alias}' was not found.")
        if len(matches) != 1:
            raise ValueError(f"Alias '{alias}' is defined in multiple files.")
        document = matches[0]
        if not self.editable(document.path):
            raise ValueError(f"Alias '{alias}' is read-only in this tool.")
        return document

    def setup_snapshot(self, alias, *, adding=False):
        require_alias(alias)
        files = self.files()
        if adding:
            self.add_destination(alias, files)
        else:
            self.editable_alias(alias, files)
        return config_contents(files)

    def attach_identity(self, alias, identity, snapshot):
        with self.locked():
            files = self.files()
            require_unchanged(files, snapshot)
            document = self.editable_alias(alias, files)
            document.prepend("\n".join([f"Host {alias}", *identity_options(identity)]) + "\n\n")

    def change(self, alias, replacement=None):
        if replacement is not None:
            require_alias(replacement)
        if not self.root.exists():
            require_alias(alias)
            raise ValueError(f"Alias '{alias}' was not found.")
        with self.locked():
            files = self.files()
            document = self.editable_alias(alias, files)
            if replacement == alias:
                return
            if replacement is not None and any(replacement in file.aliases() for file in files.values()):
                raise ValueError(f"Alias '{replacement}' already exists.")
            document.replace_alias(alias, replacement)
            document.save("".join(document.lines))
