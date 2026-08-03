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
            avisoVazio.style.display = visiveis === 0 ? "" : "none";
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
})();
