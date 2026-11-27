from django.core.management.base import BaseCommand

from users.setup import close_setup, has_admin, open_setup


class Command(BaseCommand):
    help = "P24: at start-up, open first-run setup for an hour (with a new setup code) while no active admin exists."

    def handle(self, *args, **options):
        if has_admin():
            close_setup()
            return
        path = open_setup()
        # Never print the code itself: logs are not a place for secrets.
        self.stdout.write(
            f"首次設定已開放一小時：請在瀏覽器開啟網站完成設定。超過時限時需要設定碼，"
            f"用 `docker compose exec backend cat {path}` 查看。"
        )
