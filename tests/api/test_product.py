from repairshopr_api.models.product import Product


def test_from_dict_defaults_omitted_list_fields_to_empty_lists() -> None:
    product = Product.from_dict({"id": 1})

    assert product.vendor_ids == []
    assert product.location_quantities == []
    assert product.photos == []


def test_from_dict_list_defaults_are_not_shared_between_products() -> None:
    first = Product.from_dict({"id": 1})
    second = Product.from_dict({"id": 2})

    first.vendor_ids.append(10)
    first.location_quantities.append({"location_id": 20})
    first.photos.append({"url": "https://example.com/photo.jpg"})

    assert second.vendor_ids == []
    assert second.location_quantities == []
    assert second.photos == []
