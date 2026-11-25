import importlib

from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from .links import linked_ids
from .models import Document, VersionLink
from .test_images import ImageFixture

A = "11111111-1111-1111-1111-111111111111"
B = "22222222-2222-2222-2222-222222222222"


class LinkParsingTests(ImageFixture):
    """P13: which addresses count as links to documents."""

    @override_settings(PUBLIC_ORIGIN="https://kb.example.test", ALLOWED_HOSTS=["intranet.local", ".example.org"])
    def test_paths_full_urls_and_code(self):
        text = f"""[a](/app/docs/{A}/) [again](/read/{A}/?x=1#s) [b](https://kb.example.test/articles/{B}/)
[elsewhere](https://other.example/app/docs/{"3" * 8}-3333-3333-3333-{"3" * 12}/) /app/docs/not-a-uuid/
`/app/docs/{"4" * 8}-4444-4444-4444-{"4" * 12}/`

```
[x](/app/docs/{"5" * 8}-5555-5555-5555-{"5" * 12}/)
```
<https://kb.example.test/app/docs/{B}>
[intranet](http://intranet.local:18080/read/{"6" * 8}-6666-6666-6666-{"6" * 12}/)
"""
        self.assertEqual(linked_ids(text), [A, B, f'{"6" * 8}-6666-6666-6666-{"6" * 12}'])


class LinkTests(ImageFixture):
    """P13a: links are recorded per version; backlinks count current versions only; readers see what they may."""

    def setUp(self):
        super().setUp()
        self.target = self.create("# 目標\n", "target.md")
        self.other = self.create("# 另一份\n", "other.md")

    def links(self, document, client=None):
        return (client or self.client).get(f"/api/documents/{document}/links/").json()

    def test_edits_uploads_restores_and_new_documents_record_links(self):
        self.edit(f"[目標](/app/docs/{self.target}/)\n")
        self.assertEqual([item["id"] for item in self.links(self.target)["incoming"]], [self.doc])
        first = self.current()
        self.edit("沒有連結了\n")
        self.assertEqual(self.links(self.target)["incoming"], [])  # only current versions count
        response = self.client.post(f"/api/documents/{self.doc}/versions/{first}/restore/", {"base_version": self.current()},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(len(self.links(self.target)["incoming"]), 1)
        response = self.client.post(f"/api/documents/{self.other}/versions/", {
            "file": SimpleUploadedFile("other.md", f"# 另一份\n[t](/read/{self.target}/)\n".encode()),
        })
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(len(self.links(self.target)["incoming"]), 2)

    def test_self_links_are_ignored(self):
        self.edit(f"[自己](/app/docs/{self.doc}/)\n")
        self.assertFalse(VersionLink.objects.exists())

    def test_outgoing_states(self):
        missing = "99999999-9999-9999-9999-999999999999"
        self.edit(f"[t](/app/docs/{self.target}/) [o](/app/docs/{self.other}/) [m](/app/docs/{missing}/)\n")
        self.assertEqual(self.client.delete(f"/api/documents/{self.other}/").status_code, 204)
        outgoing = {item["id"]: item for item in self.links(self.doc)["outgoing"]}
        self.assertEqual(outgoing[self.target]["status"], "ok")
        self.assertEqual(outgoing[self.target]["title"], "target")
        self.assertEqual((outgoing[self.other]["status"], outgoing[self.other]["title"]), ("trashed", "other"))
        self.assertEqual(outgoing[missing], {"id": missing, "status": "missing"})
        viewer = {item["id"]: item for item in self.links(self.doc, self.as_user(self.viewer))["outgoing"]}
        self.assertEqual(viewer[self.other], {"id": self.other, "status": "trashed"})  # no title for readers without the trash

    def test_trashed_sources_do_not_count(self):
        self.edit(f"[t](/app/docs/{self.target}/)\n")
        self.assertEqual(self.client.delete(f"/api/documents/{self.doc}/").status_code, 204)
        self.assertEqual(self.links(self.target)["incoming"], [])

    def test_permanently_deleted_target_shows_as_missing(self):
        self.edit(f"[o](/app/docs/{self.other}/)\n")
        self.assertEqual(self.client.delete(f"/api/documents/{self.other}/").status_code, 204)
        response = self.as_user(self.admin).post(f"/api/trash/{self.other}/delete/", {"title": "other", "confirm": True},
                                                 content_type="application/json")
        self.assertIn(response.status_code, (200, 204), response.content)
        self.assertEqual(self.links(self.doc)["outgoing"], [{"id": self.other, "status": "missing"}])

    def test_access(self):
        self.assertEqual(self.as_user().get(f"/api/documents/{self.target}/links/").status_code, 403)
        self.assertEqual(self.as_user(self.viewer).get(f"/api/documents/{self.target}/links/").status_code, 200)
        self.assertEqual(self.as_user().get(f"/api/documents/resolve/?ids={self.target}").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/documents/{self.target}/").status_code, 204)
        self.assertEqual(self.client.get(f"/api/documents/{self.target}/links/").status_code, 404)

    def test_resolve_and_incoming_counts(self):
        self.edit(f"[t](/app/docs/{self.target}/)\n")
        resolved = self.client.get(f"/api/documents/resolve/?ids={self.target},{A}").json()
        self.assertEqual((resolved[self.target]["status"], resolved[self.target]["title"]), ("ok", "target"))
        self.assertEqual(resolved[A], {"status": "missing"})
        counts = self.client.get(f"/api/documents/incoming-links/?ids={self.target},{self.other}").json()
        self.assertEqual(counts, {self.target: 1, self.other: 0})
        # Links from documents in the same selection do not count: they are going to the trash too.
        counts = self.client.get(f"/api/documents/incoming-links/?ids={self.target},{self.doc}").json()
        self.assertEqual(counts[self.target], 0)
        self.assertEqual(self.client.get("/api/documents/resolve/?ids=nope").status_code, 400)

    def test_migration_backfills_current_versions(self):
        self.edit(f"[t](/app/docs/{self.target}/)\n")
        VersionLink.objects.all().delete()
        importlib.import_module("documents.migrations.0020_version_links").backfill_links(apps, None)
        self.assertEqual(VersionLink.objects.get().target_id.hex, self.target.replace("-", ""))
        self.assertEqual(Document.objects.count(), 3)
