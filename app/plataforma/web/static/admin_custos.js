(function () {
    "use strict";

    var campoBusca = document.querySelector(".campo-busca-colaborador");
    var itensColaborador = document.querySelectorAll(".colaborador-item");
    var checks = document.querySelectorAll(".colaborador-check");
    var linhasTabela = document.querySelectorAll(".tabela-custos tbody tr");

    if (campoBusca) {
        campoBusca.addEventListener("input", function () {
            var termo = campoBusca.value.trim().toLowerCase();

            itensColaborador.forEach(function (item) {
                var passa = !termo || item.dataset.busca.indexOf(termo) !== -1;
                item.style.display = passa ? "" : "none";
            });
        });
    }

    function aplicarFiltroTabela() {
        var selecionados = Array.prototype.filter
            .call(checks, function (c) { return c.checked; })
            .map(function (c) { return c.value; });

        linhasTabela.forEach(function (linha) {
            var mostrar = selecionados.length === 0 || selecionados.indexOf(linha.dataset.usuarioId) !== -1;
            linha.style.display = mostrar ? "" : "none";
        });
    }

    checks.forEach(function (check) {
        check.addEventListener("change", aplicarFiltroTabela);
    });
})();
