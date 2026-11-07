from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health),
    path("talks/", views.talk_list),
    path("talks/<int:issue>/", views.talk_detail),
    path("signups/", views.signup),
    path("feed/", views.feed_list),
    path("feed/<int:pk>/", views.feed_detail),
    path("ingest/", views.ingest),
    path("signin-sheets/", views.signin_sheet),
]
