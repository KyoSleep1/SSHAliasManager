import argparse
import sys
from pathlib import Path

from ssh_config import SSHConfig


def list_aliases(config):
    entries = config.list_aliases()
    if not entries:
        print("No SSH aliases found.")
        return
    for alias, path, editable in entries:
        status = "" if editable else " (read-only)"
        print(f"{alias}\t{path}{status}")


def add_alias(config, alias, host, user, port, identity):
    config.add(alias, host, user, port, identity)
    print(f"Saved '{alias}'. Connect with ssh {alias}.")


def rename_alias(config, alias, new_alias):
    config.change(alias, new_alias)
    print(f"Alias '{alias}' is now '{new_alias}'.")


def remove_alias(config, alias):
    config.change(alias)
    print(f"Removed '{alias}'.")


def menu(config):
    while True:
        print("\nSSH aliases\n1. List\n2. Add\n3. Rename\n4. Remove\n0. Quit")
        action = input("Choose an option: ").strip()
        try:
            if action == "0":
                return
            if action == "1":
                list_aliases(config)
            elif action == "2":
                alias = input("Alias: ").strip()
                host = input("Hostname or IP address: ").strip()
                user = input("SSH username: ").strip()
                port = input("Port [22]: ").strip() or 22
                identity = input("Private key path [optional]: ").strip() or None
                add_alias(config, alias, host, user, port, identity)
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
            else:
                print("Choose a listed option.")
        except (OSError, ValueError) as error:
            print(f"Error: {error}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Manage OpenSSH aliases or open an interactive menu.")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("list", help="List SSH aliases")

    add = commands.add_parser("add", help="Add an SSH alias")
    add.add_argument("alias")
    add.add_argument("--host", required=True, help="Hostname or IP address")
    add.add_argument("--user", required=True, help="SSH username")
    add.add_argument("--port", default=22, help="SSH port (default: 22)")
    add.add_argument("--identity-file", help="Path to a local private key")

    rename = commands.add_parser("rename", help="Rename an SSH alias")
    rename.add_argument("alias")
    rename.add_argument("new_alias")

    remove = commands.add_parser("remove", help="Remove an SSH alias")
    remove.add_argument("alias")

    args = parser.parse_args()
    config = SSHConfig(Path.home() / ".ssh")
    try:
        if args.command == "list":
            list_aliases(config)
        elif args.command == "add":
            add_alias(config, args.alias, args.host, args.user, args.port, args.identity_file)
        elif args.command == "rename":
            rename_alias(config, args.alias, args.new_alias)
        elif args.command == "remove":
            remove_alias(config, args.alias)
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
