from jaguar_xiv_missao.analysis.text import count_mentions, normalize
from jaguar_xiv_missao.metadata.formatting import format_title, merge_tags


def test_title_uppercase_with_small_words():
    assert (
        format_title("arthur do val reage a vídeo bizarro da eduarda campopiano!")
        == "ARTHUR do VAL REAGE a VÍDEO BIZARRO da EDUARDA CAMPOPIANO!"
    )


def test_title_first_word_always_upper_and_truncates():
    assert format_title("do val reage").startswith("DO ")
    assert len(format_title("palavra " * 30, 100)) <= 100


def test_merge_tags_dedupes_and_limits():
    tags = merge_tags(["MBL", "renan santos"], ["#mbl", "Nikolas Ferreira", ""])
    assert tags == ("mbl", "renan santos", "nikolas ferreira")
    many = merge_tags([], [f"tag{i:04d}" * 3 for i in range(200)])
    assert sum(len(t) + 1 for t in many) <= 500


def test_mentions_ignore_accents_case_and_partial_words():
    text = "O MISSÃO e o Partido Missao... Renan Santos falou; mblzinho não conta, MBL sim."
    assert normalize("Missão") == "missao"
    assert count_mentions(text, ["missão", "renan santos", "mbl"]) == 4
