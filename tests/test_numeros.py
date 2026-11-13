from backend.numeros import find_number_changes

def test_numero_perdido():
    assert find_number_changes("Foram 120 casos em 2020.", "Houve casos em 2020.") == ["perdida: “120”"]

def test_valor_alterado():
    assert find_number_changes("A dose é de 5 mg.", "A dose é de 50 mg.") == [
        "perdida: “5 mg”", "acrescentada: “50 mg”"]

def test_unidade_alterada():
    assert find_number_changes("Mede 5 km.", "Mede 5 m.") == ["alterada: “5 km”"]

def test_formatos_equivalentes():
    assert find_number_changes("1.000 pessoas e 2,5%", "1000 pessoas e 2,5 %") == []

def test_data_alterada():
    assert find_number_changes("Em 12/03/2020 houve.", "Em 12/03/2021 houve.") == [
        "perdida: “12/03/2020”", "acrescentada: “12/03/2021”"]

def test_sem_numeros():
    assert find_number_changes("O céu é azul.", "O céu é azul.") == []
