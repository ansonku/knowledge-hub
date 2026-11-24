from rest_framework import serializers

from .models import Category, Document, DocumentActivity, Tag, Version


class CategorySerializer(serializers.ModelSerializer):
    document_count = serializers.SerializerMethodField()

    def get_document_count(self, category):
        # Direct, non-trashed documents only; the client sums subtrees.
        return getattr(category, "document_count", 0)

    class Meta:
        model = Category
        fields = ["id", "name", "parent", "description", "color", "document_count"]


class TagLabelSerializer(serializers.ModelSerializer):
    """Tags as they appear on a document: no usage counts."""
    class Meta:
        model = Tag
        fields = ["id", "name"]


class TagSerializer(serializers.ModelSerializer):
    document_count = serializers.SerializerMethodField()

    def get_document_count(self, tag):
        # Non-trashed documents carrying the tag.
        return getattr(tag, "document_count", 0)

    class Meta:
        model = Tag
        fields = ["id", "name", "document_count"]


class VersionSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    restored_from_number = serializers.IntegerField(read_only=True)

    def get_author(self, version):
        user = version.created_by
        return user.display_name or user.username if user else None
    class Meta:
        model = Version
        fields = [
            "id", "number", "filename", "sha256", "size", "note", "created_at", "source", "created_by",
            "author", "restored_from", "restored_from_number",
        ]


class DocumentSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", default=None, read_only=True)
    tags = TagLabelSerializer(many=True, read_only=True)
    current_version = VersionSerializer(read_only=True)

    class Meta:
        model = Document
        fields = ["id", "title", "format", "category", "category_name", "tags", "current_version", "updated_at"]


class DocumentListSerializer(DocumentSerializer):
    is_public = serializers.BooleanField(read_only=True)
    is_favorite = serializers.BooleanField(read_only=True)
    published_version = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta(DocumentSerializer.Meta):
        fields = [*DocumentSerializer.Meta.fields, "is_public", "is_favorite", "published_version"]


class ActivitySerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()
    document = serializers.SerializerMethodField()

    def get_actor(self, item):
        user = item.actor
        return user.display_name or user.username if user else None

    def get_document(self, item):
        return {"id": item.document_id, "title": item.document.title, "format": item.document.format}

    class Meta:
        model = DocumentActivity
        fields = ["id", "action", "actor", "version_number", "detail", "created_at", "document"]


class BulkChange(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=100)
    # "organize": set the collection (when given) and add tags in one step, e.g. for a finished upload batch.
    action = serializers.ChoiceField(["move", "add_tags", "remove_tags", "trash", "organize"])
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), allow_null=True, required=False)
    tags = serializers.PrimaryKeyRelatedField(queryset=Tag.objects.all(), many=True, required=False)

    def validate(self, data):
        if data["action"] == "move" and "category" not in data:
            raise serializers.ValidationError({"category": "請選擇要移動到的集合。"})
        if data["action"] in ("add_tags", "remove_tags") and not data.get("tags"):
            raise serializers.ValidationError({"tags": "請選擇標籤。"})
        if data["action"] == "organize" and "category" not in data and not data.get("tags"):
            raise serializers.ValidationError({"detail": "請選擇集合或標籤。"})
        return data


class DocumentMetadata(serializers.Serializer):
    title = serializers.CharField(max_length=240, required=False)
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), allow_null=True, required=False)
    tags = serializers.PrimaryKeyRelatedField(queryset=Tag.objects.all(), many=True, required=False)


class VersionUpload(serializers.Serializer):
    file = serializers.FileField(max_length=255)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)
    force = serializers.BooleanField(default=False)


class NewUpload(DocumentMetadata, VersionUpload):
    pass


class NewMarkdown(DocumentMetadata):
    """A Markdown document written in the editor rather than uploaded."""
    title = serializers.CharField(max_length=240)


class MarkdownEdit(VersionUpload):
    base_version = serializers.UUIDField()


class DeleteVersion(serializers.Serializer):
    number = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class RestoreVersion(serializers.Serializer):
    base_version = serializers.UUIDField()
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)
