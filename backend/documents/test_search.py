"""P16a: search snippets, matched fields and relevance order (workspace, reading portal, public site)."""
from django.test import SimpleTestCase

from . import search
from .models import Category, Tag
from .test_images import ImageFixture


class SnippetTests(SimpleTestCase):
    def test_centred_with_ellipses_and_two_pieces_for_far_apart_words(self):
        text = "前言" * 60 + "韌體更新的步驟" + "中段" * 80 + "最後確認校驗碼" + "結尾" * 60
        pieces = search.snippets(text, ["韌體", "校驗碼"])
        self.assertEqual(len(pieces), 2)
        self.assertIn("韌體", pieces[0])
        self.assertIn("校驗碼", pieces[1])
        self.assertTrue(all(piece.startswith("…") and piece.endswith("…") for piece in pieces))
        self.assertTrue(all(len(piece) <= search.SNIPPET_WIDTH + 2 for piece in pieces))

    def test_close_matches_merge_and_short_text_has_no_ellipsis(self):
        self.assertEqual(search.snippets("BMC 韌體更新步驟", ["韌體", "更新"]), ["BMC 韌體更新步驟"])

    def test_pieces_stay_short_when_matches_are_close(self):
        text = "開頭" * 50 + "韌體" + "中" * 40 + "韌體" + "中" * 40 + "韌體" + "結尾" * 50
        pieces = search.snippets(text, ["韌體"])
        self.assertTrue(all(len(piece) <= search.SNIPPET_WIDTH + 2 for piece in pieces), pieces)

    def test_a_leading_title_is_not_a_body_match(self):
        details = search.match_details(["韌體"], title="韌體指南", body="# 韌體指南 內容沒有提到", document_format="md")
        self.assertEqual(details, {"fields": ["title"], "snippets": []})

    def test_case_insensitive_and_no_match(self):
        self.assertEqual(search.snippets("OpenBMC service", ["bmc"]), ["OpenBMC service"])
        self.assertEqual(search.snippets("沒有關鍵字", ["韌體"]), [])

    def test_does_not_cut_a_latin_word(self):
        text = "word " * 40 + "needle " + "tail " * 40
        self.assertFalse(search.snippets(text, ["needle"])[0].lstrip("…").startswith(("ord", "rd", "d ")))

    def test_markdown_noise_removed_but_alt_text_kept(self):
        text = search.readable_text(
            "## 步驟 **粗體** [連結文字](/app/docs/x/) ![機箱正面](/api/images/1/) :::gallery grid - [x] 完成 `code` | 表格 |",
            "md")
        for noise in ("##", "**", "/app/docs", "/api/images", ":::", "[x]", "`", "|"):
            self.assertNotIn(noise, text)
        for kept in ("步驟", "粗體", "連結文字", "機箱正面", "完成", "code", "表格"):
            self.assertIn(kept, text)


class SearchApiTests(ImageFixture):
    def setUp(self):
        super().setUp()
        self.body_only = self.create("# 說明\n\n" + "一般內容。" * 40 + "這裡提到韌體一次。\n", "其他說明.md")
        self.titled = self.create("# 韌體更新指南\n\n步驟如下。\n", "韌體更新指南.md")
        self.tagged = self.create("# 備註\n\n內容。\n", "備註.md")
        tag = Tag.objects.create(name="韌體")
        self.client.patch(f"/api/documents/{self.tagged}/", {"tags": [str(tag.pk)]}, content_type="application/json")

    def ids(self, response):
        return [str(row.get("id") or row.get("document_id")) for row in response.json()["results"]]

    def test_workspace_relevance_by_default_and_time_on_request(self):
        response = self.client.get("/api/documents/", {"q": "韌體"})
        self.assertEqual(response.json()["ordering"], "relevance")
        self.assertEqual(self.ids(response), [self.titled, self.tagged, self.body_only])
        by_time = self.client.get("/api/documents/", {"q": "韌體", "ordering": "updated_at"})
        self.assertEqual(self.ids(by_time), [self.body_only, self.titled, self.tagged])

    def test_workspace_matches(self):
        rows = {str(row["id"]): row["matches"] for row in self.client.get("/api/documents/", {"q": "韌體"}).json()["results"]}
        self.assertEqual(rows[self.titled], {"fields": ["title"], "snippets": []})
        self.assertEqual(rows[self.tagged], {"fields": ["tags"], "snippets": []})
        self.assertEqual(rows[self.body_only]["fields"], ["body"])
        self.assertIn("韌體", rows[self.body_only]["snippets"][0])
        self.assertTrue(rows[self.body_only]["snippets"][0].startswith("…"))

    def test_collection_match_counts_as_label(self):
        category = Category.objects.create(name="韌體專區")
        other = self.create("# 無關\n", "無關.md")
        self.client.patch(f"/api/documents/{other}/", {"category": str(category.pk)}, content_type="application/json")
        rows = {str(row["id"]): row["matches"] for row in self.client.get("/api/documents/", {"q": "韌體"}).json()["results"]}
        self.assertEqual(rows[other]["fields"], ["collection"])

    def test_no_words_no_matches_and_time_order(self):
        body = self.client.get("/api/documents/").json()
        self.assertEqual(body["ordering"], "-updated_at")
        self.assertNotIn("matches", body["results"][0])

    def test_reading_portal(self):
        body = self.as_user(self.viewer).get("/api/read/articles/", {"q": "韌體"}).json()
        self.assertEqual([str(row["document_id"]) for row in body["results"]], [self.titled, self.tagged, self.body_only])
        self.assertEqual(body["results"][0]["matches"], {"fields": ["title"], "snippets": []})

    def test_public_uses_the_published_version_only(self):
        version = self.edit("# 公開\n\n公開版本談到韌體。\n", self.body_only)
        response = self.as_user(self.admin).post(f"/api/documents/{self.body_only}/publication/",
                                                 {"version": version, "title": "其他說明"}, content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        self.edit("# 草稿\n\n草稿才有的祕密字詞與韌體。\n", self.body_only)
        public = self.as_user().get("/api/public/articles/", {"q": "韌體"})
        self.assertEqual(self.ids(public), [self.body_only])
        snippet = public.json()["results"][0]["matches"]["snippets"][0]
        self.assertIn("公開版本談到韌體", snippet)
        self.assertNotIn("祕密", snippet)
        self.assertEqual(self.as_user().get("/api/public/articles/", {"q": "祕密"}).json()["count"], 0)
        self.assertNotIn("matches", self.as_user().get("/api/public/articles/").json()["results"][0])


class CategoryScopeTests(ImageFixture):
    """P17: category_scope=direct lists one level of a collection."""

    def test_direct_leaves_out_sub_collections(self):
        parent = Category.objects.create(name="上層")
        child = Category.objects.create(name="下層", parent=parent)
        top = self.create("# 上層文件\n", "上層文件.md")
        below = self.create("# 下層文件\n", "下層文件.md")
        self.client.patch(f"/api/documents/{top}/", {"category": str(parent.pk)}, content_type="application/json")
        self.client.patch(f"/api/documents/{below}/", {"category": str(child.pk)}, content_type="application/json")

        def ids(**params):
            return {str(row["id"]) for row in self.client.get("/api/documents/", params).json()["results"]}

        self.assertEqual(ids(category=str(parent.pk)), {top, below})
        self.assertEqual(ids(category=str(parent.pk), category_scope="direct"), {top})
        self.assertEqual(ids(category=str(child.pk), category_scope="direct"), {below})
        self.assertEqual(self.client.get("/api/documents/", {"category": str(parent.pk), "category_scope": "all"}).status_code, 400)
