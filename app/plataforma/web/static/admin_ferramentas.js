(function () {
    "use strict";

    var interruptorRobo = document.getElementById("interruptor-robo");

    if (interruptorRobo) {
        interruptorRobo.addEventListener("change", function () {
            interruptorRobo.closest("form").submit();
        });
    }

    // Zona de soltar do prompt (2026-08-25) — versão simples, 1 arquivo
    // só, do mesmo componente visual .zona-soltar usado na Fila do Robô
    // (fila.js, bem mais elaborado por lidar com vários arquivos ao
    // mesmo tempo). Aqui só troca o texto pelo nome do arquivo
    // escolhido/solto e aceita arrastar-e-soltar de verdade (via
    // DataTransfer, pra funcionar com o <form> nativo no submit).
    var zonaPrompt = document.getElementById("zona-soltar-prompt");
    var campoPrompt = document.getElementById("arquivo-prompt");
    var textoZonaPrompt = document.getElementById("zona-soltar-prompt-texto");

    if (zonaPrompt && campoPrompt && textoZonaPrompt) {
        var textoPadraoPrompt = textoZonaPrompt.textContent;

        var atualizarTextoPrompt = function () {
            textoZonaPrompt.textContent = (campoPrompt.files && campoPrompt.files.length)
                ? campoPrompt.files[0].name
                : textoPadraoPrompt;
        };

        campoPrompt.addEventListener("change", atualizarTextoPrompt);

        ["dragenter", "dragover"].forEach(function (evento) {
            zonaPrompt.addEventListener(evento, function (e) {
                e.preventDefault();
                zonaPrompt.classList.add("arrastando");
            });
        });

        ["dragleave", "drop"].forEach(function (evento) {
            zonaPrompt.addEventListener(evento, function (e) {
                e.preventDefault();
                zonaPrompt.classList.remove("arrastando");
            });
        });

        zonaPrompt.addEventListener("drop", function (e) {
            if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
                campoPrompt.files = e.dataTransfer.files;
                atualizarTextoPrompt();
            }
        });
    }

    var campoPasta = document.getElementById("pasta_entrada");
    var botaoEscolher = document.getElementById("botao-escolher-pasta");
    var navegador = document.getElementById("navegador-pastas");

    if (!campoPasta || !botaoEscolher || !navegador) {
        return;
    }

    // Deriva a URL base da ferramenta (/admin/ferramentas/extratus-relatorios,
    // /admin/ferramentas/extratus-aburesi, ...) do action do form do
    // interruptor — mesmo truque já usado em fila.js/gerar_relatorio.js,
    // reaproveitado aqui quando essa tela saiu de dentro de cada
    // ferramenta e virou parte do admin (2026-08-24).
    var formInterruptor = document.getElementById("form-interruptor-robo");
    var baseUrl = formInterruptor ? formInterruptor.action.replace(/\/alternar$/, "") : "/admin/ferramentas";

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
