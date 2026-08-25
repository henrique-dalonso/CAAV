"""Registro de qual "chave" pública (usada nas URLs /admin/custos/<chave>
e /admin/ferramentas/<chave>) corresponde a qual Ferramenta.slug interno.

Existe porque Ferramenta.slug está travado por permissões/favoritos já
gravados no banco de usuários reais (não pode mudar, ver seed.py) mas não
bate mais com o nome real da ferramenta ("extratus" pra "Extratus -
Relatórios") — Henrique, diretoria, 2026-08-24: as telas novas do admin
(Custos, Ferramentas/Configurações) usam o nome de verdade na URL, não o
slug antigo.

Só entram aqui ferramentas que JÁ têm alguma tela própria em pelo menos
uma das duas seções — uma ferramenta sem entrada aqui (ex: Leitor de
Publicações, ainda "em construção") aparece com o cartão desabilitado
nas duas grades em vez de dar 404."""

CHAVE_POR_SLUG = {
    "extratus": "extratus-relatorios",
    "extratus-aburesi": "extratus-aburesi",
}
