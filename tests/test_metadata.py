from castclipes.metadata.formatting import format_title, merge_tags


def test_title_uppercase_with_small_words():
    assert (
        format_title("fulano de tal reage a vídeo bizarro da beltrana!", style="upper")
        == "FULANO de TAL REAGE a VÍDEO BIZARRO da BELTRANA!"
    )


def test_title_natural_keeps_ai_casing():
    assert format_title("  como o iPhone mudou tudo ") == "Como o iPhone mudou tudo"


def test_title_first_word_always_upper_and_truncates():
    assert format_title("do val reage", style="upper").startswith("DO ")
    assert len(format_title("palavra " * 30, 100)) <= 100


def test_merge_tags_dedupes_and_limits():
    tags = merge_tags(["MBL", "renan santos"], ["#mbl", "Nikolas Ferreira", ""])
    assert tags == ("mbl", "renan santos", "nikolas ferreira")
    many = merge_tags([], [f"tag{i:04d}" * 3 for i in range(200)])
    assert sum(len(t) + 1 for t in many) <= 500
