from rest_framework import serializers

from .models import Category, Document, Tag, Version


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "parent"]


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name"]


class VersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Version
        fields = ["id", "number", "filename", "sha256", "size", "note", "created_at", "source", "created_by"]


class DocumentSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", default=None, read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    current_version = VersionSerializer(read_only=True)

    class Meta:
        model = Document
        fields = ["id", "title", "format", "category", "category_name", "tags", "current_version", "updated_at"]


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


class MarkdownEdit(VersionUpload):
    base_version = serializers.UUIDField()
