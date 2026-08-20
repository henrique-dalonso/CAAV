(function () {
    "use strict";

    // Interruptor liga/desliga o robô — visível pra coordenador também
    // (não só admin), por isso fica fora da guarda abaixo (que só cobre
    // o navegador de pastas, admin-only).
    var interruptorRobo = document.getElementById("interruptor-robo");

    if (interruptorRobo) {
        interruptorRobo.addEventListener("change", function () {
            interruptorRobo.closest("form").submit();
        });
    }

    var campoPasta = document.getElementById("pasta_entrada");
    var botaoEscolher = document.getElementById("botao-escolher-pasta");
    var navegador = document.getElementById("navegador-pastas");

    if (!campoPasta || !botaoEscolher || !navegador) {
        return;
    }

    // Deriva a URL base do módulo (Relatórios usa /extratus/...,
    // Aburesi usa /extratus-aburesi/...) do action do form do
    // interruptor, mesmo truque já usado em fila.js/gerar_relatorio.js —
    // achado ao renomear esse arquivo (Rodada 13, nomenclatura): a
    // cópia aburesi tinha essa URL fixa em "/extratus/..." (bug real,
    // buscava as pastas do módulo ERRADO), agora corrigido na raiz.
    var formInterruptor = document.getElementById("form-interruptor-robo");
    var baseUrl = formInterruptor ? formInterruptor.action.replace(/\/alternar$/, "") : "/extratus/configuracoes-robo";

    var elementoAtual = document.getElementById("navegador-pastas-atual");
    var elementoLista = document.getElementById("navegador-pastas-lista");
    var botaoUsar = document.getElementById("navegador-pastas-usar");
    var botaoFechar = document.getElementById("navegador-pastas-fechar");

    var caminhoAtual = "";

    function carregar(caminho) {
        var url = baseUrl + "/pastas" + (caminho ? "?caminho=" + encodeURIComponent(caminho) : "");

        fetch(url)
            .then(function (resposta) { return resposta.json(); })
            .then(function (dados) {
                caminhoAtual = dados.caminho;
                elementoAtual.textContent = caminhoAtual;
                elementoLista.innerHTML = "";

                if (dados.pai) {
                    var itemPai = document.createElement("button");
                    itemPai.type = "button";
                    itemPai.className = "navegador-pastas-item";
                    itemPai.textContent = ".. (subir um nível)";
                    itemPai.addEventListener("click", function () { carregar(dados.pai); });
                    elementoLista.appendChild(itemPai);
                }

                dados.pastas.forEach(function (nome) {
                    var item = document.createElement("button");
                    item.type = "button";
                    item.className = "navegador-pastas-item";
                    item.textContent = nome;
                    item.addEventListener("click", function () {
                        carregar(caminhoAtual + "\\" + nome);
                    });
                    elementoLista.appendChild(item);
                });
            });
    }

    botaoEscolher.addEventListener("click", function () {
        navegador.hidden = false;
        carregar(campoPasta.value || null);
    });

    botaoFechar.addEventListener("click", function () {
        navegador.hidden = true;
    });

    botaoUsar.addEventListener("click", function () {
        campoPasta.value = caminhoAtual;
        navegador.hidden = true;
    });

    navegador.addEventListener("click", function (evento) {
        if (evento.target === navegador) {
            navegador.hidden = true;
        }
    });
})();
