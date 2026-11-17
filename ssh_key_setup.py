import hashlib
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from ssh_config import WINDOWS, connection_options, identity_options, restrict_windows_file


SESSION_OPTIONS = [
    "-T",
    "-o", "ClearAllForwardings=yes",
    "-o", "ForwardAgent=no",
    "-o", "ForwardX11=no",
    "-o", "ControlPath=none",
    "-o", "PermitLocalCommand=no",
    "-o", "RemoteCommand=none",
    "-o", "ConnectTimeout=10",
]


def effective_target(alias, options):
    try:
        result = subprocess.run(["ssh", "-G", "-T", *options, "--", alias], stdout=subprocess.PIPE,
                                check=True, timeout=15)
    except subprocess.CalledProcessError as error:
        raise ValueError(f"OpenSSH could not load alias '{alias}'.") from error
    except subprocess.TimeoutExpired as error:
        raise ValueError(f"OpenSSH timed out while loading alias '{alias}'.") from error
    settings = dict(line.split(b" ", 1) for line in result.stdout.splitlines() if b" " in line)
    try:
        return b"\0".join(settings[field] for field in (b"hostname", b"user", b"port"))
    except KeyError as error:
        raise ValueError(f"OpenSSH did not report a complete target for alias '{alias}'.") from error


def local_identity(config, target):
    directory = config.root / "ssh-alias-manager"
    name = "id_ed25519_" + hashlib.sha256(target).hexdigest()[:32]
    identity = directory / name
    config.root.mkdir(mode=0o700, exist_ok=True)
    with config.locked():
        directory.mkdir(mode=0o700, exist_ok=True)
        if directory.resolve() != directory or identity.is_symlink():
            raise ValueError("The managed key path must be inside the SSH directory.")
        if not identity.exists():
            with tempfile.TemporaryDirectory(prefix="key-", dir=directory) as staging:
                staged = Path(staging) / "identity"
                result = subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "",
                                         "-C", "ssh-alias-manager", "-f", str(staged)],
                                        stdin=subprocess.DEVNULL)
                if result.returncode:
                    raise ValueError("OpenSSH could not generate the key.")
                if WINDOWS:
                    restrict_windows_file(staged)
                staged.replace(identity)
        if not identity.is_file():
            raise ValueError("The managed key path must be a regular file.")
    return identity


def install_command(identity):
    result = subprocess.run(["ssh-keygen", "-y", "-P", "", "-f", str(identity)],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE)
    fields = result.stdout.split()[:2]
    if result.returncode or len(fields) != 2 or fields[0] != b"ssh-ed25519" or not re.fullmatch(
        rb"[A-Za-z0-9+/]+={0,2}", fields[1]
    ):
        raise ValueError("OpenSSH could not read the managed public key.")
    public_key = shlex.quote(b" ".join(fields).decode("ascii"))
    return (
        'umask 077; keyfile="$HOME/.ssh/authorized_keys"; '
        'mkdir -p "$HOME/.ssh" && touch "$keyfile" || exit 1; '
        f'grep -Fqx {public_key} "$keyfile"; '
        f'''case $? in 0) exit 0;; 1) printf '\\n%s\\n' {public_key} >> "$keyfile";; *) exit 1;; esac'''
    )


def key_login_works(alias, options, identity=None):
    command = ["ssh", *SESSION_OPTIONS, *options, "-o", "BatchMode=yes", "-o", "PreferredAuthentications=publickey"]
    if identity is not None:
        key_file, identities_only = identity_options(identity)
        command.extend(["-o", key_file.strip(), "-o", identities_only.strip()])
    try:
        result = subprocess.run([*command, "--", alias, "exit"], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                                errors="replace", timeout=20)
    except subprocess.TimeoutExpired as error:
        raise ValueError(f"SSH timed out while verifying key login for '{alias}'.") from error
    detail = result.stderr.strip()
    if result.returncode == 255 and detail and not re.search(
        r"permission denied \(|host key verification failed|too many authentication failures", detail, re.I
    ):
        raise ValueError(f"SSH failed for '{alias}'.\n{detail}")
    return result.returncode == 0


def authorize_key(config, alias, snapshot, options=()):
    if not sys.stdin.isatty():
        raise ValueError("Run key setup in an interactive terminal for the SSH prompts.")
    print(f"Checking SSH access for '{alias}'...", flush=True)
    target = effective_target(alias, options)
    if key_login_works(alias, options):
        return None

    identity = local_identity(config, target)
    if not key_login_works(alias, options, identity):
        if config.setup_snapshot(alias, adding=bool(options)) != snapshot:
            raise ValueError("The SSH config changed during setup. Try again.")
        print(f"Authorizing a key for '{alias}'. Enter the password at the OpenSSH prompt.", flush=True)
        command = [
            "ssh", *SESSION_OPTIONS, *options, "-o", "BatchMode=no", "-o", "PasswordAuthentication=yes",
            "-o", "NumberOfPasswordPrompts=1",
            "-o", "PreferredAuthentications=keyboard-interactive,password",
            "--", alias, install_command(identity),
        ]
        try:
            result = subprocess.run(command, env={**os.environ, "SSH_ASKPASS_REQUIRE": "never"}, timeout=120)
        except subprocess.TimeoutExpired as error:
            raise ValueError(f"SSH key authorization timed out for '{alias}'.") from error
        if result.returncode:
            raise ValueError(f"SSH could not authorize the key for '{alias}'.")
        if not key_login_works(alias, options, identity):
            raise ValueError(f"The server did not accept the key for '{alias}'. Check its public key settings.")

    return identity


def setup_key(config, alias):
    snapshot = config.setup_snapshot(alias)
    identity = authorize_key(config, alias, snapshot)
    if identity is not None:
        config.attach_identity(alias, identity, snapshot)


def setup_new_alias(config, alias, host, user, port):
    options = [argument for option in connection_options(host, user, port) for argument in ("-o", option)]
    snapshot = config.setup_snapshot(alias, adding=True)
    identity = authorize_key(config, alias, snapshot, options)
    config.add(alias, host, user, port, identity, snapshot=snapshot)
