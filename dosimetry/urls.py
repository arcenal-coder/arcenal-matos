from django.urls import path

from . import views

app_name = "dosimetry"
urlpatterns = [
    path("", views.index, name="index"),
    path("badges/", views.badge_list, name="badges"),
    path("mine/", views.badge_list, {"mine": True}, name="mine"),
    path("badges/new/", views.receive, name="receive"),
    path("badges/<uuid:pk>/", views.badge_detail, name="badge"),
    path("badges/<uuid:pk>/<str:operation>/", views.badge_action, name="badge-action"),
    path("configuration/<str:kind>/", views.configuration, name="configuration"),
    path("configuration/<str:kind>/<int:pk>/", views.configuration, name="configuration-edit"),
    path("operations/<str:kind>/", views.operation, name="operation"),
    path("shipments/", views.shipment_list, name="shipments"),
    path("shipments/<int:pk>/", views.shipment_detail, name="shipment"),
    path("history/", views.history, name="history"),
    path("assistance/", views.assistance, name="assistance"),
    path("assistance/<uuid:pk>/decision/", views.assistance_decide, name="assistance-decide"),
]
