from affiliate_bot import compliance


def test_disclosure_required(settings):
    r = compliance.check_post("作品名 見どころ", None, None, False, settings)
    assert not r.ok and any("広告表示" in x for x in r.reasons)


def test_ng_words_block(settings):
    r = compliance.check_post("女子高生 が主役の作品【PR】", None, None, False, settings)
    assert not r.ok


def test_media_rights():
    assert compliance.media_rights_ok("https://pics.dmm.co.jp/digital/video/abc/abcpl.jpg")
    assert compliance.media_rights_ok("https://cc3001.dmm.co.jp/litevideo/freepv/a/b.mp4")
    assert not compliance.media_rights_ok("https://example.com/stolen.jpg")
    assert not compliance.media_rights_ok("https://evil.pics.dmm.co.jp.attacker.com/x.jpg")


def test_adult_requires_human_ack(settings):
    settings.adult_on_x_acknowledged = False
    r = compliance.check_post("作品【PR】", None, None, True, settings)
    assert not r.ok and r.requires_human
    settings.adult_on_x_acknowledged = True
    settings.sensitive_media_setting_confirmed = True
    r = compliance.check_post("作品【PR】", None, "https://pics.dmm.co.jp/a.jpg", True, settings)
    assert r.ok


def test_non_adult_ok(settings):
    r = compliance.check_post("作品の紹介です【PR】", None, "https://pics.dmm.com/a.jpg", False, settings)
    assert r.ok and r.risk == 0.0


def test_weighted_len():
    assert compliance.weighted_len("abc") == 3
    assert compliance.weighted_len("あいう") == 6
    assert compliance.weighted_len("https://example.com/very/long/path/that/is/long") == 23


def test_product_allowed():
    assert compliance.product_allowed("普通の作品", ["ドラマ"])[0]
    assert not compliance.product_allowed("盗撮もの", [])[0]
