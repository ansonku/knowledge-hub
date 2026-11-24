from django.db import migrations
from django.db.models import F

# Same order as documents.models.AUTO_COLLECTION_COLORS (kept inline: migrations must not import live code).
COLORS = ("blue", "teal", "green", "amber", "orange", "red", "purple")


def assign_colors(apps, schema_editor):
    """Give every collection without a colour the least used one, in name order."""
    Category = apps.get_model("documents", "Category")
    used = {color: 0 for color in COLORS}
    for color in Category.objects.exclude(color="").values_list("color", flat=True):
        if color in used:
            used[color] += 1
    # Top-level collections first (PostgreSQL sorts NULL last by default), then by name.
    for category in Category.objects.filter(color="").order_by(F("parent_id").asc(nulls_first=True), "name", "id"):
        color = min(COLORS, key=lambda name: (used[name], COLORS.index(name)))
        used[color] += 1
        Category.objects.filter(pk=category.pk).update(color=color)


class Migration(migrations.Migration):
    dependencies = [("documents", "0009_site_settings")]
    operations = [migrations.RunPython(assign_colors, migrations.RunPython.noop)]
