import getpass
import os

from app.auth import ADMIN_PASSWORD_HASH_ENV, verify_password


if __name__ == "__main__":
    password_hash = os.environ.get(ADMIN_PASSWORD_HASH_ENV)
    if not password_hash:
        raise SystemExit(f"{ADMIN_PASSWORD_HASH_ENV} is not set.")

    password = getpass.getpass("Admin password to verify: ")
    if verify_password(password, password_hash):
        print("Password matches the configured admin hash.")
    else:
        raise SystemExit("Password did not match the configured admin hash.")