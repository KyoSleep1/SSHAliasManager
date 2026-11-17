import argparse
import os
import sys
from pathlib import Path

from ssh_config import WINDOWS, SSHConfig
from ssh_key_setup import setup_key, setup_new_alias


APP_NAME = "SSH Alias Manager"


def list_aliases(config):
    entries = config.list_aliases()
    if not entries:
        print("No SSH aliases found.")
        return
    for alias, path, editable in entries:
        status = "" if editable else " (read-only)"
        print(f"{alias}\t{path}{status}")


def add_alias(config, alias, host, user, port, identity, configure_key=False):
    if configure_key:
        setup_new_alias(config, alias, host, user, port)
        print(f"Saved '{alias}'. Key login works. Connect with ssh {alias}.")
    else:
        config.add(alias, host, user, port, identity)
        print(f"Saved '{alias}'. Connect with ssh {alias}.")


def setup_alias_key(config, alias):
    setup_key(config, alias)
    print(f"Key login works. Connect with ssh {alias}.")


def rename_alias(config, alias, new_alias):
    config.change(alias, new_alias)
    print(f"Alias '{alias}' is now '{new_alias}'.")


def remove_alias(config, alias):
    config.change(alias)
    print(f"Removed '{alias}'.")


def import_aliases(config, path):
    added, skipped = config.import_file(Path(path))
    if added:
        print("Imported " + ", ".join(added) + ".")
    if skipped:
        print("Skipped existing aliases " + ", ".join(skipped) + ".")


def clear_screen():
    if sys.stdout.isatty():
        if WINDOWS:
            os.system("cls")
        else:
            print("\033[2J\033[H", end="", flush=True)


def menu(config):
    clear_screen()
    while True:
        print(f"\n{APP_NAME}\n1. List\n2. Add\n3. Rename\n4. Remove\n5. Import\n0. Quit")
        action = input("Choose an option: ").strip()
        if action == "0":
            return
        clear_screen()
        try:
            if action == "1":
                list_aliases(config)
            elif action == "2":
                alias = input("Alias: ").strip()
                host = input("Hostname or IP address: ").strip()
                user = input("SSH username: ").strip()
                port = input("Port [22]: ").strip() or 22
                add_alias(config, alias, host, user, port, identity=None, configure_key=True)
            elif action == "3":
                list_aliases(config)
                alias = input("Current alias: ").strip()
                new_alias = input("New alias: ").strip()
                rename_alias(config, alias, new_alias)
            elif action == "4":
                list_aliases(config)
                alias = input("Alias to remove: ").strip()
                if input(f"Remove '{alias}'? [y/N]: ").strip().lower() == "y":
                    remove_alias(config, alias)
            elif action == "5":
                path = input("OpenSSH config file path: ").strip()
                if path:
                    import_aliases(config, path)
            else:
                print("Choose a listed option.")
        except KeyboardInterrupt:
            print("\nOperation canceled.")
        except (OSError, ValueError) as error:
            print(f"Error: {error}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=f"{APP_NAME} manages OpenSSH aliases.")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("list", help="List SSH aliases")

    add = commands.add_parser("add", help="Add an SSH alias")
    add.add_argument("alias")
    add.add_argument("--host", required=True, help="Hostname or IP address")
    add.add_argument("--user", required=True, help="SSH username")
    add.add_argument("--port", default=22, help="SSH port (default: 22)")
    authentication = add.add_mutually_exclusive_group()
    authentication.add_argument("--identity-file", help="Path to a local private key")
    authentication.add_argument("--setup-key", action="store_true", help="Set up key login interactively")

    key_setup = commands.add_parser("setup-key", help="Set up key login for an existing alias")
    key_setup.add_argument("alias")

    rename = commands.add_parser("rename", help="Rename an SSH alias")
    rename.add_argument("alias")
    rename.add_argument("new_alias")

    remove = commands.add_parser("remove", help="Remove an SSH alias")
    remove.add_argument("alias")

    import_command = commands.add_parser("import", help="Import named aliases from an OpenSSH config")
    import_command.add_argument("path", help="Path to the OpenSSH config file")

    args = parser.parse_args()
    config = SSHConfig(Path.home() / ".ssh")
    try:
        if args.command == "list":
            list_aliases(config)
        elif args.command == "add":
            add_alias(config, args.alias, args.host, args.user, args.port, args.identity_file, args.setup_key)
        elif args.command == "setup-key":
            setup_alias_key(config, args.alias)
        elif args.command == "rename":
            rename_alias(config, args.alias, args.new_alias)
        elif args.command == "remove":
            remove_alias(config, args.alias)
        elif args.command == "import":
            import_aliases(config, args.path)
        elif sys.stdin.isatty():
            menu(config)
        else:
            parser.print_help()
    except (EOFError, KeyboardInterrupt):
        print()
        return 130
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
