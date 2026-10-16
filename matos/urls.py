from django.urls import include, path

urlpatterns = [path("epi/", include("epi.urls")), path("dosimeters/", include("dosimetry.urls")), path("", include("core.urls"))]
