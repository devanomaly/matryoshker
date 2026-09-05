"""Root URL configuration.

Three shapes on purpose, so the fixture exercises the endpoint parser:

* an ``include()`` of the catalog app under ``api/``;
* one directly mounted view (``health/``);
* one documentation route (``docs/``) that a config is expected to filter
  out by name, since it is generated tooling rather than product surface.
"""
from django.urls import include, path

from catalog.views import HealthView


class SchemaView:
    """Placeholder for the generated OpenAPI schema view.

    The real project would use the schema view shipped by the REST
    framework. It is inlined here so the fixture has a ``docs/`` route
    without depending on an installed package.
    """

    @classmethod
    def as_view(cls):
        """Return the view callable Django would mount."""
        return cls

    def get(self, request):
        """Return the machine-readable API schema."""
        return {"openapi": "3.0.0", "paths": {}}


urlpatterns = [
    path("api/", include("catalog.urls")),
    path("health/", HealthView.as_view()),
    path("docs/", SchemaView.as_view()),
]
