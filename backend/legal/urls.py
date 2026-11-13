from django.urls import re_path

from . import views

urlpatterns = [
    # With or without the slash, so a hand-typed or store-listing link works either way.
    re_path(r"^privacy/?$", views.privacy, name="legal-privacy"),
    re_path(r"^terms/?$", views.terms, name="legal-terms"),
]
