from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health),
    path("talks/", views.talk_list),
    path("talks/<int:issue>/", views.talk_detail),
    path("signups/", views.signup),
    path("signups/remove/", views.signup_remove),
    path("feed/", views.feed_list),
    path("feed/<int:pk>/", views.feed_detail),
    path("ingest/", views.ingest),
    path("signin-sheets/", views.signin_sheet),
    path("otis/kb/", views.otis_kb),
    path("otis/config/", views.otis_config),
    path("weather/", views.weather),
    path("suggestions/", views.suggestion),
    path("episodes/", views.episode_list),
    path("episodes/<int:number>/", views.episode_detail),
]
