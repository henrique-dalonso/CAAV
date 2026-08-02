(function () {
    "use strict";

    // form[data-confirm] agora é tratado globalmente em base.js (modal
    // estilizado em vez do confirm() cru do navegador).

    // Cada .seletor-ferramentas na página (uma no form de criar usuário,
    // uma por linha da tabela) é independente — funciona igual a bandeja
    // de apps do cabeçalho, só que pode ter várias ao mesmo tempo na tela.
    document.querySelectorAll(".seletor-ferramentas").forEach(function (seletor) {
        var botao = seletor.querySelector(".botao-selecionar-ferramentas, .botao-icone-ferramentas");
        var painel = seletor.querySelector(".painel-ferramentas");
        var botaoMarcarTodas = seletor.querySelector(".botao-marcar-todas");
        var checks = seletor.querySelectorAll(".ferramenta-tile-input");
        var contagem = seletor.querySelector(".seletor-ferramentas-contagem");

        if (!botao || !painel) {
            return;
        }

        function atualizarContagem() {
            if (!contagem) {
                return;
            }

            var marcados = Array.prototype.filter.call(checks, function (c) {
                return c.checked;
            }).length;

            contagem.textContent = marcados;
        }

        function fechar() {
            painel.hidden = true;
            botao.setAttribute("aria-expanded", "false");
        }

        function posicionar() {
            var margem = 8;
            var retanguloBotao = botao.getBoundingClientRect();
            var alturaPainel = painel.offsetHeight;
            var larguraPainel = painel.offsetWidth;

            // Embaixo do botão por padrão; sobe se não couber. Painel é
            // "position:fixed" (relativo à janela, não à tabela), então
            // essas contas usam coordenadas de viewport mesmo.
            var topo = retanguloBotao.bottom + margem;
            if (topo + alturaPainel > window.innerHeight - margem) {
                topo = retanguloBotao.top - alturaPainel - margem;
            }
            if (topo < margem) {
                topo = margem;
            }

            var esquerda = retanguloBotao.left;
            if (esquerda + larguraPainel > window.innerWidth - margem) {
                esquerda = window.innerWidth - larguraPainel - margem;
            }
            if (esquerda < margem) {
                esquerda = margem;
            }

            painel.style.top = topo + "px";
            painel.style.left = esquerda + "px";
        }

        function abrir() {
            document.querySelectorAll(".painel-ferramentas").forEach(function (p) {
                if (p !== painel) {
                    p.hidden = true;
                }
            });
            painel.hidden = false;
            posicionar();
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
            if (!painel.hidden && !seletor.contains(evento.target)) {
                fechar();
            }
        });

        if (botaoMarcarTodas) {
            botaoMarcarTodas.addEventListener("click", function () {
                var todasMarcadas = Array.prototype.every.call(checks, function (c) {
                    return c.checked;
                });

                checks.forEach(function (c) {
                    c.checked = !todasMarcadas;
                });

                atualizarContagem();
            });
        }

        checks.forEach(function (c) {
            c.addEventListener("change", atualizarContagem);
        });

        atualizarContagem();
    });

    document.addEventListener("keydown", function (evento) {
        if (evento.key === "Escape") {
            document.querySelectorAll(".painel-ferramentas").forEach(function (p) {
                p.hidden = true;
            });
        }
    });

    // Form de criar usuário: "Administrador? Sim" esconde cargo +
    // ferramentas (não fazem sentido pra admin, que já tem acesso total).
    var segmentoAdmin = document.getElementById("segmento-admin");
    var blocoCargo = document.getElementById("bloco-cargo-ferramentas");

    if (segmentoAdmin && blocoCargo) {
        var radiosAdmin = segmentoAdmin.querySelectorAll('input[name="eh_admin"]');

        function atualizarBlocoCargo() {
            var selecionado = segmentoAdmin.querySelector('input[name="eh_admin"]:checked');
            var ehAdmin = !!selecionado && selecionado.value === "true";
            blocoCargo.hidden = ehAdmin;

            // "hidden" só esconde visualmente — os checkboxes continuam
            // marcados e seriam enviados no POST mesmo escondidos. Como
            // admin não usa nada disso mesmo (acesso é sempre inerente),
            // desmarca tudo aqui pra não sobrar estado escondido enganoso
            // (o backend também ignora isso quando eh_admin=True, mas os
            // dois lados concordarem evita confusão de quem tá preenchendo).
            if (ehAdmin) {
                blocoCargo.querySelectorAll('input[type="checkbox"]').forEach(function (c) {
                    c.checked = false;
                });
            }
        }

        radiosAdmin.forEach(function (r) {
            r.addEventListener("change", atualizarBlocoCargo);
        });

        atualizarBlocoCargo();

        // Coordenador já sai com tudo marcado (admin só desmarca o que
        // não quiser) — Colaborador volta pra tudo desmarcado. O checkbox
        // "Admin da ferramenta" só faz sentido (e só aparece) pra
        // coordenador — pra colaborador some e é desmarcado.
        var radiosCargo = blocoCargo.querySelectorAll('input[name="cargo"]');
        var checksFerramentas = blocoCargo.querySelectorAll(".ferramenta-tile-input");
        var linhasAdminFerramenta = blocoCargo.querySelectorAll(".ferramenta-tile-admin");

        if (radiosCargo.length && checksFerramentas.length) {
            radiosCargo.forEach(function (r) {
                r.addEventListener("change", function () {
                    var ehCoordenador = r.value === "coordenador" && r.checked;

                    checksFerramentas.forEach(function (c) {
                        c.checked = ehCoordenador;
                    });

                    linhasAdminFerramenta.forEach(function (linha) {
                        linha.hidden = !ehCoordenador;

                        if (!ehCoordenador) {
                            var checkAdmin = linha.querySelector('input[type="checkbox"]');
                            if (checkAdmin) {
                                checkAdmin.checked = false;
                            }
                        }
                    });

                    // Dispara "change" num deles só pra atualizar o
                    // contador do botão (o listener já existe lá em cima).
                    if (checksFerramentas[0]) {
                        checksFerramentas[0].dispatchEvent(new Event("change"));
                    }
                });
            });

            // Estado inicial (colaborador é o padrão marcado) — some com
            // as linhas de admin-de-ferramenta até escolher coordenador.
            linhasAdminFerramenta.forEach(function (linha) {
                linha.hidden = true;
            });
        }
    }
})();
