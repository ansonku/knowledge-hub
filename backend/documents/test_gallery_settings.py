from django.test import Client, TestCase

from users.models import AuditLog, User

from .models import SiteSettings

URL = "/api/site/gallery/"
STANDARD = {"effect": "center", "speed": "normal", "backdrop": 92, "layout": "justified", "member_download": True,
            "respect_reduced_motion": True}


class GallerySettingsTests(TestCase):
    """P11d: site-wide lightbox and gallery choices; anyone reads them, only Admins change them."""

    def setUp(self):
        self.admin = User.objects.create_user("admin", "admin@example.test", role=User.Role.ADMIN)
        self.editor = User.objects.create_user("editor", "editor@example.test", role=User.Role.EDITOR)
        self.client.force_login(self.admin)

    def put(self, data, client=None):
        return (client or self.client).put(URL, data, content_type="application/json")

    def test_defaults_are_public(self):
        self.assertEqual(Client().get("/api/site/").json()["gallery"], STANDARD)

    def test_admin_changes_them_and_the_change_is_audited(self):
        response = self.put({**STANDARD, "effect": "zoom", "speed": "fast", "backdrop": 100, "layout": "masonry", "member_download": False,
                             "respect_reduced_motion": False})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["gallery"], {"effect": "zoom", "speed": "fast", "backdrop": 100, "layout": "masonry", "member_download": False,
                                                      "respect_reduced_motion": False})
        self.assertEqual(SiteSettings.current().lightbox_reduced_motion, False)
        self.assertEqual(Client().get("/api/site/").json()["gallery"]["layout"], "masonry")
        entry = AuditLog.objects.get(action="site_gallery_updated")
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.metadata["gallery"]["effect"], {"from": "center", "to": "zoom"})
        self.assertEqual(entry.metadata["gallery"]["member_download"], {"from": True, "to": False})
        row = next(row for row in self.client.get("/api/admin/audit/").json()["results"] if row["action"] == "site_gallery_updated")
        self.assertEqual(row["detail"]["gallery"]["layout"], {"from": "justified", "to": "masonry"})

    def test_saving_without_changes_is_not_audited(self):
        self.assertEqual(self.put(STANDARD).status_code, 200)
        self.assertFalse(AuditLog.objects.filter(action="site_gallery_updated").exists())

    def test_only_admins(self):
        editor = Client()
        editor.force_login(self.editor)
        self.assertEqual(self.put({**STANDARD, "speed": "slow"}, editor).status_code, 403)
        self.assertEqual(self.put({**STANDARD, "speed": "slow"}, Client()).status_code, 403)
        self.assertEqual(SiteSettings.current().lightbox_speed, "normal")

    def test_values_are_checked(self):
        for bad in ({"effect": "spin"}, {"speed": "warp"}, {"backdrop": 59}, {"backdrop": 101}, {"layout": ""}, {"layout": "gird"}):
            with self.subTest(bad):
                self.assertEqual(self.put({**STANDARD, **bad}).status_code, 400)
        self.assertEqual(self.put({"effect": "zoom"}).status_code, 400)  # every field is required
