(function () {
    "use strict";

    // Mesma máscara de nº de processo (CNJ) que o Extratus já usa em
    // gerar_relatorio.js — reescrita aqui (não importada) porque cada
    // ferramenta carrega seu próprio JS, sem um arquivo compartilhado
    // entre elas ainda.
    function formatarProcessoCNJ(valorBruto) {
        var digitos = valorBruto.replace(/\D/g, "").slice(0, 20);
        var partes = [
            digitos.slice(0, 7),
            digitos.slice(7, 9),
            digitos.slice(9, 13),
            digitos.slice(13, 14),
            digitos.slice(14, 16),
            digitos.slice(16, 20),
        ];
        var separadores = ["", "-", ".", ".", ".", "."];
        var formatado = "";
        for (var i = 0; i < partes.length; i++) {
            if (!partes[i]) { break; }
            formatado += separadores[i] + partes[i];
        }
        return formatado;
    }

    function mostrarErro(campo, mensagem) {
        campo.classList.remove("campo-invalido");
        void campo.offsetWidth; // força reflow — reinicia a animação mesmo se já estava marcado
        campo.classList.add("campo-invalido");

        var proximo = campo.nextElementSibling;
        if (!proximo || !proximo.classList.contains("erro-campo-mensagem")) {
            proximo = document.createElement("span");
            proximo.className = "erro-campo-mensagem";
            campo.insertAdjacentElement("afterend", proximo);
        }
        proximo.textContent = mensagem;
    }

    function limparErro(campo) {
        campo.classList.remove("campo-invalido");
        var proximo = campo.nextElementSibling;
        if (proximo && proximo.classList.contains("erro-campo-mensagem")) {
            proximo.remove();
        }
    }

    document.addEventListener("input", function (evento) {
        var alvo = evento.target;

        if (alvo.matches && alvo.matches("#processo")) {
            alvo.value = formatarProcessoCNJ(alvo.value);
        }

        if (alvo.classList && alvo.classList.contains("campo-invalido") && alvo.value.trim()) {
            limparErro(alvo);
        }
    });

    document.addEventListener("submit", function (evento) {
        var form = evento.target;
        if (!form.matches || !form.matches(".form-crivus")) { return; }

        var primeiroInvalido = null;

        form.querySelectorAll("[required]").forEach(function (campo) {
            if (!campo.value || !campo.value.trim()) {
                mostrarErro(campo, "Preencha este campo.");
                if (!primeiroInvalido) { primeiroInvalido = campo; }
            } else {
                limparErro(campo);
            }
        });

        if (primeiroInvalido) {
            evento.preventDefault();
            primeiroInvalido.focus();
        }
    });

    // Anexos (home.html) — Henrique, 2026-09-04: "só dá pra selecionar
    // mais de 1 se for tudo junto de uma vez, se eu adiciono um, envio,
    // clico pra adicionar outro, ele substitui". <input type=file
    // multiple> sempre substitui a cada abertura do seletor — pra
    // ACUMULAR entre aberturas diferentes, precisa guardar a lista à
    // parte e reconstruir input.files via DataTransfer a cada mudança
    // (truque padrão pra "adicionar" a um file input).
    var ARQUIVOS_ACUMULADOS = [];

    function renderizarAnexos(dropzone) {
        var vazio = dropzone.querySelector(".dropzone-crivus-vazio");
        var chips = dropzone.querySelector(".dropzone-crivus-chips");

        chips.innerHTML = "";

        if (!ARQUIVOS_ACUMULADOS.length) {
            vazio.hidden = false;
            chips.hidden = true;
            return;
        }

        vazio.hidden = true;
        chips.hidden = false;

        // Mostra até 3 arquivos lado a lado; o resto (só acontece pra
        // coordenador/admin, sem limite fixo) vira "+N", mesmo padrão
        // já usado no Extratus pra excesso de itens.
        var LIMITE_VISUAL = 3;
        var visiveis = ARQUIVOS_ACUMULADOS.slice(0, LIMITE_VISUAL);
        var resto = ARQUIVOS_ACUMULADOS.length - visiveis.length;

        visiveis.forEach(function (arquivo) {
            var chip = document.createElement("span");
            chip.className = "anexo-chip";
            chip.textContent = arquivo.name;
            chip.title = arquivo.name;
            chips.appendChild(chip);
        });

        if (resto > 0) {
            var maisChip = document.createElement("span");
            maisChip.className = "anexo-chip anexo-chip-mais";
            maisChip.textContent = "+" + resto;
            chips.appendChild(maisChip);
        }
    }

    function sincronizarInputArquivos(input) {
        var dt = new DataTransfer();
        ARQUIVOS_ACUMULADOS.forEach(function (arquivo) { dt.items.add(arquivo); });
        input.files = dt.files;
    }

    document.addEventListener("change", function (evento) {
        var input = evento.target;
        if (!input.matches || !input.matches("#arquivos")) { return; }

        var dropzone = input.closest(".dropzone-crivus");
        var maximoTexto = dropzone.dataset.maximo;
        var maximo = maximoTexto ? parseInt(maximoTexto, 10) : null;

        Array.from(input.files).forEach(function (novo) {
            var jaEstaNaLista = ARQUIVOS_ACUMULADOS.some(function (existente) {
                return existente.name === novo.name && existente.size === novo.size;
            });
            if (!jaEstaNaLista) {
                ARQUIVOS_ACUMULADOS.push(novo);
            }
        });

        if (maximo && ARQUIVOS_ACUMULADOS.length > maximo) {
            ARQUIVOS_ACUMULADOS = ARQUIVOS_ACUMULADOS.slice(0, maximo);
        }

        sincronizarInputArquivos(input);
        renderizarAnexos(dropzone);
    });

    // Agendamento (detalhe.html) — Henrique, 2026-09-04: exibição só de
    // leitura por padrão; o lápis (canto superior direito, vermelho —
    // "algo delicado") revela tipo/datas editáveis + "Marcar
    // desnecessário". Só troca uma classe — os campos continuam no DOM
    // e são enviados no POST mesmo escondidos, então clicar direto em
    // "Marcar como Pronto" sem nunca abrir o modo edição preserva a
    // sugestão da IA como está.
    document.addEventListener("click", function (evento) {
        var botao = evento.target.closest(".botao-editar-agendamento");
        if (!botao) { return; }

        var item = botao.closest(".item-agendamento");
        if (item) {
            item.classList.toggle("modo-edicao");
        }
    });
})();
