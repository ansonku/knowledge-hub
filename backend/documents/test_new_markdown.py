import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TransactionTestCase, override_settings

from users.models import User

from .models import Category, DocumentActivity, Tag, Version
from .services import markdown_filename


class NewMarkdownTests(TransactionTestCase):
    """P9: write a Markdown document in the editor instead of uploading a file."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.storage = Path(temporary.name)
        settings = override_settings(DOCUMENT_STORAGE=str(self.storage))
        settings.enable()
        self.addCleanup(settings.disable)
        self.editor = User.objects.create_user("editor", "editor@example.test", role=User.Role.EDITOR)
        self.viewer = User.objects.create_user("reader", "reader@example.test")
        self.client.force_login(self.editor)

    def create(self, client=None, **data):
        return (client or self.client).post("/api/documents/new/", data, content_type="application/json")

    def test_creates_a_markdown_document_with_its_title_as_v1(self):
        guides, urgent = Category.objects.create(name="指南"), Tag.objects.create(name="急件")
        response = self.create(title="  韌體  更新\n步驟  ", category=str(guides.pk), tags=[str(urgent.pk)])
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["title"], body["format"], body["category"]), ("韌體 更新 步驟", "md", str(guides.pk)))
        self.assertEqual([tag["id"] for tag in body["tags"]], [str(urgent.pk)])
        version = Version.objects.get(document_id=body["id"])
        self.assertEqual((version.number, version.source, version.filename, version.created_by),
                         (1, "create", "韌體 更新 步驟.md", self.editor))
        self.assertEqual((self.storage / version.path).read_text(encoding="utf-8"), "# 韌體 更新 步驟\n\n")
        self.assertEqual(body["current_version"]["source"], "create")
        activity = DocumentActivity.objects.get(document_id=body["id"])
        self.assertEqual((activity.action, activity.version_number), (DocumentActivity.Action.CREATED, 1))

    def test_found_by_search_and_editable_right_away(self):
        document = self.create(title="會議紀錄 草稿").json()
        results = self.client.get("/api/documents/", {"q": "會議紀錄"}).json()["results"]
        self.assertIn(document["id"], [row["id"] for row in results])
        response = self.client.post(f"/api/documents/{document['id']}/markdown/", {
            "file": SimpleUploadedFile("x.md", "# 會議紀錄 草稿\n\n內容\n".encode()),
            "base_version": document["current_version"]["id"],
        })
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["current_version"]["number"], 2)

    def test_same_title_twice_is_fine_but_uploads_still_check_duplicates(self):
        first, second = self.create(title="新文件"), self.create(title="新文件")
        self.assertEqual((first.status_code, second.status_code), (201, 201))
        self.assertNotEqual(first.json()["id"], second.json()["id"])
        upload = self.client.post("/api/documents/", {"file": SimpleUploadedFile("dup.md", "# 新文件\n\n".encode())})
        self.assertEqual(upload.status_code, 409)

    def test_title_is_required_and_bounded(self):
        self.assertEqual(self.create(title="").status_code, 400)
        self.assertEqual(self.create(title="   \n ").status_code, 400)
        self.assertEqual(self.create().status_code, 400)
        self.assertEqual(self.create(title="x" * 241).status_code, 400)
        self.assertEqual(self.create(title="x" * 240).status_code, 201)

    def test_only_editors(self):
        viewer = Client()
        viewer.force_login(self.viewer)
        self.assertEqual(self.create(viewer, title="不行").status_code, 403)
        self.assertEqual(self.create(Client(), title="不行").status_code, 403)
        self.assertFalse(Version.objects.exists())

    def test_file_names_are_safe(self):
        self.assertEqual(markdown_filename("a/b\\c:d*e?f\"g<h>i|j"), "a b c d e f g h i j.md")
        self.assertEqual(markdown_filename("tab\there\x00nul"), "tab here nul.md")
        self.assertEqual(markdown_filename("../.."), "document.md")
        self.assertEqual(markdown_filename("///"), "document.md")
        self.assertEqual(markdown_filename("報告. "), "報告.md")
        self.assertEqual(len(markdown_filename("長" * 240)), 203)
        body = self.create(title="../etc/passwd").json()
        self.assertEqual(Version.objects.get(document_id=body["id"]).filename, "etc passwd.md")
