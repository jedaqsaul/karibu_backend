"""
manage.py seed_data

Seeds the local dev database with realistic demo data:
  - 1 super admin
  - 6 organizers (5 approved, 1 pending — so /admin/approvals has something to show)
  - 8 attendees
  - 10 categories
  - ~24 events spread across every status (draft, pending_approval, published,
    rejected, completed) so every admin/organizer/attendee screen has data
    to render, including edge cases like a rejected event with a reason.

Banner images use picsum.photos, seeded per-event-slug so they're stable
across re-runs. These are stored as the literal remote URL on the
ImageField — Django's storage.url() returns an absolute URL unchanged,
so this works without actually downloading/uploading any files, and
without needing Cloudinary configured in dev.

Usage:
    python manage.py seed_data            # idempotent — safe to re-run
    python manage.py seed_data --flush    # wipe events/categories first
"""

import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import OrganizerProfile, UserRole
from apps.events.models import Category, Event, EventStatus

User = get_user_model()

PASSWORD = "Karibu@2026"


def picsum(seed, w=800, h=600):
    return f"https://picsum.photos/seed/{seed}/{w}/{h}"


CATEGORIES = [
    ("Music", "🎵"), ("Tech", "💻"), ("Sports", "⚽"), ("Comedy", "🎤"),
    ("Arts & Culture", "🎨"), ("Food & Drink", "🍲"), ("Fashion", "👗"),
    ("Business", "💼"), ("Health & Wellness", "🧘"), ("Family", "👨‍👩‍👧"),
]

ORGANIZERS = [
    ("Amina", "Hassan", "amina@liveeventsco.co.ke", "Live Events Co.", True),
    ("Brian", "Otieno", "brian@nairobitechhub.co.ke", "Nairobi Tech Hub", True),
    ("Cynthia", "Wambui", "cynthia@koroga.co.ke", "Koroga Festival", True),
    ("David", "Kimani", "david@comedystorenbo.co.ke", "Comedy Store Nairobi", True),
    ("Faith", "Njeri", "faith@runke.co.ke", "Athletics Kenya Events", True),
    ("George", "Mutiso", "george@popupsupperclub.co.ke", "Pop-Up Supper Club", False),  # pending approval
]

ATTENDEES = [
    ("Grace", "Wanjiku", "grace.wanjiku@example.com"),
    ("Kevin", "Otieno", "kevin.otieno@example.com"),
    ("Sarah", "Mwangi", "sarah.mwangi@example.com"),
    ("James", "Kariuki", "james.kariuki@example.com"),
    ("Linda", "Achieng", "linda.achieng@example.com"),
    ("Peter", "Njoroge", "peter.njoroge@example.com"),
    ("Mercy", "Chebet", "mercy.chebet@example.com"),
    ("Tom", "Mburu", "tom.mburu@example.com"),
]

# (title, category name, city, venue, capacity)
EVENT_SEEDS = [
    ("Nairobi Jazz Festival 2026", "Music", "Nairobi", "Uhuru Gardens", 4000),
    ("Blankets & Wine", "Music", "Nairobi", "Ngong Race Course", 6000),
    ("Tech Summit KE 2026", "Tech", "Nairobi", "KICC", 1500),
    ("Koroga Festival", "Music", "Nairobi", "Carnivore Grounds", 5000),
    ("Nairobi Fashion Week", "Fashion", "Nairobi", "Sarit Expo Centre", 800),
    ("Comedy Night Nairobi", "Comedy", "Nairobi", "The Alchemist Bar", 300),
    ("East Africa Art Exhibition", "Arts & Culture", "Nairobi", "Nairobi National Museum", 500),
    ("Nairobi Food & Wine Festival", "Food & Drink", "Nairobi", "Two Rivers Mall", 2500),
    ("RunNairobi 10K", "Sports", "Nairobi", "Karura Forest", 3000),
    ("Afro Nation Kenya", "Music", "Diani", "Diani Beach Grounds", 8000),
    ("Startup Pitch Night", "Business", "Nairobi", "iHub Nairobi", 250),
    ("Yoga in the Park", "Health & Wellness", "Nairobi", "Karura Forest", 400),
    ("Kids Fun Day Festival", "Family", "Nairobi", "Uhuru Gardens", 1200),
    ("Mombasa Beach Party", "Music", "Mombasa", "Nyali Beach", 3500),
    ("Nairobi Marathon", "Sports", "Nairobi", "Nyayo Stadium", 10000),
    ("Devfest Nairobi", "Tech", "Nairobi", "Strathmore University", 900),
    ("Kisumu Cultural Week", "Arts & Culture", "Kisumu", "Kisumu Social Centre", 1000),
    ("Stand-Up Comedy Showcase", "Comedy", "Nairobi", "Kenya Cultural Centre", 450),
    ("Nakuru Business Expo", "Business", "Nakuru", "Nakuru ASK Showground", 600),
    ("Wellness Retreat Weekend", "Health & Wellness", "Naivasha", "Lake Naivasha Resort", 150),
    ("Street Food Carnival", "Food & Drink", "Nairobi", "Jamhuri Park", 2000),
    ("Nairobi Vintage Fashion Fair", "Fashion", "Nairobi", "The Alchemist Bar", 350),
    ("Family Picnic Day", "Family", "Nairobi", "Karura Forest", 800),
    ("Eldoret Music Festival", "Music", "Eldoret", "Eldoret Sports Club", 2200),
]


class Command(BaseCommand):
    help = "Seed the database with demo categories, organizers, attendees, and events."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush", action="store_true",
            help="Delete existing events and categories before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["flush"]:
            self.stdout.write("Flushing existing events and categories…")
            Event.objects.all().delete()
            Category.objects.all().delete()

        self._seed_super_admin()
        categories = self._seed_categories()
        organizers = self._seed_organizers()
        self._seed_attendees()
        self._seed_events(categories, organizers)

        self.stdout.write(self.style.SUCCESS("\nSeed complete."))
        self.stdout.write(self.style.SUCCESS(f"All seeded accounts use the password: {PASSWORD}"))

    # ------------------------------------------------------------------

    def _seed_super_admin(self):
        if User.objects.filter(role=UserRole.SUPER_ADMIN).exists():
            self.stdout.write("Super admin already exists — skipping.")
            return
        User.objects.create_superuser(
            email="admin@karibu.co.ke",
            password=PASSWORD,
            first_name="Karibu",
            last_name="Admin",
        )
        self.stdout.write(self.style.SUCCESS("Created super admin: admin@karibu.co.ke"))

    def _seed_categories(self):
        categories = {}
        for name, icon in CATEGORIES:
            cat, created = Category.objects.get_or_create(
                name=name, defaults={"slug": slugify(name), "icon": icon},
            )
            categories[name] = cat
            if created:
                self.stdout.write(f"Category: {name}")
        return categories

    def _seed_organizers(self):
        organizers = []
        for first, last, email, org_name, approved in ORGANIZERS:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first, "last_name": last,
                    "role": UserRole.ORGANIZER, "is_approved": approved,
                },
            )
            if created:
                user.set_password(PASSWORD)
                user.save(update_fields=["password"])
                OrganizerProfile.objects.create(
                    user=user,
                    organization_name=org_name,
                    bio=f"{org_name} — bringing unforgettable experiences to Kenya.",
                    website=f"https://{slugify(org_name)}.co.ke",
                    # NOTE: banner_image intentionally left blank — it's a
                    # writable upload field (organizer uploads via the
                    # profile page), unlike Event.banner_image which has a
                    # dedicated read-only banner_url. Seeding it with a raw
                    # picsum link here would render broken without a
                    # larger serializer change.
                )
                self.stdout.write(
                    f"Organizer: {email} "
                    f"({'approved' if approved else 'PENDING approval'})"
                )
            organizers.append(user)
        return organizers

    def _seed_attendees(self):
        for first, last, email in ATTENDEES:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first, "last_name": last,
                    "role": UserRole.ATTENDEE,
                },
            )
            if created:
                user.set_password(PASSWORD)
                user.save(update_fields=["password"])
                self.stdout.write(f"Attendee: {email}")

    def _seed_events(self, categories, organizers):
        # Only approved organizers create events that are visible/published;
        # everyone still gets a mix of statuses for realistic dashboards.
        approved_organizers = [o for o in organizers if o.is_approved] or organizers
        now = timezone.now()
        admin = User.objects.filter(role=UserRole.SUPER_ADMIN).first()

        # Deterministic-ish status distribution across the 24 seed events.
        # NOTE: the Event model has no separate "rejected" status — the
        # AdminEventApprovalView reject action sets status back to DRAFT
        # and populates rejection_reason. "REJECTED_DRAFT" here is just a
        # local marker so this loop knows to also fill in rejection_reason;
        # it's translated to EventStatus.DRAFT below.
        REJECTED_DRAFT = "rejected_draft"
        statuses = (
            [EventStatus.PUBLISHED] * 12
            + [EventStatus.PENDING_APPROVAL] * 4
            + [EventStatus.DRAFT] * 2
            + [REJECTED_DRAFT] * 3
            + [EventStatus.CANCELLED] * 1
            + [EventStatus.COMPLETED] * 2
        )
        random.seed(42)
        random.shuffle(statuses)

        created_count = 0
        for i, (title, cat_name, city, venue, capacity) in enumerate(EVENT_SEEDS):
            slug = slugify(title)
            if Event.objects.filter(slug=slug).exists():
                continue

            seed_status = statuses[i % len(statuses)]
            is_rejected = seed_status == REJECTED_DRAFT
            status = EventStatus.DRAFT if is_rejected else seed_status
            organizer = approved_organizers[i % len(approved_organizers)]

            # Completed events are in the past; everything else is upcoming.
            if status == EventStatus.COMPLETED:
                start = now - timedelta(days=random.randint(10, 90))
            else:
                start = now + timedelta(days=random.randint(3, 120))
            end = start + timedelta(hours=random.choice([2, 3, 4, 6]))

            is_free = random.random() < 0.2
            price = 0 if is_free else random.choice([500, 800, 1200, 1500, 2500, 3500, 5000, 8000])
            sold = random.randint(0, capacity) if status in (
                EventStatus.PUBLISHED, EventStatus.COMPLETED
            ) else 0

            event = Event(
                organizer=organizer,
                title=title,
                slug=slug,
                description=(
                    f"Join us for {title}, happening at {venue} in {city}. "
                    f"An unmissable experience brought to you by "
                    f"{getattr(organizer, 'organizer_profile', None) and organizer.organizer_profile.organization_name or organizer.full_name}."
                ),
                category=categories.get(cat_name),
                tags=f"{slugify(cat_name)},{slugify(city)},karibu",
                venue=venue,
                address=f"{venue}, {city}",
                city=city,
                country="Kenya",
                start_datetime=start,
                end_datetime=end,
                is_free=is_free,
                ticket_price=price,
                total_capacity=capacity,
                tickets_sold=min(sold, capacity),
                banner_image=picsum(slug),
                status=status,
            )

            if is_rejected:
                event.submitted_at = now - timedelta(days=random.randint(3, 10))
                event.rejection_reason = random.choice([
                    "Venue capacity doesn't match ticket allocation — please correct and resubmit.",
                    "Event description is missing required safety information for this venue.",
                    "Banner image does not meet platform content guidelines — please replace and resubmit.",
                ])
            elif status == EventStatus.PENDING_APPROVAL:
                event.submitted_at = now - timedelta(days=random.randint(1, 5))
            elif status == EventStatus.PUBLISHED:
                event.submitted_at = now - timedelta(days=random.randint(5, 20))
                event.approved_by = admin
                event.approved_at = event.submitted_at + timedelta(days=1)
            elif status == EventStatus.CANCELLED:
                event.submitted_at = now - timedelta(days=random.randint(10, 30))
                event.approved_by = admin
                event.approved_at = event.submitted_at + timedelta(days=1)

            event.save()
            created_count += 1
            label = f"{status} (rejected)" if is_rejected else status
            self.stdout.write(f"Event: {title} [{label}]")

        self.stdout.write(self.style.SUCCESS(f"\nCreated {created_count} new events."))
