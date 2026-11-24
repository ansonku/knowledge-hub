from documents.models import SiteSettings


def site(request):
    """Site name for the Django account pages (editable by Admins, see SiteSettings)."""
    return {"site_name": SiteSettings.current().name}
