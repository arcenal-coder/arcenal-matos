import csv
import io
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from .models import Asset, Category, Site, User
from .permissions import assets, manage, require
from .services import audit

HEADERS = ["identifiant", "nom", "categorie", "marque", "modele", "numero_serie", "site",
           "emplacement", "etat", "personne_affectee", "date_achat", "cout_achat",
           "controle_obligatoire", "dernier_controle", "prochain_controle", "periodicite_jours", "champs_personnalises"]


def safe_cell(value):
    value = "" if value is None else str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value


def csv_bytes(rows):
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(HEADERS)
    for row in rows:
        writer.writerow([safe_cell(item) for item in row])
    return output.getvalue().encode("utf-8-sig")


def asset_row(item):
    return [item.code, item.name, item.category.name, item.brand, item.model, item.serial,
            item.site.name, item.location, item.state, item.assigned_to.username if item.assigned_to else "",
            item.purchase_date, item.purchase_cost, "oui" if item.control_required else "non",
            item.last_control, item.next_control, item.interval_days, json.dumps(item.custom_fields, ensure_ascii=False)]


@transaction.atomic
def import_csv(actor, content):
    require(actor, ("admin", "manager"))
    if len(content) > 5 * 1024 * 1024:
        raise ValidationError("Le fichier CSV dépasse 5 Mo.")
    try:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text), delimiter=";")
        if reader.fieldnames != HEADERS:
            raise ValidationError("Les colonnes doivent correspondre exactement au modèle CSV (séparateur point-virgule).")
        parsed = []
        errors = []
        seen = set()
        for number, row in enumerate(reader, start=2):
            if number > 10001:
                raise ValidationError("Un import est limité à 10 000 lignes.")
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("Nombre de colonnes incorrect")
                code = row["identifiant"].strip()
                if code in seen:
                    raise ValueError("Identifiant répété dans le fichier")
                seen.add(code)
                site = Site.objects.get(name=row["site"].strip())
                manage(actor, site.pk)
                category = Category.objects.get(name=row["categorie"].strip())
                user = User.objects.get(username=row["personne_affectee"].strip(), role="member", site=site) if row["personne_affectee"].strip() else None
                boolean = row["controle_obligatoire"].strip().lower()
                if boolean not in ("", "oui", "non"):
                    raise ValueError("controle_obligatoire : oui ou non")
                item = Asset(code=code, name=row["nom"].strip(), category=category, site=site,
                             brand=row["marque"], model=row["modele"], serial=row["numero_serie"],
                             location=row["emplacement"], state=row["etat"] or "available", assigned_to=user,
                             purchase_cost=Decimal(row["cout_achat"].replace(",", ".")) if row["cout_achat"] else None,
                             control_required=boolean == "oui", interval_days=int(row["periodicite_jours"]) if row["periodicite_jours"] else None,
                             custom_fields=json.loads(row["champs_personnalises"] or "{}"))
                for field, column in [("purchase_date", "date_achat"), ("last_control", "dernier_controle"), ("next_control", "prochain_controle")]:
                    setattr(item, field, date.fromisoformat(row[column]) if row[column] else None)
                if not isinstance(item.custom_fields, dict):
                    raise ValueError("Les champs personnalisés doivent être un objet JSON")
                if user and item.blocked:
                    raise ValueError("Un matériel bloqué ne peut être affecté à l'import")
                item.full_clean()
                parsed.append(item)
            except (ValidationError, ValueError, InvalidOperation, Site.DoesNotExist, Category.DoesNotExist, User.DoesNotExist) as exc:
                errors.append(f"Ligne {number} : {exc}")
        if errors:
            raise ValidationError(errors[:50])
        for item in parsed:
            try:
                item.save()
            except IntegrityError as exc:
                raise ValidationError("Un identifiant a été créé pendant l'import ; aucune ligne n'a été ajoutée.") from exc
            audit(actor, "asset.imported", item)
        return len(parsed)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValidationError(f"CSV UTF-8 invalide : {exc}") from exc


def report(actor, kind="csv", site_id=None):
    require(actor, ("admin", "manager", "agent"))
    queryset = assets(actor).order_by("site__name", "code")
    if site_id:
        manage(actor, site_id)
        queryset = queryset.filter(site_id=site_id)
    items = list(queryset)
    if kind == "csv":
        data = csv_bytes(asset_row(item) for item in items)
        mime = "text/csv; charset=utf-8"
    elif kind == "pdf":
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=landscape(A4))
        width, height = landscape(A4)
        y = height - 45

        def header():
            pdf.setFont("Helvetica", 9)
            pdf.drawRightString(width - 35, 18, "Par ARCenal")
            pdf.setFont("Helvetica-Bold", 16)
            pdf.drawString(35, height - 30, "ARCenal Matos · Inventaire et audit")
            pdf.setFont("Helvetica", 9)
            pdf.drawString(35, height - 47, f"{timezone.localdate()} · {len(items)} équipements · {actor}")
            pdf.drawString(35, height - 70, "Identifiant / Nom                         Site                  État                    Contrôle         Affectation")

        header()
        y = height - 90
        for item in items:
            if y < 40:
                pdf.showPage()
                header()
                y = height - 90
            columns = [(35, f"{item.code} · {item.name}"[:45]), (300, item.site.name[:22]),
                       (440, "Bloqué" if item.blocked else item.get_state_display()),
                       (560, str(item.control_due or "—")), (680, str(item.assigned_to or "—")[:23])]
            for x, value in columns:
                pdf.drawString(x, y, value)
            y -= 17
        pdf.save()
        data = buffer.getvalue()
        mime = "application/pdf"
    else:
        raise ValidationError("Format de rapport inconnu")
    audit(actor, "report.generated", details={"format": kind, "count": len(items), "site": site_id})
    return data, mime
