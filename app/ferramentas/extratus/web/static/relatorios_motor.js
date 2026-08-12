(function () {
    "use strict";

    var campoBusca = document.querySelector(".campo-busca");
    var abas = document.querySelectorAll(".aba-relatorios-motor");
    var itens = document.querySelectorAll(".relatorio-item");
    var avisoVazio = document.querySelector(".filtro-vazio");

    if (!campoBusca || !itens.length) {
        return;
    }

    // Sucesso é a aba padrão de propósito — Henrique, 2026-08-08: "o
    // intuito é o advogado que precisa desses relatorios ja ter em
    // facil acesso", depois Revisão, Erro por último ("em ordem de grau
    // de fudido"). Sem "Todos" aqui — só uma aba por vez, diferente do
    // chip "Todos" da Relatórios manual.
    var statusAtivo = "sucesso";

    function aplicarFiltros() {
        var termo = campoBusca.value.trim().toLowerCase();
        var visiveis = 0;

        itens.forEach(function (item) {
            var passaStatus = item.dataset.status === statusAtivo;
            var passaBusca = !termo || item.dataset.busca.indexOf(termo) !== -1;
            var mostrar = passaStatus && passaBusca;

            // Mesma pegadinha do [hidden] vs display de autor já
            // resolvida em relatorios_prontos.js — style.display direto
            // em vez do atributo.
            item.style.display = mostrar ? "" : "none";

            if (mostrar) {
                visiveis += 1;
            }
        });

        if (avisoVazio) {
            avisoVazio.style.display = visiveis === 0 ? "" : "none";
        }
    }

    campoBusca.addEventListener("input", aplicarFiltros);

    abas.forEach(function (aba) {
        aba.addEventListener("click", function () {
            abas.forEach(function (a) { a.classList.remove("aba-relatorios-motor-ativa"); });
            aba.classList.add("aba-relatorios-motor-ativa");
            statusAtivo = aba.dataset.status;
            aplicarFiltros();
        });
    });

    // Clicar no nome/meta do relatório baixa, igual à Relatórios manual
    // — .truncavel é tratado globalmente em base.js, não conflita.
    document.querySelectorAll(".relatorio-info-clicavel").forEach(function (bloco) {
        bloco.addEventListener("click", function () {
            window.location = bloco.dataset.download;
        });
    });

    // Deep-link do botão "Ir ao relatório" (Conferências manuais,
    // web/routes/inbox.py, ?processo=...) — pré-preenche a busca, troca
    // pra aba certa (o item pode estar em Sucesso/Revisão/Erro, não só
    // na aba padrão "Sucesso") e dá scroll+destaque no item certo.
    var processoInicial = campoBusca.dataset.processoInicial;
    if (processoInicial) {
        var alvoPreCheck = document.querySelector('.relatorio-item[data-processo="' + CSS.escape(processoInicial) + '"]');
        if (alvoPreCheck) {
            var abaCerta = document.querySelector('.aba-relatorios-motor[data-status="' + alvoPreCheck.dataset.status + '"]');
            if (abaCerta) {
                abas.forEach(function (a) { a.classList.remove("aba-relatorios-motor-ativa"); });
                abaCerta.classList.add("aba-relatorios-motor-ativa");
                statusAtivo = alvoPreCheck.dataset.status;
            }
        }
        campoBusca.value = processoInicial;
    }

    aplicarFiltros();

    if (processoInicial) {
        var alvo = document.querySelector('.relatorio-item[data-processo="' + CSS.escape(processoInicial) + '"]');
        if (alvo) {
            alvo.scrollIntoView({ behavior: "smooth", block: "center" });
            alvo.classList.add("relatorio-item-destacado");
            setTimeout(function () { alvo.classList.remove("relatorio-item-destacado"); }, 2400);
        }
    }
})();
