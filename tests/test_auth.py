from app.core.auth import gerar_hash_senha, verificar_senha


def test_hash_nao_guarda_senha_em_texto_puro():
    hash_gerado = gerar_hash_senha("minhaSenha123")
    assert "minhaSenha123" not in hash_gerado


def test_verificar_senha_correta():
    hash_gerado = gerar_hash_senha("minhaSenha123")
    assert verificar_senha("minhaSenha123", hash_gerado) is True


def test_verificar_senha_incorreta():
    hash_gerado = gerar_hash_senha("minhaSenha123")
    assert verificar_senha("senhaErrada", hash_gerado) is False


def test_hashes_diferentes_para_mesma_senha():
    # bcrypt usa "salt" aleatório — dois hashes da mesma senha devem ser diferentes,
    # mas os dois têm que continuar validando a senha certa.
    hash1 = gerar_hash_senha("repetida")
    hash2 = gerar_hash_senha("repetida")

    assert hash1 != hash2
    assert verificar_senha("repetida", hash1)
    assert verificar_senha("repetida", hash2)
