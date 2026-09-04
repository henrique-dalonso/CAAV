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
})();
