"""User accounts (admins): list, create, change, delete; iothing-auth's routes. The role shown and set is the
account's role in ionotes."""

from app.auth import auth

router = auth.users_router()
