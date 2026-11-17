# SSH aliases

Create, list, rename, and remove OpenSSH aliases on macOS, Linux, and Windows. Connect with `ssh ALIAS` after saving an alias in your user SSH config.

Requires Python 3.9+ and the OpenSSH client. Run `python3 ssh_aliases.py` for the terminal menu. On Windows, use `py -3 ssh_aliases.py` and replace `python3` with `py -3` in the commands below.

## Agent setup

1. Run `python3 ssh_aliases.py list` to see existing aliases.
2. Ask for an alias, hostname or IP address, SSH username, port (default `22`), and optional local private key path. Let SSH prompt for passwords or key passphrases locally.
3. Run `python3 ssh_aliases.py add ALIAS --host HOST --user USERNAME` with the supplied values. Add `--port PORT` and `--identity-file PATH` when supplied. Pass user values as individual arguments.
4. Confirm the alias was saved and give the user `ssh ALIAS`.

Use `python3 ssh_aliases.py rename OLD NEW` or `python3 ssh_aliases.py remove ALIAS` for updates. The list shows literal `Host` entries from the user config and matching include paths. Entries outside `~/.ssh` or defined across multiple files appear as read-only.
