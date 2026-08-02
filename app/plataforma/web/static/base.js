(function () {
    "use strict";

    // Banners de sucesso/erro ("Usuário excluído", etc) ganham um
    // contador de 5s + um "x" pra fechar na hora — em qualquer página,
    // sem precisar mexer nos templates que já geram esses banners.
    document.querySelectorAll(".banner-sucesso, .banner-erro").forEach(function (banner) {
        var acoes = document.createElement("span");
        acoes.className = "banner-acoes";

        var contador = document.createElement("span");
        contador.className = "banner-contador";

        var botaoFechar = document.createElement("button");
        botaoFechar.type = "button";
        botaoFechar.className = "banner-fechar";
        botaoFechar.setAttribute("aria-label", "Fechar mensagem");
        botaoFechar.textContent = "×";

        acoes.appendChild(contador);
        acoes.appendChild(botaoFechar);
        banner.appendChild(acoes);

        var restante = 5;
        contador.textContent = "(" + restante + ")";

        var intervalo = setInterval(function () {
            restante -= 1;

            if (restante <= 0) {
                clearInterval(intervalo);
                banner.remove();
                return;
            }

            contador.textContent = "(" + restante + ")";
        }, 1000);

        botaoFechar.addEventListener("click", function () {
            clearInterval(intervalo);
            banner.remove();
        });
    });

    // Clique em qualquer .truncavel (nome cortado, e-mail cortado, etc)
    // alterna o corte — um listener só cobre a página inteira, incluindo
    // conteúdo que aparece depois (tabela re-renderizada, painel aberto).
    document.addEventListener("click", function (evento) {
        var alvo = evento.target.closest(".truncavel");

        if (alvo) {
            alvo.classList.toggle("expandido");
        }
    });

    // Qualquer <details> do site fecha sozinho ao clicar fora dele —
    // nativamente <details> só fecha clicando de novo no <summary>, o
    // que não combina com o resto dos painéis (bandeja de apps, seletor
    // de ferramentas etc), que já fecham ao clicar fora.
    document.addEventListener("click", function (evento) {
        document.querySelectorAll("details[open]").forEach(function (detalhe) {
            if (!detalhe.contains(evento.target)) {
                detalhe.open = false;
            }
        });
    });

    // Campo "confirmar senha" — valida no navegador (mensagem nativa,
    // sem precisar de um segundo estilo de erro) que bate com "nova
    // senha" antes de deixar enviar. Cobre qualquer form com esses dois
    // campos, não só a tela de admin.
    function validarConfirmacaoSenha(evento) {
        var novaSenha = evento.target.closest("form").querySelector(".campo-nova-senha");
        var confirmarSenha = evento.target.closest("form").querySelector(".campo-confirmar-senha");

        if (!novaSenha || !confirmarSenha) {
            return;
        }

        if (novaSenha.value !== confirmarSenha.value) {
            confirmarSenha.setCustomValidity("As senhas não coincidem.");
        } else {
            confirmarSenha.setCustomValidity("");
        }
    }

    document.querySelectorAll(".campo-nova-senha, .campo-confirmar-senha").forEach(function (campo) {
        campo.addEventListener("input", validarConfirmacaoSenha);
    });

    // form[data-confirm="mensagem"] pede confirmação num modal estilizado
    // antes de mandar de verdade — cobre a página inteira (não só admin),
    // string vazia (ex: linha do próprio usuário logado) não pergunta nada.
    var modalConfirmacao = document.getElementById("modal-confirmacao");

    if (modalConfirmacao) {
        var mensagemConfirmacao = document.getElementById("modal-confirmacao-mensagem");
        var botaoCancelarConfirmacao = document.getElementById("modal-confirmacao-cancelar");
        var botaoConfirmarConfirmacao = document.getElementById("modal-confirmacao-confirmar");
        var formPendente = null;

        function fecharModalConfirmacao() {
            modalConfirmacao.hidden = true;
            formPendente = null;
        }

        document.querySelectorAll("form[data-confirm]").forEach(function (form) {
            form.addEventListener("submit", function (evento) {
                var mensagem = form.dataset.confirm;

                if (!mensagem) {
                    return;
                }

                evento.preventDefault();
                formPendente = form;
                mensagemConfirmacao.textContent = mensagem;
                botaoConfirmarConfirmacao.classList.toggle(
                    "modal-confirmacao-confirmar-perigo",
                    form.dataset.perigo === "true"
                );
                modalConfirmacao.hidden = false;
            });
        });

        botaoCancelarConfirmacao.addEventListener("click", fecharModalConfirmacao);

        botaoConfirmarConfirmacao.addEventListener("click", function () {
            var form = formPendente;
            fecharModalConfirmacao();

            if (form) {
                form.submit();
            }
        });

        modalConfirmacao.addEventListener("click", function (evento) {
            if (evento.target === modalConfirmacao) {
                fecharModalConfirmacao();
            }
        });

        document.addEventListener("keydown", function (evento) {
            if (evento.key === "Escape" && !modalConfirmacao.hidden) {
                fecharModalConfirmacao();
            }
        });
    }

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

    // Favoritos da bandeja de apps — até 3, fixam o app no início da
    // fila. Guardado no localStorage (por navegador, não por conta).
    var CHAVE_FAVORITOS = "extratus_favoritos_apps";
    var MAXIMO_FAVORITOS = 3;
    var bandeja = document.getElementById("bandeja-apps");

    if (bandeja) {
        function lerFavoritos() {
            try {
                var salvos = JSON.parse(localStorage.getItem(CHAVE_FAVORITOS));
                return Array.isArray(salvos) ? salvos : [];
            } catch (erro) {
                return [];
            }
        }

        function salvarFavoritos(lista) {
            localStorage.setItem(CHAVE_FAVORITOS, JSON.stringify(lista));
        }

        function aplicarFavoritos() {
            var favoritos = lerFavoritos();
            var itens = Array.prototype.slice.call(bandeja.querySelectorAll(".bandeja-apps-item"));

            itens.forEach(function (item) {
                var estrela = item.querySelector(".bandeja-apps-favorito");
                var ehFavorito = favoritos.indexOf(item.dataset.slug) !== -1;

                if (estrela) {
                    estrela.classList.toggle("favorito-ativo", ehFavorito);
                }
            });

            // Reordena: favoritos primeiro (na ordem em que foram
            // marcados, mais antigo primeiro), o resto sempre em ordem
            // alfabética — desfavoritar um item devolve ele pro lugar
            // certo em vez de deixar preso onde estava.
            itens.sort(function (a, b) {
                var posA = favoritos.indexOf(a.dataset.slug);
                var posB = favoritos.indexOf(b.dataset.slug);

                if (posA === -1 && posB === -1) {
                    return a.dataset.nome.localeCompare(b.dataset.nome);
                }
                if (posA === -1) {
                    return 1;
                }
                if (posB === -1) {
                    return -1;
                }
                return posA - posB;
            });

            itens.forEach(function (item) { bandeja.appendChild(item); });
        }

        bandeja.querySelectorAll(".bandeja-apps-favorito").forEach(function (estrela) {
            function alternar(evento) {
                evento.preventDefault();
                evento.stopPropagation();

                var slug = estrela.closest(".bandeja-apps-item").dataset.slug;
                var favoritos = lerFavoritos();
                var indice = favoritos.indexOf(slug);

                if (indice !== -1) {
                    favoritos.splice(indice, 1);
                } else if (favoritos.length < MAXIMO_FAVORITOS) {
                    favoritos.push(slug);
                } else {
                    // Já tem 3 — ignora até o usuário desmarcar algum.
                    return;
                }

                salvarFavoritos(favoritos);
                aplicarFavoritos();
            }

            estrela.addEventListener("click", alternar);
            estrela.addEventListener("keydown", function (evento) {
                if (evento.key === "Enter" || evento.key === " ") {
                    alternar(evento);
                }
            });
        });

        aplicarFavoritos();
    }
})();
