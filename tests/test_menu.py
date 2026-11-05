"""Cardápio: o do PDF vem pronto, a dona edita no painel e o site mostra na página inicial."""


def test_menu_from_the_pdf_is_ready(client):
    menu = client.get("/menu").json()
    assert [p["name"] for p in menu["packages"]] == ["Buffet 1", "Buffet 2", "Buffet 3", "Buffet 4"]
    first = menu["packages"][0]
    assert first["prices"][0] == {"label": "Heineken", "value": 240}
    assert first["image"] == "/static/cardapio/buffet-1.jpg"
    assert any(c["name"] == "Moscow Mule" for c in menu["cocktails"])
    assert any(d["title"] == "Risotos" for d in menu["dishes"])
    assert client.get(first["image"]).status_code == 200


def test_owner_edits_and_hides_prices(client, owner):
    menu = client.get("/admin/menu", headers=owner).json()
    menu.pop("updated_at")
    menu["packages"][0]["name"] = "Buffet Premium"
    menu["show_prices"] = False
    saved = client.put("/admin/menu", json=menu, headers=owner)
    assert saved.status_code == 200, saved.json()
    public = client.get("/menu").json()
    assert public["packages"][0]["name"] == "Buffet Premium"
    assert all(p["prices"] == [] for p in public["packages"])  # valores escondidos no site
    admin = client.get("/admin/menu", headers=owner).json()
    assert admin["packages"][0]["prices"]  # mas continuam guardados para a dona


def test_restore_goes_back_to_the_pdf(client, owner):
    menu = client.get("/admin/menu", headers=owner).json()
    menu.pop("updated_at")
    menu["packages"] = menu["packages"][:1]
    client.put("/admin/menu", json=menu, headers=owner)
    assert len(client.get("/menu").json()["packages"]) == 1
    client.post("/admin/menu/restaurar", headers=owner)
    assert len(client.get("/menu").json()["packages"]) == 4


def test_uploaded_package_photo_is_kept(client, api, owner):
    image_id = api.image(owner)
    menu = client.get("/admin/menu", headers=owner).json()
    menu.pop("updated_at")
    menu["packages"][0]["image"] = f"/media/{image_id}"
    assert client.put("/admin/menu", json=menu, headers=owner).status_code == 200
    assert client.get(f"/media/{image_id}").status_code == 200
    menu["packages"][0]["image"] = "/static/cardapio/buffet-1.jpg"  # troca: a enviada é apagada
    client.put("/admin/menu", json=menu, headers=owner)
    assert client.get(f"/media/{image_id}").status_code == 404


def test_only_the_owner_edits(client, ana):
    menu = client.get("/menu").json()
    menu.pop("updated_at")
    assert client.put("/admin/menu", json=menu, headers=ana).status_code == 403
    assert client.put("/admin/menu", json=menu).status_code == 401


def test_rejects_an_outside_photo(client, owner):
    menu = client.get("/admin/menu", headers=owner).json()
    menu.pop("updated_at")
    menu["packages"][0]["image"] = "https://exemplo.com/foto.jpg"
    response = client.put("/admin/menu", json=menu, headers=owner)
    assert response.status_code == 422
