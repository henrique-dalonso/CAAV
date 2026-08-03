(function () {
    "use strict";

    var campoUpload = document.getElementById("campo-pdfs-fila");
    var botaoEnviar = document.getElementById("botao-enviar-fila");

    if (campoUpload && botaoEnviar) {
        campoUpload.addEventListener("change", function () {
            botaoEnviar.disabled = this.files.length === 0;
        });
    }

    var botaoSelecionar = document.getElementById("botao-selecionar-fila");
    var acoes = document.getElementById("fila-acoes-selecao");
    var checkTodos = document.getElementById("check-selecionar-todos-fila");
    var botaoRemover = document.getElementById("botao-remover-selecionados");
    var botaoCancelar = document.getElementById("botao-cancelar-selecao-fila");

    if (!botaoSelecionar || !acoes) {
        return;
    }

    var checkboxes = document.querySelectorAll(".fila-item-checkbox");
    var checks = document.querySelectorAll(".fila-item-check");

    function atualizarBotaoRemover() {
        var algumMarcado = Array.prototype.some.call(checks, function (c) { return c.checked; });
        var todosMarcados = checks.length > 0 && Array.prototype.every.call(checks, function (c) { return c.checked; });

        botaoRemover.disabled = !algumMarcado;
        checkTodos.checked = todosMarcados;
    }

    function entrarModoSelecao() {
        botaoSelecionar.disabled = true;
        acoes.hidden = false;
        checkboxes.forEach(function (c) { c.hidden = false; });
        atualizarBotaoRemover();
    }

    function sairModoSelecao() {
        botaoSelecionar.disabled = false;
        acoes.hidden = true;
        checkboxes.forEach(function (c) { c.hidden = true; });
        checks.forEach(function (c) { c.checked = false; });
        checkTodos.checked = false;
    }

    botaoSelecionar.addEventListener("click", entrarModoSelecao);
    botaoCancelar.addEventListener("click", sairModoSelecao);

    checkTodos.addEventListener("change", function () {
        checks.forEach(function (c) { c.checked = checkTodos.checked; });
        atualizarBotaoRemover();
    });

    checks.forEach(function (c) {
        c.addEventListener("change", atualizarBotaoRemover);
    });
})();
