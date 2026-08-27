(function () {
    "use strict";

    var campoBusca = document.querySelector(".campo-busca");
    var abas = document.querySelectorAll(".aba-relatorios-robo");
    var itens = document.querySelectorAll(".relatorio-item");
    var avisoVazio = document.querySelector(".filtro-vazio");
    var listaEl = document.getElementById("lista-relatorios-robo");
    var campoDataDe = document.getElementById("filtro-data-de");
    var campoDataAte = document.getElementById("filtro-data-ate");

    if (!campoBusca || !itens.length) {
        return;
    }

    // "Todos" é a aba padrão (Henrique, 2026-08-21, mudou de ideia em
    // relação à decisão de 2026-08-08 abaixo) — mostra do mais antigo
    // pro mais novo (column-reverse no CSS), diferente das outras 3
    // abas (Sucesso, Revisão, Erro — essas continuam mais novo primeiro,
    // "em ordem de grau de fudido").
    var statusAtivo = "todos";

    function aplicarFiltros() {
        var termo = campoBusca.value.trim().toLowerCase();
        var dataDe = campoDataDe ? campoDataDe.value : "";
        var dataAte = campoDataAte ? campoDataAte.value : "";
        var visiveis = 0;

        itens.forEach(function (item) {
            var passaStatus = statusAtivo === "todos" || item.dataset.status === statusAtivo;
            var passaBusca = !termo || item.dataset.busca.indexOf(termo) !== -1;
            // Comparação de string funciona direto porque data-criado-em
            // e o <input type="date"> usam o mesmo formato ISO (AAAA-MM-DD).
            var passaData = (!dataDe || item.dataset.criadoEm >= dataDe)
                && (!dataAte || item.dataset.criadoEm <= dataAte);
            var mostrar = passaStatus && passaBusca && passaData;

            // Mesma pegadinha do [hidden] vs display de autor já
            // resolvida em relatorios_manuais.js — style.display direto
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

    // Henrique, 2026-08-26: o calendário de cada campo se ajusta pelo
    // que já foi escolhido no outro — não faz sentido "Até" permitir uma
    // data antes de "De" (nem o contrário). Quem for preenchido PRIMEIRO
    // vira o limite do outro; limpar o campo remove o limite de novo.
    if (campoDataDe) {
        campoDataDe.addEventListener("change", function () {
            if (campoDataAte) {
                campoDataAte.min = campoDataDe.value || "";
            }
            aplicarFiltros();
        });
    }
    if (campoDataAte) {
        campoDataAte.addEventListener("change", function () {
            if (campoDataDe) {
                campoDataDe.max = campoDataAte.value || "";
            }
            aplicarFiltros();
        });
    }

    abas.forEach(function (aba) {
        aba.addEventListener("click", function () {
            abas.forEach(function (a) { a.classList.remove("aba-relatorios-robo-ativa"); });
            aba.classList.add("aba-relatorios-robo-ativa");
            statusAtivo = aba.dataset.status;

            if (listaEl) {
                listaEl.classList.toggle("lista-relatorios-invertida", statusAtivo === "todos");
            }

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

    // Nome do PDF de origem — ver comentário equivalente em
    // relatorios_manuais.js (Relatórios URGENTES) — mesma lógica.
    document.querySelectorAll(".link-pdf-original").forEach(function (link) {
        link.addEventListener("click", function (evento) {
            evento.stopPropagation();
        });
    });

    // Deep-link do botão "Ir ao relatório" (Conferências manuais,
    // web/routes/gerar_relatorio.py, ?processo=...) — pré-preenche a busca, troca
    // pra aba certa (o item pode estar em Sucesso/Revisão/Erro — mesmo
    // com "Todos" sendo o padrão, um deep-link deve destacar a aba
    // específica do item, não deixar em "Todos") e dá scroll+destaque no
    // item certo.
    var processoInicial = campoBusca.dataset.processoInicial;
    if (processoInicial) {
        var alvoPreCheck = document.querySelector('.relatorio-item[data-processo="' + CSS.escape(processoInicial) + '"]');
        if (alvoPreCheck) {
            var abaCerta = document.querySelector('.aba-relatorios-robo[data-status="' + alvoPreCheck.dataset.status + '"]');
            if (abaCerta) {
                abas.forEach(function (a) { a.classList.remove("aba-relatorios-robo-ativa"); });
                abaCerta.classList.add("aba-relatorios-robo-ativa");
                statusAtivo = alvoPreCheck.dataset.status;
            }
        }
        campoBusca.value = processoInicial;
    }

    // "Todos" é o padrão agora — aplica a inversão de lista já na carga
    // inicial, não só quando alguém clica na aba (mesmo motivo do toggle
    // dentro do listener de clique acima).
    if (listaEl) {
        listaEl.classList.toggle("lista-relatorios-invertida", statusAtivo === "todos");
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
