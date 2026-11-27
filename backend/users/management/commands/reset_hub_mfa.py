from allauth.mfa.models import Authenticator
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from users.lifecycle import audit, revoke_sessions
from users.models import User


class Command(BaseCommand):
    help = ("P25: turn off two-factor for one account from the host, when nobody can reset it in the web "
            "(for example the only admin lost both phone and recovery codes). Signs the account out everywhere.")

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--reason", required=True, help="Why, for the audit log (e.g. how the person's identity was checked).")

    def handle(self, *args, **options):
        reason = options["reason"].strip()
        if len(reason) < 4:
            raise CommandError("Give a reason of at least a few words.")
        with transaction.atomic():
            user = User.objects.select_for_update().filter(email__iexact=options["email"].strip()).first()
            if user is None:
                raise CommandError("No account has that email address.")
            removed, _ = Authenticator.objects.filter(user=user).delete()
            if not removed:
                raise CommandError("That account does not use two-factor authentication.")
            revoke_sessions(user)
            audit("mfa_command_reset", user, reason=reason)
        self.stdout.write(self.style.SUCCESS(
            f"Two-factor authentication is off for {user.email}; the account was signed out everywhere. "
            "Ask them to turn it on again after signing in."
        ))
