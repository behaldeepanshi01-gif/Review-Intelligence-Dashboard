"""Run locally as the app owner. Passwords are entered hidden, never as arguments."""
import argparse
import getpass
import json
import manager_identity as identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["set", "remove"])
    parser.add_argument("manager_id")
    parser.add_argument("--permissions", help="Private JSON mapping dataset IDs to location lists")
    args = parser.parse_args()
    if args.operation == "remove":
        identity.remove_account(args.manager_id)
        print("Account removed. Existing sessions no longer authorize the dashboard.")
        return
    if not args.permissions:
        parser.error("set requires --permissions")
    with open(args.permissions, encoding="utf-8") as file:
        grants = json.load(file)
    password = getpass.getpass("New password (at least 16 characters): ")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords did not match. Nothing changed.")
    identity.set_account(args.manager_id, password, grants)
    print("Account saved. Previous sessions revoked.")


if __name__ == "__main__":
    main()
