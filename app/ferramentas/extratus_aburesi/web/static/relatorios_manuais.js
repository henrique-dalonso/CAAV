(function () {
    "use strict";

    var campoBusca = document.querySelector(".campo-busca");
    var chips = document.querySelectorAll(".chip");
    var itens = document.querySelectorAll(".relatorio-item");
    var avisoVazio = document.querySelector(".filtro-vazio");
    var checkMeus = document.getElementById("check-meus-relatorios");

    if (!campoBusca || !itens.length) {
        return;
    }

    var statusAtivo = "todos";

    function aplicarFiltros() {
        var termo = campoBusca.value.trim().toLowerCase();
        var somenteMeus = checkMeus && checkMeus.checked;
        var meuId = checkMeus ? checkMeus.dataset.usuarioId : null;
        var visiveis = 0;

        itens.forEach(function (item) {
            var passaStatus = statusAtivo === "todos" || item.dataset.status === statusAtivo;
            var passaBusca = !termo || item.dataset.busca.indexOf(termo) !== -1;
            var passaMeus = !somenteMeus || item.dataset.usuarioId === meuId;
            var mostrar = passaStatus && passaBusca && passaMeus;

            // Usa style.display em vez do atributo "hidden": .relatorio-item
            // já tem "display: flex" no CSS, e regra de autor com mesma
            // especificidade vence a regra padrão do navegador pra
            // [hidden] — então "hidden" sozinho não escondia nada na prática.
            item.style.display = mostrar ? "" : "none";

            if (mostrar) {
                visiveis += 1;
            }
        });

        if (avisoVazio) {
            // Ver comentário equivalente em app/ferramentas/extratus/web/
            // static/relatorios_manuais.js — mesma lógica.
            avisoVazio.style.display = visiveis === 0 ? "block" : "none";
        }
    }

    campoBusca.addEventListener("input", aplicarFiltros);

    if (checkMeus) {
        checkMeus.addEventListener("change", aplicarFiltros);
    }

    chips.forEach(function (chip) {
        chip.addEventListener("click", function () {
            chips.forEach(function (c) { c.classList.remove("chip-ativo"); });
            chip.classList.add("chip-ativo");
            statusAtivo = chip.dataset.status;
            aplicarFiltros();
        });
    });
    // .truncavel agora é tratado globalmente em base.js.

    // Clicar no nome/meta do relatório baixa, igual ao botão dedicado —
    // não conflita com o toggle de truncamento (base.js), que também
    // dispara no mesmo clique: baixar é Content-Disposition:attachment,
    // não navega a página, então os dois efeitos acontecem juntos sem
    // atrapalhar um ao outro.
    document.querySelectorAll(".relatorio-info-clicavel").forEach(function (bloco) {
        bloco.addEventListener("click", function () {
            window.location = bloco.dataset.download;
        });
    });

    // Ver comentário equivalente em app/ferramentas/extratus/web/static/
    // relatorios_manuais.js — nome do PDF de origem.
    document.querySelectorAll(".link-pdf-original").forEach(function (link) {
        link.addEventListener("click", function (evento) {
            evento.stopPropagation();
        });
    });

    // Ver comentário equivalente em app/ferramentas/extratus/web/static/
    // relatorios_manuais.js — botão "Marcar como revisado".
    document.querySelectorAll(".botao-marcar-revisado").forEach(function (botao) {
        botao.addEventListener("click", function (evento) {
            evento.stopPropagation();
            var jobId = botao.dataset.jobId;
            botao.disabled = true;
            fetch("relatorios-urgentes/" + jobId + "/marcar-notificacao-resolvida", { method: "POST" })
                .then(function (resp) {
                    if (!resp.ok) { throw new Error("falhou"); }
                    botao.remove();
                })
                .catch(function () { botao.disabled = false; });
        });
    });

    // Deep-link do botão "Ir ao relatório" (Conferências manuais,
    // web/routes/gerar_relatorio.py, ?processo=...) — pré-preenche a busca, tira
    // "Solicitados por mim" (o relatório duplicado pode ser de outro
    // usuário) e dá scroll+destaque no item certo.
    var processoInicial = campoBusca.dataset.processoInicial;
    if (processoInicial) {
        campoBusca.value = processoInicial;
        if (checkMeus) {
            checkMeus.checked = false;
        }
    }

    // "Solicitados por mim" vem marcado por padrão no HTML — sem esta
    // chamada, a lista continuaria mostrando todo mundo até o primeiro
    // clique/digitação disparar aplicarFiltros().
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
