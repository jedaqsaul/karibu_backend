"""
shared/utils/media.py

Helper for resolving a FileField/ImageField value to a URL.

Normally `field.url` is correct — but Django's FileSystemStorage runs the
stored name through `filepath_to_uri()`, which percent-encodes characters
like ':' and '//'. That's fine for real uploaded filenames, but it mangles
values that are already absolute URLs (e.g. seed data / dev fixtures that
point straight at https://picsum.photos/... instead of an uploaded file).

Use this anywhere a serializer exposes a banner/avatar/image URL so both
cases work correctly.
"""


def resolve_media_url(field):
    """
    field: a Django FileField/ImageField instance (e.g. obj.banner_image).
    Returns None if empty, the raw value if it's already an absolute URL,
    or field.url otherwise (normal uploaded-file / Cloudinary behaviour).
    """
    if not field:
        return None

    name = str(field)
    if name.startswith("http://") or name.startswith("https://"):
        return name

    return field.url
