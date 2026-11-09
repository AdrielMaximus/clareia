from backend.ressalvas import find_lost_caveats


def test_perdeu_pode_e_integralmente():
    r = find_lost_caveats(
        "A tecnologia pode ser integralmente substituída",
        "A tecnologia é substituída",
    )
    assert set(r) == {"pode", "integralmente"}


def test_so_integralmente():
    r = find_lost_caveats(
        "A tecnologia pode ser integralmente substituída",
        "A tecnologia pode ser substituída",
    )
    assert r == ["integralmente"]


def test_palavra_nos_dois_textos():
    assert find_lost_caveats("Isso depende do caso.", "Isso depende do caso.") == []


def test_maiusculas_e_acentos():
    assert find_lost_caveats("GERALMENTE funciona.", "Funciona.") == ["geralmente"]


def test_palavra_dentro_de_outra():
    assert find_lost_caveats("Podemos concluir que sim.", "Concluímos que sim.") == []
    assert find_lost_caveats("Um sistema poderoso.", "Um sistema forte.") == []


def test_sem_palavras_da_lista():
    assert find_lost_caveats("O céu é azul.", "O céu é azul.") == []


if __name__ == "__main__":
    testes = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for teste in testes:
        teste()
        print("ok", teste.__name__)
    print(f"{len(testes)} testes passaram")