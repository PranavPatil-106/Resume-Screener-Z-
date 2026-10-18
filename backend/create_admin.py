"""
One-time CLI command to initialize the first administrator account.

Guards:
- Refuses execution if any user account already exists in the database.
- Strictly interactive password entry via getpass (never via CLI flags or arguments).
- Re-prompts for confirmation; passwords must match.
- Uses Argon2id via password_security.hash_password.
- Plaintext passwords and hashes are never printed or logged.
- No import-time side effects (runs only when explicitly executed as a script).
"""

import getpass
import sys
from database import SessionLocal
from models import User, UserRole, UserStatus
from password_security import hash_password


def validate_email_format(email: str) -> str:
    """Validate and normalize candidate email address."""
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("Invalid email format. Please provide a valid email address.")
    parts = normalized.split("@")
    if len(parts) != 2 or "." not in parts[1]:
        raise ValueError("Invalid email format. Domain part must contain a valid hostname.")
    return normalized


def create_initial_admin() -> None:
    """Interactively creates the first administrator user if no accounts exist."""
    db = SessionLocal()
    try:
        # Strict guard: refuse to create if ANY user already exists in the database
        user_count = db.query(User).count()
        if user_count > 0:
            print(
                "Error: One or more user accounts already exist in the database.\n"
                "This command can only be used to create the initial administrator account.",
                file=sys.stderr,
            )
            sys.exit(1)

        print("=== Create Initial Administrator Account ===")
        print("Note: This command can only run once when no accounts exist.\n")

        try:
            raw_email = input("Administrator email: ")
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(1)

        try:
            email = validate_email_format(raw_email)
        except ValueError as err:
            print(f"Error: {err}", file=sys.stderr)
            sys.exit(1)

        try:
            password = getpass.getpass("Password: ")
            if not password:
                print("Error: Password cannot be empty.", file=sys.stderr)
                sys.exit(1)
            if len(password) < 8:
                print("Error: Password must be at least 8 characters long.", file=sys.stderr)
                sys.exit(1)

            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                print("Error: Passwords do not match.", file=sys.stderr)
                sys.exit(1)
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(1)

        # Hash password with Argon2id
        pw_hash = hash_password(password)

        # Clear plaintext password variables from local memory
        del password
        del confirm

        # Create active admin user
        admin_user = User(
            email=email,
            role=UserRole.ADMIN.value,
            status=UserStatus.ACTIVE.value,
            password_hash=pw_hash,
        )

        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)

        print(f"\nInitial administrator account created successfully for: {admin_user.email}")
    except Exception as exc:
        db.rollback()
        print(f"Error creating administrator account: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    create_initial_admin()
