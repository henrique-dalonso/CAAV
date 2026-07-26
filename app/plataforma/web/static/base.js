(function () {
    "use strict";

    var alternadores = [];

    function configurarAlternador(idBotao, idPainel) {
        var botao = document.getElementById(idBotao);
        var painel = document.getElementById(idPainel);

        if (!botao || !painel) {
            return;
        }

        function fechar() {
            painel.hidden = true;
            painel.classList.remove("expandido");
            botao.setAttribute("aria-expanded", "false");
        }

        function abrir() {
            // Só um painel aberto por vez — abrir o seletor de apps fecha
            // o card de perfil, e vice-versa.
            alternadores.forEach(function (a) {
                if (a.fechar !== fechar) {
                    a.fechar();
                }
            });
            painel.hidden = false;
            botao.setAttribute("aria-expanded", "true");
        }

        botao.addEventListener("click", function (evento) {
            evento.stopPropagation();

            if (painel.hidden) {
                abrir();
            } else {
                fechar();
            }
        });

        document.addEventListener("click", function (evento) {
            if (!painel.hidden && !painel.contains(evento.target) && !botao.contains(evento.target)) {
                fechar();
            }
        });

        alternadores.push({ fechar: fechar });
    }

    configurarAlternador("botao-apps", "bandeja-apps");
    configurarAlternador("botao-perfil", "card-perfil");

    var emailPerfil = document.querySelector(".card-perfil-email");

    if (emailPerfil) {
        emailPerfil.addEventListener("click", function () {
            emailPerfil.closest(".card-perfil").classList.toggle("expandido");
        });
    }

    document.addEventListener("keydown", function (evento) {
        if (evento.key === "Escape") {
            alternadores.forEach(function (a) { a.fechar(); });
        }
    });
})();
