import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TransactionTestCase, override_settings

from users.models import User

from .models import Document, DocumentActivity, Tag


class TagMergeTests(TransactionTestCase):
    """P4c: tag usage counts and the Admin-only tag merge."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings = override_settings(DOCUMENT_STORAGE=str(Path(temporary.name)))
        settings.enable()
        self.addCleanup(settings.disable)
        self.admin = User.objects.create_user("admin", "admin@example.test", role=User.Role.ADMIN)
        self.editor = User.objects.create_user("editor", "editor@example.test", role=User.Role.EDITOR)
        self.viewer = User.objects.create_user("reader", "reader@example.test")
        self.client.force_login(self.editor)
        self.a, self.b, self.c = (Tag.objects.create(name=name) for name in ("api", "API 設計", "介面"))

    def upload(self, content, *tags):
        response = self.client.post("/api/documents/", {
            "file": SimpleUploadedFile("doc.md", content), "tags": [str(tag.pk) for tag in tags],
        })
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["id"]

    def as_user(self, user):
        client = Client()
        if user:
            client.force_login(user)
        return client

    def merge(self, client, sources, target):
        return client.post("/api/tags/merge/", {"sources": [str(tag.pk) for tag in sources], "target": str(target.pk)},
                           content_type="application/json")

    def tag_names(self, document_id):
        return sorted(Document.objects.get(pk=document_id).tags.values_list("name", flat=True))

    def test_counts_exclude_trash_and_document_tags_have_no_counts(self):
        first = self.upload(b"one", self.a)
        self.upload(b"two", self.a, self.b)
        trashed = self.upload(b"three", self.a)
        self.client.delete(f"/api/documents/{trashed}/")
        counts = {row["name"]: row["document_count"] for row in self.client.get("/api/tags/").json()}
        self.assertEqual(counts, {"api": 2, "API 設計": 1, "介面": 0})
        self.assertEqual(self.client.get(f"/api/documents/{first}/").json()["tags"], [{"id": str(self.a.pk), "name": "api"}])

    def test_only_admins_can_merge(self):
        document = self.upload(b"one", self.a)
        for user in (None, self.viewer, self.editor):
            with self.subTest(user=user and user.username):
                self.assertEqual(self.merge(self.as_user(user), [self.a], self.c).status_code, 403)
        self.assertTrue(Tag.objects.filter(pk=self.a.pk).exists())
        self.assertEqual(self.tag_names(document), ["api"])

    def test_merge_moves_documents_records_activity_and_deletes_sources(self):
        only_a = self.upload(b"one", self.a)
        a_and_c = self.upload(b"two", self.a, self.c)
        b_only = self.upload(b"three", self.b)
        untouched = self.upload(b"four")
        trashed = self.upload(b"five", self.b)
        self.client.delete(f"/api/documents/{trashed}/")
        stamps = dict(Document.objects.values_list("pk", "updated_at"))

        response = self.merge(self.as_user(self.admin), [self.a, self.b], self.c)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"target": str(self.c.pk), "merged": 2, "documents": 4})
        for document_id in (only_a, a_and_c, b_only, trashed):
            self.assertEqual(self.tag_names(document_id), ["介面"])
        self.assertEqual(self.tag_names(untouched), [])
        self.assertEqual(list(Tag.objects.values_list("name", flat=True)), ["介面"])
        # Taxonomy tidying does not count as editing the documents.
        self.assertEqual(dict(Document.objects.values_list("pk", "updated_at")), stamps)
        entry = DocumentActivity.objects.filter(document_id=only_a, action="metadata").latest("created_at")
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.detail, {"tags": {"added": ["介面"], "removed": ["api"]}})
        unchanged_c = DocumentActivity.objects.filter(document_id=a_and_c, action="metadata").latest("created_at")
        self.assertEqual(unchanged_c.detail["tags"]["removed"], ["api"])
        self.assertFalse(DocumentActivity.objects.filter(document_id=untouched, action="metadata").exists())

    def test_merge_rejects_invalid_requests(self):
        admin = self.as_user(self.admin)
        self.assertEqual(self.merge(admin, [self.a, self.c], self.c).status_code, 400)
        self.assertEqual(self.merge(admin, [], self.c).status_code, 400)
        missing = Tag(name="gone")
        self.assertEqual(self.merge(admin, [missing], self.c).status_code, 400)
        self.assertEqual(admin.post("/api/tags/merge/", {"sources": ["nope"], "target": str(self.c.pk)},
                                    content_type="application/json").status_code, 400)
        self.assertEqual(Tag.objects.count(), 3)
