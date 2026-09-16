import getpass

from app.auth import hash_password


if __name__ == "__main__":
    password = getpass.getpass("Admin password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords did not match.")
    print(hash_password(password))
