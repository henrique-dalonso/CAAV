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
nas duas grades em vez de dar 404.

Derivado de REGISTRO_TELAS (nucleo_relatorios/telas.py) desde a tarefa
Emenda (2026-09-09) — ver docstring de telas.py pro raciocínio completo da
generalização. Crivus continua fora do REGISTRO_TELAS (motor separado),
mas ganhou entrada MANUAL aqui em 2026-09-16 (Henrique, diretoria: "criar
a tela de custos do Crivus também, da mesma forma das outras
ferramentas") — precisa de uma chave pra aparecer no cartão de Custos do
admin (ver app/plataforma/web/routes/admin_custos.py)."""

from app.ferramentas.nucleo_relatorios.telas import REGISTRO_TELAS

CHAVE_POR_SLUG = {
    tela.slug_plataforma: tela.chave_admin for tela in REGISTRO_TELAS.values()
} | {
    # Ferramenta.slug de verdade (seed.py) é "leitor-publicacoes" — a
    # URL do admin usa o nome real da ferramenta, "crivus", mesmo padrão
    # das outras.
    "leitor-publicacoes": "crivus",
}
