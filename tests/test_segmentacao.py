from backend.main import split_text_into_segments

def test_abreviacao_d_joao():
    assert split_text_into_segments(
        "Naquele ano, D. João VI criou uma escola. Depois veio outra."
    ) == ["Naquele ano, D. João VI criou uma escola.", "Depois veio outra."]