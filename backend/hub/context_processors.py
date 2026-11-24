from documents.models import SiteSettings


def site(request):
    """Site name and the active announcement (P6c) for the Django account pages."""
    current = SiteSettings.current()
    return {"site_name": current.name, "site_notice": current.active_notice()}
