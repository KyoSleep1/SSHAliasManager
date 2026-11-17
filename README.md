# SSH Alias Manager

Create, list, rename, remove, and import OpenSSH aliases on macOS, Linux, and Windows. Connect with `ssh ALIAS` after saving an alias in your user SSH config.

Requires Python 3.9+ and the OpenSSH client. Run `./ssh-aliases.sh` for the terminal menu on macOS or Linux. On Windows, use `.\ssh-aliases.bat` in place of `./ssh-aliases.sh` in the commands below. The batch file uses the Windows Python launcher (`py`).

## Agent setup

1. Run `./ssh-aliases.sh list` to see existing aliases.
2. Ask for an alias, hostname or IP address, SSH username, port (default `22`), and optional local private key path. Let OpenSSH handle passwords and key passphrases in the user's terminal.
3. Run `./ssh-aliases.sh add ALIAS --host HOST --user USERNAME` with the supplied values. Add `--port PORT` when supplied. Use `--identity-file PATH` for an existing key or `--setup-key` in the user's terminal to set up key login during Add. Pass user values as individual arguments.
4. Confirm the alias was saved and give the user `ssh ALIAS`.

## Key login

The **Add** menu starts key setup after you enter the connection details. Enter the password at the one-time OpenSSH prompt when asked. The tool creates a local Ed25519 key without a passphrase, installs the public key, and saves the new alias only after key login succeeds. Press **Ctrl+C** to cancel setup. To set up an existing alias, run `./ssh-aliases.sh setup-key ALIAS` in a terminal.

Automatic installation works from Windows, macOS, and Linux clients with servers that use a POSIX shell and the standard `~/.ssh/authorized_keys` file. For Windows servers, follow [Microsoft's key setup guide](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh-keymanagement) and add the alias using the local private key path.

## Manage existing aliases

For an existing OpenSSH config, ask for its path and run `./ssh-aliases.sh import PATH`. The terminal menu also has **Import**. Import copies standalone named `Host` entries with their per-host options and skips existing aliases. Import included files individually.

Use `./ssh-aliases.sh rename OLD NEW` or `./ssh-aliases.sh remove ALIAS` for updates. The list shows literal `Host` entries from the user config and matching include paths. Entries outside `~/.ssh` or defined across multiple files appear as read-only.
