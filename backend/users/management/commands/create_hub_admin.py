from getpass import getpass

from allauth.account.models import EmailAddress
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, IntegrityError, transaction

from users.lifecycle import audit
from users.models import User
from users.setup import close_setup


class Command(BaseCommand):
    help = "Create the first active Knowledge Hub administrator from the deployment console."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("email")

    def handle(self, *args, **options):
        if User.objects.filter(role=User.Role.ADMIN, is_active=True).exists():
            raise CommandError("An active administrator already exists.")
        user = User(username=options["username"], email=options["email"].lower(), role=User.Role.ADMIN)
        try:
            user.full_clean(exclude=["password"])
            password = getpass("Password: ")
            if password != getpass("Confirm password: "):
                raise CommandError("Passwords do not match.")
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error
        user.set_password(password)
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ["knowledge-hub:bootstrap"])
                if User.objects.filter(role=User.Role.ADMIN, is_active=True).exists():
                    raise CommandError("An active administrator already exists.")
                user.save()
                EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
                audit("admin_bootstrapped", user, via="command")
                close_setup()  # P24: the setup wizard and its code are no longer needed
        except IntegrityError as error:
            raise CommandError("Username or email already exists.") from error
        self.stdout.write(self.style.SUCCESS("Administrator created."))
