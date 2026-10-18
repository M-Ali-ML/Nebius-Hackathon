from nemotron_challenge.plates import _json_reply, image_data_url, is_plate, plate_caption


def _rec(*classes):
    return {"blocks": [{"order": i, "cls": c, "bbox": [0, 0, 1, 1], "text": f"t{i}"} for i, c in enumerate(classes)]}


def test_is_plate_allows_captions_but_not_body_text():
    assert is_plate(_rec("Page-header", "Picture", "Caption"))
    assert not is_plate(_rec("Picture", "Text"))
    assert not is_plate(_rec("Page-header"))


def test_plate_caption_keeps_printed_plate_text():
    assert plate_caption(_rec("Page-header", "Picture", "Text")) == "t0 | t1"


def test_json_reply_strips_code_fence():
    assert _json_reply('```json\n{"subject": "Optics"}\n```') == {"subject": "Optics"}


def test_image_data_url_downscales(tmp_path):
    import base64, io
    from PIL import Image
    path = tmp_path / "big.png"
    Image.new("RGB", (5000, 3000), "white").save(path)
    url = image_data_url(path, max_side=1000)
    with Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))) as image:
        assert max(image.size) == 1000
