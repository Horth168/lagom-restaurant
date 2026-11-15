"""Create the first OWNER account (or another owner).

Usage (from the backend folder, with the virtual environment active):

    python -m scripts.create_owner

You will be asked for the email, name and password. The password is never shown
or stored in plain text.

Non-interactive (e.g. on Render's shell):
    set OWNER_EMAIL, OWNER_NAME, OWNER_PASSWORD environment variables, then run the same command.
"""
import getpass
import os
import sys

from sqlalchemy import func, select

from app.core.security import hash_password, password_problems
from app.db import SessionLocal
from app.models import User
from app.models.enums import Role
from app.services.audit import audit


def main() -> int:
    email = os.environ.get("OWNER_EMAIL") or input("Owner email: ").strip()
    name = os.environ.get("OWNER_NAME") or input("Full name: ").strip()
    password = os.environ.get("OWNER_PASSWORD")
    if not password:
        password = getpass.getpass("Password (min 10 chars, upper+lower case, a number): ")
        if password != getpass.getpass("Repeat password: "):
            print("Passwords do not match.")
            return 1
    if problems := password_problems(password):
        print("Password is too weak: " + "; ".join(problems))
        return 1

    with SessionLocal() as db:
        email = email.lower()
        if db.scalar(select(User).where(func.lower(User.email) == email)):
            print(f"An account with {email} already exists.")
            return 1
        user = User(email=email, full_name=name or "Owner", role=Role.OWNER, password_hash=hash_password(password))
        db.add(user)
        db.flush()
        audit(db, "staff.created", "user", user.id, details={"role": "OWNER", "via": "create_owner script"})
        db.commit()
        print(f"Owner account created for {email}. You can now sign in at /admin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
