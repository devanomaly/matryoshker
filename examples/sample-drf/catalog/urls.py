"""URL routing for the catalog app, mounted by the project under ``api/``."""
from django.urls import path
from rest_framework.routers import DefaultRouter

from catalog.views import AuthorViewSet, BookViewSet, HealthView

router = DefaultRouter()
router.register("books", BookViewSet, basename="book")
router.register("authors", AuthorViewSet, basename="author")

urlpatterns = router.urls + [
    path("health/", HealthView.as_view()),
]
