import importlib

from django.apps import apps
from django.test import Client, TestCase

from users.models import User

from .models import AUTO_COLLECTION_COLORS, Category, SiteSettings


class SiteSettingsTests(TestCase):
    """P5a: site name/tagline and automatic collection colours."""

    def setUp(self):
        self.admin = User.objects.create_user("admin", "admin@example.test", role=User.Role.ADMIN)
        self.editor = User.objects.create_user("editor", "editor@example.test", role=User.Role.EDITOR)

    def as_user(self, user):
        client = Client()
        if user:
            client.force_login(user)
        return client

    def test_anyone_reads_only_admins_change(self):
        self.assertEqual(Client().get("/api/site/").json(),
                         {"name": SiteSettings.DEFAULT_NAME, "tagline": SiteSettings.DEFAULT_TAGLINE})
        payload = {"name": "  研發知識庫 ", "tagline": "<b>規格</b>與指南"}
        for user in (None, self.editor):
            self.assertEqual(self.as_user(user).patch("/api/site/", payload, content_type="application/json").status_code, 403)
        response = self.as_user(self.admin).patch("/api/site/", payload, content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"name": "研發知識庫", "tagline": "<b>規格</b>與指南"})
        self.assertEqual(SiteSettings.objects.get().updated_by, self.admin)
        self.assertEqual(Client().get("/api/site/").json()["name"], "研發知識庫")
        too_long = {"name": "x" * 61, "tagline": ""}
        self.assertEqual(self.as_user(self.admin).patch("/api/site/", too_long, content_type="application/json").status_code, 400)
        self.assertEqual(self.as_user(self.admin).patch("/api/site/", {"name": "", "tagline": ""}, content_type="application/json").status_code, 400)

    def test_seo_head_uses_escaped_site_settings(self):
        self.as_user(self.admin).patch("/api/site/", {"name": "研發<知識>庫", "tagline": "介紹 & 說明"}, content_type="application/json")
        head = Client().get("/articles/")["X-Hub-Head"]
        self.assertTrue(head.isascii())
        self.assertIn("<title>&#30740;&#30332;&lt;&#30693;&#35672;&gt;&#24235;</title>", head)
        self.assertIn('og:site_name" content="&#30740;&#30332;&lt;', head)
        self.assertIn("&amp;", head)

    def test_new_collections_get_the_least_used_colour(self):
        editor = self.as_user(self.editor)
        colors = [editor.post("/api/categories/", {"name": f"C{index}"}, content_type="application/json").json()["color"]
                  for index in range(len(AUTO_COLLECTION_COLORS) + 1)]
        self.assertEqual(colors, [*AUTO_COLLECTION_COLORS, AUTO_COLLECTION_COLORS[0]])
        chosen = editor.post("/api/categories/", {"name": "Grey", "color": "gray"}, content_type="application/json").json()
        self.assertEqual(chosen["color"], "gray")
        # Editing never re-colours a collection.
        category = Category.objects.get(name="Grey")
        editor.patch(f"/api/categories/{category.pk}/", {"name": "Grey 2"}, content_type="application/json")
        category.refresh_from_db()
        self.assertEqual(category.color, "gray")

    def test_migration_colours_existing_collections_evenly(self):
        assign = importlib.import_module("documents.migrations.0010_collection_colors").assign_colors
        Category.objects.create(name="Kept", color="blue")
        parent = Category.objects.create(name="Z parent")
        Category.objects.create(name="A child", parent=parent)
        for name in ("B", "A"):
            Category.objects.create(name=name)
        assign(apps, None)
        colors = dict(Category.objects.values_list("name", "color"))
        self.assertEqual(colors, {"Kept": "blue", "A": "teal", "B": "green", "Z parent": "amber", "A child": "orange"})

