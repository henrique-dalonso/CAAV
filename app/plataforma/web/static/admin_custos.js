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

    // --- Gráfico de gasto ao longo do tempo (SVG desenhado à mão, sem
    // dependência externa nenhuma — Henrique, diretoria, 2026-08-26). ---
    var elementoDados = document.getElementById("dados-grafico-custos");
    var svg = document.getElementById("grafico-custos");
    var botoesPeriodo = document.querySelectorAll(".grafico-periodo-botao");

    if (elementoDados && svg) {
        var dados = JSON.parse(elementoDados.textContent || "{}");
        var series = dados.series || {};
        var cotacao = dados.cotacao || 1;

        var NS = "http://www.w3.org/2000/svg";
        var LARGURA = 800;
        var ALTURA = 220;
        var MARGEM_INFERIOR = 26;
        var MARGEM_SUPERIOR = 12;

        function formatarReais(valor) {
            return "R$ " + valor.toFixed(2).replace(".", ",");
        }

        function renderizarGrafico(pontos) {
            svg.setAttribute("viewBox", "0 0 " + LARGURA + " " + ALTURA);
            svg.innerHTML = "";

            if (!pontos.length) {
                return;
            }

            var maiorCusto = Math.max.apply(null, pontos.map(function (p) { return p.custo; }));
            var alturaUtil = ALTURA - MARGEM_INFERIOR - MARGEM_SUPERIOR;
            var larguraBarra = LARGURA / pontos.length;
            var espacamento = larguraBarra * 0.25;

            // Mostra rótulo embaixo de toda barra se couber (poucos
            // pontos); senão, só a cada N barras, pra não empilhar texto
            // ilegível quando há 30 pontos (30 dias) na mesma largura.
            var passoRotulo = pontos.length <= 15 ? 1 : Math.ceil(pontos.length / 10);

            pontos.forEach(function (ponto, indice) {
                var alturaBarra = maiorCusto > 0 ? (ponto.custo / maiorCusto) * alturaUtil : 0;
                var x = indice * larguraBarra + espacamento / 2;
                var y = ALTURA - MARGEM_INFERIOR - alturaBarra;
                var largura = larguraBarra - espacamento;

                var barra = document.createElementNS(NS, "rect");
                barra.setAttribute("x", x);
                barra.setAttribute("y", y);
                barra.setAttribute("width", Math.max(largura, 1));
                barra.setAttribute("height", Math.max(alturaBarra, 1));
                barra.setAttribute("rx", 2);
                barra.setAttribute("class", "grafico-custos-barra");

                var titulo = document.createElementNS(NS, "title");
                titulo.textContent = ponto.rotulo + ": " + formatarReais(ponto.custo * cotacao);
                barra.appendChild(titulo);

                svg.appendChild(barra);

                if (indice % passoRotulo === 0) {
                    var rotulo = document.createElementNS(NS, "text");
                    rotulo.setAttribute("x", x + largura / 2);
                    rotulo.setAttribute("y", ALTURA - 6);
                    rotulo.setAttribute("text-anchor", "middle");
                    rotulo.setAttribute("class", "grafico-custos-rotulo");
                    rotulo.textContent = ponto.rotulo;
                    svg.appendChild(rotulo);
                }
            });
        }

        botoesPeriodo.forEach(function (botao) {
            botao.addEventListener("click", function () {
                botoesPeriodo.forEach(function (b) { b.classList.remove("ativo"); });
                botao.classList.add("ativo");
                renderizarGrafico(series[botao.dataset.periodo] || []);
            });
        });

        var botaoInicial = document.querySelector(".grafico-periodo-botao.ativo") || botoesPeriodo[0];
        if (botaoInicial) {
            renderizarGrafico(series[botaoInicial.dataset.periodo] || []);
        }
    }
})();
