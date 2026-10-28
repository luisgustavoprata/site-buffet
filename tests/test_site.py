import io

from PIL import Image as PILImage

from tests.conftest import png_bytes


def test_site_has_default_content(client):
    body = client.get("/site").json()
    assert body["business_name"]
    assert "Casamento" in body["event_types"]
    assert body["bio_photos"] == []


def test_owner_edits_texts(client, owner):
    response = client.patch(
        "/admin/site",
        json={"business_name": "Buffet Sálvia", "bio": "Minha história.", "instagram": "@salvia"},
        headers=owner,
    )
    assert response.status_code == 200, response.json()
    site = client.get("/site").json()
    assert site["business_name"] == "Buffet Sálvia"
    assert site["bio"] == "Minha história."
    assert site["instagram"] == "salvia"


def test_only_the_owner_edits_the_site(client, ana):
    assert client.patch("/admin/site", json={"bio": "x"}, headers=ana).status_code == 403
    assert client.patch("/admin/site", json={"bio": "x"}).status_code == 401
    assert client.post("/admin/images", files={"file": ("a.png", png_bytes())}).status_code == 401


def test_upload_is_reencoded_and_shrunk(api, client, owner):
    big = png_bytes(size=(3000, 1500))
    response = api.upload(owner, big)
    assert response.status_code == 201, response.json()
    body = response.json()
    assert (body["width"], body["height"]) == (1920, 960)
    assert body["content_type"] == "image/jpeg"
    media = client.get(f"/media/{body['id']}")
    assert media.status_code == 200
    assert media.headers["content-type"] == "image/jpeg"
    assert "immutable" in media.headers["cache-control"]
    assert PILImage.open(io.BytesIO(media.content)).format == "JPEG"


def test_transparent_png_keeps_transparency(api, owner):
    response = api.upload(owner, png_bytes(mode="RGBA", color=(0, 0, 0, 0)))
    assert response.json()["content_type"] == "image/webp"


def test_exif_gps_is_removed(api, client, owner):
    exif = PILImage.Exif()
    exif[0x8825] = {1: "S", 2: (23.0, 0.0, 0.0)}  # GPSInfo
    exif[0x010F] = "Celular da Helena"  # fabricante
    jpeg = png_bytes(fmt="JPEG", exif=exif.tobytes())
    image_id = api.upload(owner, jpeg, "f.jpg", "image/jpeg").json()["id"]
    stored = PILImage.open(io.BytesIO(client.get(f"/media/{image_id}").content))
    assert not stored.getexif()


def test_fake_image_is_rejected(api, owner):
    response = api.upload(owner, b"<script>alert(1)</script>", "foto.jpg", "image/jpeg")
    assert response.status_code == 422
    assert "JPG, PNG ou WebP" in response.json()["detail"]


def test_gif_is_rejected(api, owner):
    response = api.upload(owner, png_bytes(fmt="GIF"), "a.gif", "image/gif")
    assert response.status_code == 422


def test_upload_size_limit(api, owner):
    response = api.upload(owner, b"0" * (1024 * 1024 + 10))
    assert response.status_code == 413


def test_set_cover_and_old_photo_is_deleted(api, client, owner):
    first, second = api.image(owner), api.image(owner)
    client.patch("/admin/site", json={"hero_image_id": first}, headers=owner)
    client.patch("/admin/site", json={"hero_image_id": second}, headers=owner)
    assert client.get("/site").json()["hero_image_id"] == second
    assert client.get(f"/media/{first}").status_code == 404


def test_cannot_use_a_missing_photo(client, owner):
    response = client.patch("/admin/site", json={"owner_image_id": 999}, headers=owner)
    assert response.status_code == 422


def test_bio_photos(api, client, owner):
    one, two = api.image(owner), api.image(owner)
    client.post(
        "/admin/site/bio-photos", json={"image_id": one, "caption": "Na cozinha"}, headers=owner
    )
    site = client.post("/admin/site/bio-photos", json={"image_id": two}, headers=owner).json()
    assert [p["image_id"] for p in site["bio_photos"]] == [one, two]
    photo_id = site["bio_photos"][0]["id"]
    site = client.delete(f"/admin/site/bio-photos/{photo_id}", headers=owner).json()
    assert [p["image_id"] for p in site["bio_photos"]] == [two]
    assert client.get(f"/media/{one}").status_code == 404
    assert client.delete(f"/admin/site/bio-photos/{photo_id}", headers=owner).status_code == 404
