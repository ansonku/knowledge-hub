import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TransactionTestCase, override_settings

from users.models import User

from .models import Category, Document, DocumentActivity, Tag


class OrganizeTests(TransactionTestCase):
    """P8: set the collection and add tags to a finished upload batch in one step."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings = override_settings(DOCUMENT_STORAGE=str(Path(temporary.name)))
        settings.enable()
        self.addCleanup(settings.disable)
        self.editor = User.objects.create_user("editor", "editor@example.test", role=User.Role.EDITOR)
        self.viewer = User.objects.create_user("reader", "reader@example.test")
        self.client.force_login(self.editor)
        self.specs = Category.objects.create(name="規格")
        self.guides = Category.objects.create(name="指南")
        self.urgent, self.draft, self.old = (Tag.objects.create(name=name) for name in ("急件", "草稿", "舊標籤"))
        self.first = self.upload(b"one", category=str(self.guides.pk))
        self.second = self.upload(b"two")
        Document.objects.get(pk=self.first).tags.add(self.old)

    def upload(self, content, **data):
        response = self.client.post("/api/documents/", {"file": SimpleUploadedFile("doc.md", content), **data})
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["id"]

    def organize(self, client=None, ids=None, **data):
        payload = {"ids": ids or [self.first, self.second], "action": "organize", **data}
        return (client or self.client).post("/api/documents/bulk/", payload, content_type="application/json")

    def state(self, document_id):
        document = Document.objects.get(pk=document_id)
        return document.category_id, set(document.tags.values_list("name", flat=True))

    def metadata_activity(self, document_id):
        return list(DocumentActivity.objects.filter(document_id=document_id, action=DocumentActivity.Action.METADATA))

    def test_sets_collection_and_adds_tags_together(self):
        response = self.organize(category=str(self.specs.pk), tags=[str(self.urgent.pk), str(self.draft.pk)])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"count": 2})
        self.assertEqual(self.state(self.first), (self.specs.pk, {"舊標籤", "急件", "草稿"}))
        self.assertEqual(self.state(self.second), (self.specs.pk, {"急件", "草稿"}))
        # One activity entry per document, holding both changes.
        [entry] = self.metadata_activity(self.first)
        self.assertEqual(entry.detail["category"], {"from": "指南", "to": "規格"})
        self.assertEqual(entry.detail["tags"], {"added": ["急件", "草稿"], "removed": []})

    def test_tags_only_leaves_collections_alone(self):
        self.assertEqual(self.organize(tags=[str(self.urgent.pk)]).status_code, 200)
        self.assertEqual(self.state(self.first), (self.guides.pk, {"舊標籤", "急件"}))
        self.assertEqual(self.state(self.second), (None, {"急件"}))

    def test_collection_only_and_explicit_uncategorised(self):
        self.assertEqual(self.organize(category=str(self.specs.pk)).status_code, 200)
        self.assertEqual(self.state(self.first)[0], self.specs.pk)
        self.assertEqual(self.organize(category=None).status_code, 200)
        self.assertEqual((self.state(self.first)[0], self.state(self.second)[0]), (None, None))
        self.assertEqual(self.state(self.first)[1], {"舊標籤"})

    def test_nothing_changes_means_no_activity(self):
        self.assertEqual(self.organize(ids=[self.first], category=str(self.guides.pk), tags=[str(self.old.pk)]).status_code, 200)
        self.assertEqual(self.metadata_activity(self.first), [])

    def test_needs_a_collection_or_tags(self):
        response = self.organize()
        self.assertEqual(response.status_code, 400)
        self.assertIn("請選擇集合或標籤", str(response.json()))

    def test_viewers_cannot_organize(self):
        viewer = Client()
        viewer.force_login(self.viewer)
        self.assertEqual(self.organize(viewer, tags=[str(self.urgent.pk)]).status_code, 403)
        self.assertEqual(self.state(self.second), (None, set()))

    def test_a_trashed_document_leaves_the_whole_batch_unchanged(self):
        self.assertEqual(self.client.delete(f"/api/documents/{self.second}/").status_code, 204)
        response = self.organize(category=str(self.specs.pk), tags=[str(self.urgent.pk)])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["missing"], [self.second])
        self.assertEqual(self.state(self.first), (self.guides.pk, {"舊標籤"}))

    def test_at_most_100_documents(self):
        ids = [self.first] + [f"00000000-0000-0000-0000-{n:012d}" for n in range(100)]
        self.assertEqual(self.organize(ids=ids, tags=[str(self.urgent.pk)]).status_code, 400)
