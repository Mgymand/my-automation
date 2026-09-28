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


def test_adult_is_hard_blocked_regardless_of_settings(settings):
    settings.sensitive_media_setting_confirmed = True
    settings.dmm_media_registered = True
    r = compliance.check_post("作品【PR】", None, "https://pics.dmm.co.jp/a.jpg", True, settings, site="FANZA")
    assert not r.ok and r.hard_block and not r.requires_human
    assert any("有料パートナーシップ" in x for x in r.reasons)
    # is_adult=False でも site=FANZA なら保守的にブロック
    r = compliance.check_post("作品【PR】", None, None, False, settings, site="FANZA")
    assert r.hard_block


def test_policy_registry_hard_block():
    from affiliate_bot.policy import x_affiliate_hard_block
    assert x_affiliate_hard_block("FANZA").blocked
    assert x_affiliate_hard_block("DMM.com", genres=["アダルト"]).blocked
    assert not x_affiliate_hard_block("DMM.com", genres=["ドラマ"]).blocked


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
