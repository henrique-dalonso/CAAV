(function () {
    "use strict";

    // Interruptor liga/desliga o motor — visível pra coordenador também
    // (não só admin), por isso fica fora da guarda abaixo (que só cobre
    // o navegador de pastas, admin-only).
    var interruptorMotor = document.getElementById("interruptor-motor");

    if (interruptorMotor) {
        interruptorMotor.addEventListener("change", function () {
            interruptorMotor.closest("form").submit();
        });
    }

    var campoPasta = document.getElementById("pasta_entrada");
    var botaoEscolher = document.getElementById("botao-escolher-pasta");
    var navegador = document.getElementById("navegador-pastas");

    if (!campoPasta || !botaoEscolher || !navegador) {
        return;
    }

    var elementoAtual = document.getElementById("navegador-pastas-atual");
    var elementoLista = document.getElementById("navegador-pastas-lista");
    var botaoUsar = document.getElementById("navegador-pastas-usar");
    var botaoFechar = document.getElementById("navegador-pastas-fechar");

    var caminhoAtual = "";

    function carregar(caminho) {
        var url = "/extratus/motor/pastas" + (caminho ? "?caminho=" + encodeURIComponent(caminho) : "");

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
