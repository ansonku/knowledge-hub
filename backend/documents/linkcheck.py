"""P18: links to this site's documents, images and videos that no longer work, and media kept only by old versions.

Only current versions of Markdown documents outside the trash are read. External addresses are never
fetched and HTML documents are not checked. Nothing is changed: the report says what to fix.
"""
import re
from collections import defaultdict
from urllib.parse import urlsplit

from django.db.models import Count, Exists, OuterRef, Sum
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from users.permissions import CanReadLibrary

from . import images, services, storage, videos
from .links import FENCE, INLINE_CODE, PATH, site_hosts
from .models import (
    ArticlePublication, Document, DocumentImage, DocumentVideo, VersionImage, VersionLink, VersionVideo,
)

# A Markdown link or image around an address, to show its text: [text](…) or ![alt](…).
MARKDOWN_LINK = re.compile(r"(!?)\[([^\]\n]*)\]\(\s*<?([^)\s>]*)")


def masked(text):
    """The text with code blanked out (same length, newlines kept), so positions still give line numbers."""
    def blank(match):
        return re.sub(r"[^\n]", " ", match.group(0))
    return INLINE_CODE.sub(blank, FENCE.sub(blank, text))


def references(text):
    """(kind, target id, position) for every reference to this site's content outside code, in text order."""
    plain, hosts, found = masked(text), site_hosts(), []
    for match in PATH.finditer(plain):
        origin = match.group(1)
        if origin and (urlsplit(origin).hostname or "").lower() not in hosts:
            continue
        found.append(("document", match.group(2).lower(), match.start()))
    for kind, pattern in (("image", images.REFERENCE), ("video", videos.REFERENCE)):
        found += [(kind, match.group(1).lower(), match.start()) for match in pattern.finditer(plain)]
    return sorted(found, key=lambda item: item[2])


def link_text(text, position):
    """The text of the Markdown link (or image alt) holding the address at `position`, else the bare address."""
    line_start = text.rfind("\n", 0, position) + 1
    line_end = text.find("\n", position)
    line = text[line_start:line_end if line_end != -1 else len(text)]
    for match in MARKDOWN_LINK.finditer(line):
        if match.start(3) <= position - line_start < match.end(3) + 1:
            return match.group(2).strip() or match.group(3)
    end = re.search(r"[\s)>\]]", text[position:])
    return text[position:position + (end.start() if end else 80)]


def read_body(version, document_id):
    with storage.open_version(version, document_id) as source:
        return source.read().decode("utf-8-sig", errors="replace")


def issue(kind, severity, reason, target, text, line, **extra):
    return {"kind": kind, "severity": severity, "reason": reason, "target": target, "text": text, "line": line, **extra}


def scan():
    documents = list(services.active_documents().filter(format=Document.Format.MARKDOWN, current_version__isnull=False)
                     .select_related("current_version", "category").order_by("title", "pk"))
    found = {}
    for document in documents:
        body = read_body(document.current_version, document.pk)
        found[document.pk] = (body, references(body))
    targets = defaultdict(set)
    for _, refs in found.values():
        for kind, target, _ in refs:
            targets[kind].add(target)
    linked = {str(row.pk): row for row in Document.objects.filter(pk__in=targets["document"]).only("pk", "title", "is_trashed")}
    media = {
        kind: {str(row.pk): row for row in model.objects.filter(pk__in=targets[kind]).select_related("document")
               .only("id", "document__id", "document__title", "document__is_trashed")}
        for kind, model in (("image", DocumentImage), ("video", DocumentVideo))
    }
    label = {"image": "圖片", "video": "影片"}

    report = []
    for document in documents:
        body, refs = found[document.pk]
        problems = []
        for kind, target, position in refs:
            line, text = body.count("\n", 0, position) + 1, link_text(body, position)
            if kind == "document":
                if target == str(document.pk):
                    continue
                row = linked.get(target)
                if row is None:
                    problems.append(issue(kind, "broken", "文件不存在（已永久刪除，或網址打錯）", target, text, line))
                elif row.is_trashed:
                    problems.append(issue(kind, "broken", f"「{row.title}」已移入回收桶", target, text, line, target_title=row.title))
                continue
            row = media[kind].get(target)
            if row is None:
                problems.append(issue(kind, "broken", f"{label[kind]}不存在（未使用超過 24 小時已清除，或網址打錯）", target, text, line))
            elif row.document_id != document.pk:
                owner = row.document
                if owner.is_trashed:
                    problems.append(issue(kind, "broken", f"{label[kind]}屬於已移入回收桶的「{owner.title}」", target, text, line,
                                          owner={"id": str(owner.pk), "title": owner.title}))
                else:
                    problems.append(issue(kind, "warning", f"{label[kind]}屬於另一份文件「{owner.title}」：那份文件移入回收桶後就會失效，訪客也看不到",
                                          target, text, line, owner={"id": str(owner.pk), "title": owner.title}))
        if problems:
            report.append((document, problems))

    # Public articles linking to documents that are not published: visitors see plain text there (P13c).
    publications = {row.document_id: row for row in ArticlePublication.objects.filter(document__in=documents).select_related("version")}
    published = {str(pk) for pk in ArticlePublication.objects.filter(document__is_trashed=False).values_list("document_id", flat=True)}
    by_document = {document.pk: problems for document, problems in report}
    for document in documents:
        publication = publications.get(document.pk)
        if publication is None:
            continue
        linked_out = {str(pk) for pk in VersionLink.objects.filter(version=publication.version).values_list("target_id", flat=True)}
        titles = {str(pk): title for pk, title in Document.objects.filter(pk__in=linked_out, is_trashed=False)
                  .exclude(pk=document.pk).values_list("pk", "title") if str(pk) not in published}
        if not titles:
            continue
        body = publication.body
        # Line numbers only help when the published version is the one being edited.
        current = publication.version_id == document.current_version_id
        for kind, target, position in references(body):
            if kind != "document" or target not in titles:
                continue
            entry = issue("public", "warning", f"公開文章連到未公開的「{titles[target]}」：訪客只會看到文字", target,
                          link_text(body, position), body.count("\n", 0, position) + 1 if current else None,
                          published_version=publication.version.number, target_title=titles[target])
            if document.pk not in by_document:
                by_document[document.pk] = []
                report.append((document, by_document[document.pk]))
            by_document[document.pk].append(entry)

    report.sort(key=lambda item: (item[0].title, str(item[0].pk)))
    rows = [{
        "id": str(document.pk), "title": document.title, "category": document.category_id,
        "category_name": document.category.name if document.category_id else None,
        "version": document.current_version.number,
        "issues": sorted(problems, key=lambda item: (item["line"] is None, item["line"] or 0)),
    } for document, problems in report]
    issues = [item for row in rows for item in row["issues"]]
    return {
        "summary": {
            "documents": len(rows), "broken": sum(item["severity"] == "broken" for item in issues),
            "warnings": sum(item["severity"] == "warning" for item in issues), "checked": len(documents),
        },
        "documents": rows,
        "storage": storage_report(),
    }


def storage_report():
    """Media no current version uses: kept by old versions (until those are deleted), or by none (cleaned after 24 h)."""
    old_only, unused = [], {"images": 0, "videos": 0, "bytes": 0}
    for kind, model, through, field in (("image", DocumentImage, VersionImage, "image"), ("video", DocumentVideo, VersionVideo, "video")):
        rows = model.objects.filter(document__is_trashed=False)
        any_version = through.objects.filter(**{field: OuterRef("pk")})
        current = through.objects.filter(**{field: OuterRef("pk")}, version_id=OuterRef("document__current_version_id"))
        for row in rows.filter(Exists(any_version)).exclude(Exists(current)).select_related("document").order_by("document__title", "pk"):
            numbers = sorted(through.objects.filter(**{field: row}).values_list("version__number", flat=True))
            old_only.append({
                "kind": kind, "id": str(row.pk), "size": row.size, "versions": numbers,
                "document": {"id": str(row.document_id), "title": row.document.title},
            })
        none = rows.exclude(Exists(any_version)).aggregate(count=Count("pk"), bytes=Sum("size"))
        unused["images" if kind == "image" else "videos"] = none["count"]
        unused["bytes"] += none["bytes"] or 0
    return {"old_versions": old_only, "old_versions_bytes": sum(item["size"] for item in old_only), "unused": unused}


@api_view(["GET"])
@permission_classes([CanReadLibrary])
def broken_links(request):
    services.require_editor(request.user)
    return Response(scan())
