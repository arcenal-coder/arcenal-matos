from django.urls import path

from . import views

app_name = "epi"
urlpatterns = [
    path("", views.index, name="index"),
    path("catalogue/", views.catalogue, name="catalogue"),
    path("catalogue/new/", views.reference_edit, name="reference-new"),
    path("catalogue/<int:pk>/", views.reference_edit, name="reference-edit"),
    path("stock/", views.stock, name="stock"),
    path("stock/new/", views.receipt, name="receipt"),
    path("lots/<int:pk>/", views.lot_detail, name="lot"),
    path("lots/<int:pk>/validity/", views.validity_edit, name="lot-validity"),
    path("units/<uuid:pk>/validity/", views.validity_edit, {"individual": True}, name="unit-validity"),
    path("lots/<int:pk>/issue/", views.issue, name="issue"),
    path("lots/<int:pk>/destroy/", views.destroy, name="destroy"),
    path("requests/", views.request_list, name="requests"),
    path("requests/new/", views.request_create, name="request-new"),
    path("requests/<int:pk>/", views.request_detail, name="request"),
    path("requests/<int:pk>/cancel/", views.cancel, name="cancel"),
    path("distributed/", views.distributed, name="distributed"),
    path("mine/", views.distributed, {"mine": True}, name="my-equipment"),
    path("destroyed/", views.destroyed, name="destroyed"),
    path("history/", views.history, name="history"),
    path("validity/", views.proposal_list, name="proposals"),
    path("validity/new/", views.proposal_create, name="proposal-new"),
    path("validity/<uuid:pk>/decision/", views.proposal_decide, name="proposal-decide"),
]
