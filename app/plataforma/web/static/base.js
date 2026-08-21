(function () {
    "use strict";

    // Capturado logo no topo, síncrono — document.currentScript só é
    // confiável durante a execução inicial do próprio script (mesmo
    // "deferred", esse trecho todo roda de um tirão só quando dispara).
    // Usado mais abaixo pro cache-busting do SharedWorker do sininho.
    var VERSAO_ESTATICOS = (document.currentScript && document.currentScript.dataset.versaoEstaticos) || "";

    // ---------------------------------------------------------------
    // Dica (tooltip) estilizada, sitewide — qualquer elemento com
    // data-dica="texto" ganha isso automaticamente (ver base.css,
    // .dica-flutuante). Delegação de evento no document (mouseover/
    // mouseout, focusin/focusout pra quem navega por teclado) — cobre
    // elemento que já existe na página E qualquer um que apareça depois
    // via JS (fila.js, notificações), sem precisar religar nada.
    //
    // Um único elemento, position:fixed, reaproveitado pra tudo —
    // reposicionado via getBoundingClientRect() a cada hover. Escolhido
    // no lugar do ::after puro CSS que existia antes porque um
    // position:absolute ancorado no próprio elemento é cortado por
    // qualquer ancestral com overflow:auto/hidden (as colunas da Fila
    // do Robô, as tabelas com .tabela-scroll — boa parte do site).
    // ---------------------------------------------------------------
    var ATRASO_DICA_MS = 350;

    var dicaEl = document.createElement("div");
    dicaEl.className = "dica-flutuante";
    dicaEl.setAttribute("role", "tooltip");
    document.body.appendChild(dicaEl);

    var temporizadorDica = null;

    function posicionarDica(alvo) {
        var caixaAlvo = alvo.getBoundingClientRect();
        var caixaDica = dicaEl.getBoundingClientRect();

        var esquerda = caixaAlvo.left + caixaAlvo.width / 2 - caixaDica.width / 2;
        esquerda = Math.max(8, Math.min(esquerda, window.innerWidth - caixaDica.width - 8));

        var topo = caixaAlvo.top - caixaDica.height - 8;
        if (topo < 8) {
            // Sem espaço acima (elemento perto do topo da janela) — mostra
            // embaixo em vez de deixar cortado/invisível.
            topo = caixaAlvo.bottom + 8;
        }

        dicaEl.style.left = esquerda + "px";
        dicaEl.style.top = topo + "px";
    }

    function mostrarDica(alvo) {
        var texto = alvo.getAttribute("data-dica");

        if (!texto) {
            return;
        }

        clearTimeout(temporizadorDica);
        temporizadorDica = setTimeout(function () {
            dicaEl.textContent = texto;
            dicaEl.classList.add("dica-flutuante-visivel");
            posicionarDica(alvo);
        }, ATRASO_DICA_MS);
    }

    function esconderDica() {
        clearTimeout(temporizadorDica);
        dicaEl.classList.remove("dica-flutuante-visivel");
    }

    document.addEventListener("mouseover", function (evento) {
        var alvo = evento.target.closest("[data-dica]");

        if (alvo) {
            mostrarDica(alvo);
        }
    });

    document.addEventListener("mouseout", function (evento) {
        var alvo = evento.target.closest("[data-dica]");

        if (alvo) {
            esconderDica();
        }
    });

    document.addEventListener("focusin", function (evento) {
        var alvo = evento.target.closest("[data-dica]");

        if (alvo) {
            mostrarDica(alvo);
        }
    });

    document.addEventListener("focusout", function (evento) {
        var alvo = evento.target.closest("[data-dica]");

        if (alvo) {
            esconderDica();
        }
    });

    // Banners de sucesso/erro ("Usuário excluído", etc) ganham um
    // contador de 10s + um "x" pra fechar na hora — em qualquer página,
    // sem precisar mexer nos templates que já geram esses banners.
    // decorarBanner faz isso pra um elemento que já existe no HTML
    // (renderizado pelo servidor); window.mostrarBanner (mais abaixo)
    // reaproveita a mesma função pra criar um banner novo, na hora, via
    // JS puro — usado pelo aviso instantâneo de nome duplicado da Fila.
    var DURACAO_BANNER_SEGUNDOS = 10;

    function decorarBanner(banner) {
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
        // Banner simples: "acoes" entra direto nele (linha única, flex).
        // Banner expansível (mostrarBannerDetalhado): tem um wrapper
        // .banner-linha só pro resumo — é ali que "acoes" precisa entrar,
        // não solto no banner inteiro (que agora é "block", não "flex").
        (banner.querySelector(".banner-linha") || banner).appendChild(acoes);

        var restante = DURACAO_BANNER_SEGUNDOS;
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

        function pararContador() {
            clearInterval(intervalo);
            contador.remove();
        }

        botaoFechar.addEventListener("click", function () {
            clearInterval(intervalo);
            banner.remove();
        });

        // Devolvida pra quem criou o banner poder "travar" ele antes do
        // tempo (ex: banner-toast-detalhado, ao ser expandido) — só
        // cancela o sumiço automático, o "x" continua fechando na hora.
        return pararContador;
    }

    document.querySelectorAll(".banner-sucesso, .banner-erro").forEach(decorarBanner);

    // Toast dinâmico — pra avisos que precisam aparecer na hora, sem
    // recarregar a página (ex: "esse documento já foi anexado" na Fila).
    // Flutua no canto da tela (não empurra o conteúdo, diferente do
    // banner de topo de página) mas usa a mesma cara visual
    // (.banner-erro/.banner-sucesso) pra parecer parte do mesmo sistema.
    function obterCaixaToasts() {
        var caixa = document.getElementById("caixa-toasts");

        if (!caixa) {
            caixa = document.createElement("div");
            caixa.id = "caixa-toasts";
            caixa.className = "caixa-toasts";
            document.body.appendChild(caixa);
        }

        return caixa;
    }

    // Henrique, 2026-08-21: popup tinha só 2 cores (verde/vermelho),
    // enquanto a lista do sino já usava 4 (sucesso, triagem/conferência,
    // revisão, erro — ver .item-notificacao-* em base.css) — inconsistente,
    // e causava um sintoma real: sucesso do Robô saindo em vermelho.
    // "sucesso"/"conferencia"/"revisao" reconhecidos explicitamente,
    // qualquer outro valor (inclusive "erro") cai no tom de atenção padrão.
    function classeBannerParaTom(tom) {
        if (tom === "sucesso") { return "banner-sucesso"; }
        if (tom === "conferencia") { return "banner-conferencia"; }
        if (tom === "revisao") { return "banner-revisao"; }
        return "banner-erro";
    }

    window.mostrarBanner = function (mensagem, tipo) {
        var banner = document.createElement("p");
        banner.className = classeBannerParaTom(tipo) + " banner-toast";
        banner.textContent = (tipo === "sucesso" ? "✓ " : "⚠ ") + mensagem;

        obterCaixaToasts().appendChild(banner);
        decorarBanner(banner);
    };

    // Toast com detalhe expansível — pra quando dar vários erros
    // parecidos de uma vez (ex: 5 PDFs recusados na Fila, cada um por
    // um motivo diferente) e uma frase só ("duplicado ou grande demais")
    // fica vaga demais pra ser útil. "itens" é [{ titulo, detalhe }].
    // Clicar no resumo TRAVA o banner (cancela o sumiço automático,
    // só o "x" fecha dali em diante) e revela a lista — é <div>, não
    // <p>, porque precisa caber uma <ul> dentro sem quebrar o HTML.
    window.mostrarBannerDetalhado = function (resumo, itens, tipo) {
        var banner = document.createElement("div");
        banner.className = classeBannerParaTom(tipo) + " banner-toast banner-expansivel";
        banner.setAttribute("role", "alert");

        // .banner-linha segura só o resumo (fica sempre no topo, do
        // jeito que foi mostrado — clicar nele nunca "engorda" essa
        // linha, só revela a lista abaixo). decorarBanner (acima) sabe
        // procurar essa div pra colocar o contador/fechar dentro dela.
        var linha = document.createElement("div");
        linha.className = "banner-linha";

        var texto = document.createElement("span");
        texto.className = "banner-texto";
        texto.textContent = (tipo === "sucesso" ? "✓ " : "⚠ ") + resumo;
        texto.tabIndex = 0;
        linha.appendChild(texto);
        banner.appendChild(linha);

        var lista = document.createElement("ul");
        lista.className = "banner-detalhes";
        lista.hidden = true;

        itens.forEach(function (item) {
            var li = document.createElement("li");

            var nome = document.createElement("span");
            nome.className = "banner-detalhe-nome";
            nome.textContent = '"' + item.titulo + '"';

            var detalhe = document.createElement("span");
            detalhe.className = "banner-detalhe-motivo";
            detalhe.textContent = ': "' + item.detalhe + '"';

            li.appendChild(nome);
            li.appendChild(detalhe);
            lista.appendChild(li);
        });

        banner.appendChild(lista);
        obterCaixaToasts().appendChild(banner);

        var pararContador = decorarBanner(banner);
        var travado = false;

        function alternar() {
            if (!travado) {
                travado = true;
                pararContador();
            }

            lista.hidden = !lista.hidden;
            banner.classList.toggle("banner-expandido", !lista.hidden);
        }

        texto.addEventListener("click", alternar);
        texto.addEventListener("keydown", function (evento) {
            if (evento.key === "Enter" || evento.key === " ") {
                evento.preventDefault();
                alternar();
            }
        });
    };

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
        // Guarda quem tinha o foco antes de abrir (o botão que disparou o
        // submit) — devolvido ao fechar, pra quem navega por teclado não
        // "perder o lugar" na página (Rodada 12, achado de acessibilidade).
        var elementoAnteriorFoco = null;

        function fecharModalConfirmacao() {
            modalConfirmacao.hidden = true;
            formPendente = null;

            if (elementoAnteriorFoco && typeof elementoAnteriorFoco.focus === "function") {
                elementoAnteriorFoco.focus();
            }
            elementoAnteriorFoco = null;
        }

        // Delegado no document (não um listener por form encontrado na
        // hora que a página carrega) — precisa cobrir formulário que
        // aparece DEPOIS, via polling (ex: painel de Conferências da
        // Fila do Robô, 2026-08-07). Um `querySelectorAll` fixo nunca
        // pegaria esses.
        document.addEventListener("submit", function (evento) {
            var form = evento.target;

            if (!form.matches || !form.matches("form[data-confirm]")) {
                return;
            }

            var mensagem = form.dataset.confirm;

            if (!mensagem) {
                return;
            }

            evento.preventDefault();
            formPendente = form;
            elementoAnteriorFoco = document.activeElement;
            mensagemConfirmacao.textContent = mensagem;
            botaoConfirmarConfirmacao.classList.toggle(
                "modal-confirmacao-confirmar-perigo",
                form.dataset.perigo === "true"
            );
            modalConfirmacao.hidden = false;
            botaoCancelarConfirmacao.focus();
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
            if (modalConfirmacao.hidden) {
                return;
            }

            if (evento.key === "Escape") {
                fecharModalConfirmacao();
                return;
            }

            // Foco preso nos 2 botões enquanto o modal está aberto — Tab no
            // último volta pro primeiro, Shift+Tab no primeiro vai pro
            // último, nunca escapa pro resto da página por trás.
            if (evento.key === "Tab") {
                var focaveis = [botaoCancelarConfirmacao, botaoConfirmarConfirmacao];
                var primeiro = focaveis[0];
                var ultimo = focaveis[focaveis.length - 1];

                if (evento.shiftKey && document.activeElement === primeiro) {
                    evento.preventDefault();
                    ultimo.focus();
                } else if (!evento.shiftKey && document.activeElement === ultimo) {
                    evento.preventDefault();
                    primeiro.focus();
                }
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

        // devolverFoco só é true quando o próprio usuário fechou de
        // propósito (clique no botão que abriu, ou Esc) — fechar como
        // efeito colateral de abrir outro painel, ou por clique fora
        // (que já move o foco pra onde a pessoa clicou), NÃO reivindica
        // o foco de volta (Rodada 12, achado de acessibilidade: quem usa
        // teclado perdia a posição na página ao fechar qualquer um
        // desses painéis).
        function fechar(devolverFoco) {
            var estavaAberto = !painel.hidden;

            painel.hidden = true;
            painel.classList.remove("expandido");
            botao.setAttribute("aria-expanded", "false");

            if (devolverFoco && estavaAberto) {
                botao.focus();
            }
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
                fechar(true);
            }
        });

        document.addEventListener("click", function (evento) {
            if (!painel.hidden && !painel.contains(evento.target) && !botao.contains(evento.target)) {
                fechar();
            }
        });

        alternadores.push({ fechar: fechar });
        return fechar;
    }

    // Exposto pra outras páginas montarem seu próprio painel flutuante
    // (ex: o popover "+N" de arquivos da Fila do robô) reaproveitando
    // o mesmo mecanismo (um aberto por vez, fecha fora/Esc) em vez de
    // duplicar a lógica.
    window.configurarAlternador = configurarAlternador;

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
            alternadores.forEach(function (a) { a.fechar(true); });
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

    // ---------------------------------------------------------------
    // Sininho de notificações — pendências da Fila do Robô (triagem +
    // erros) de toda ferramenta que o usuário tem acesso, GET
    // /notificacoes (ver app/plataforma/web/notificacoes.py). Presente em
    // toda página logada (base.html), não só nas ferramentas.
    //
    // Empurrado por SSE (Server-Sent Events, GET /notificacoes/eventos),
    // não mais por polling num timer — Henrique, 2026-08-08: "não dá
    // para deixar certas coisas instantâneas?" O servidor avisa
    // (eventos_sse.py) toda vez que algo muda de verdade (checagem,
    // Job novo, decisão de Conferência), e essa aba busca /notificacoes
    // na hora, sem esperar tick nenhum — inclusive com a aba em segundo
    // plano, já que uma conexão SSE não é pausada do mesmo jeito que um
    // setInterval seria (é isso que permite o som/alerta no título
    // funcionarem mesmo sem a aba estar em foco, mais abaixo).
    // INTERVALO_NOTIFICACOES_MS_RESERVA continua existindo só como rede
    // de segurança bem espaçada — se o SSE cair por algum motivo (proxy
    // bloqueando, navegador antigo sem EventSource), a página nunca
    // fica desatualizada por muito tempo, só menos instantânea.
    // Mesmo cuidado de escopo do bug achado em fila.js (2026-08-06):
    // fica DENTRO desta mesma IIFE de propósito, não em um bloco
    // `(function(){...})()` separado.
    // ---------------------------------------------------------------
    var INTERVALO_NOTIFICACOES_MS_RESERVA = 60000;

    var botaoNotificacoesEl = document.getElementById("botao-notificacoes");
    var painelNotificacoesEl = document.getElementById("painel-notificacoes");
    var fecharNotificacoesEl = document.getElementById("fechar-notificacoes");
    var fundoNotificacoesEl = document.getElementById("notificacoes-fundo");
    var abaSistemaEl = document.getElementById("aba-sistema");
    var abaMinhasEl = document.getElementById("aba-minhas");
    var abaConferenciasEl = document.getElementById("aba-conferencias");
    var listaNotificacoesEl = document.getElementById("lista-notificacoes");
    var listaNotificacoesMinhasEl = document.getElementById("lista-notificacoes-minhas");
    var listaNotificacoesConferenciasEl = document.getElementById("lista-notificacoes-conferencias");
    var painelNotificacoesVazioEl = document.getElementById("painel-notificacoes-vazio");
    var painelNotificacoesVazioMinhasEl = document.getElementById("painel-notificacoes-vazio-minhas");
    var painelNotificacoesVazioConferenciasEl = document.getElementById("painel-notificacoes-vazio-conferencias");
    var badgeNotificacoesEl = document.getElementById("badge-notificacoes");
    var contagemAbaSistemaEl = document.getElementById("contagem-aba-sistema");
    var contagemAbaMinhasEl = document.getElementById("contagem-aba-minhas");
    var contagemAbaConferenciasEl = document.getElementById("contagem-aba-conferencias");

    if (botaoNotificacoesEl && painelNotificacoesEl) {
        var fecharPainelNotificacoes = configurarAlternador("botao-notificacoes", "painel-notificacoes");

        if (fecharNotificacoesEl) {
            fecharNotificacoesEl.addEventListener("click", fecharPainelNotificacoes);
        }

        // O fundo escurecido não é mexido por configurarAlternador (não
        // sabe que ele existe) — um MutationObserver no atributo
        // "hidden" do painel mantém os dois sincronizados não importa
        // COMO o painel fechou (botão de X, clique fora, Esc — todos
        // passam por configurarAlternador, que só mexe em "hidden").
        if (fundoNotificacoesEl) {
            new MutationObserver(function () {
                fundoNotificacoesEl.classList.toggle("notificacoes-fundo-visivel", !painelNotificacoesEl.hidden);
            }).observe(painelNotificacoesEl, { attributes: true, attributeFilter: ["hidden"] });
        }

        // Abas "Sistema"/"Minhas"/"Conferências" — só trocam o que aparece
        // no conteúdo, sem pedir nada novo ao servidor (os dados de todas
        // as abas já vêm juntos numa chamada só a /notificacoes, ver
        // renderizarNotificacoes). "Conferências" só existe no DOM pra
        // quem tem acesso a pelo menos uma fila do robô (gate no próprio
        // base.html, usuario_tem_acesso_a_alguma_fila_robo) — por isso
        // abaConferenciasEl pode ser null aqui, e cada entrada abaixo
        // sabe pular a si mesma nesse caso. "Minhas" (Henrique, 2026-08-13:
        // pendências do fluxo manual, pra quem não tem acesso à Fila do
        // Robô também) reúne conferência/erro/pronto/revisão do próprio
        // usuário — identificados pelo item.pessoal === true vindo do
        // backend (ver item.pessoal em notificacoes_do_usuario).
        var ABAS_NOTIFICACOES = [
            { nome: "sistema", botao: abaSistemaEl, lista: listaNotificacoesEl, vazio: painelNotificacoesVazioEl },
            { nome: "minhas", botao: abaMinhasEl, lista: listaNotificacoesMinhasEl, vazio: painelNotificacoesVazioMinhasEl },
            { nome: "conferencias", botao: abaConferenciasEl, lista: listaNotificacoesConferenciasEl, vazio: painelNotificacoesVazioConferenciasEl },
        ];
        var abaNotificacoesAtiva = "sistema";

        function mostrarAbaNotificacoes(nomeAba) {
            abaNotificacoesAtiva = nomeAba;

            ABAS_NOTIFICACOES.forEach(function (aba) {
                if (!aba.botao) {
                    return;
                }

                var ativa = aba.nome === nomeAba;
                aba.botao.classList.toggle("aba-notificacoes-ativa", ativa);

                if (aba.lista) {
                    aba.lista.hidden = !ativa || aba.lista.children.length === 0;
                }
                if (aba.vazio) {
                    aba.vazio.hidden = !ativa || (aba.lista ? aba.lista.children.length > 0 : false);
                }
            });
        }

        ABAS_NOTIFICACOES.forEach(function (aba) {
            if (aba.botao) {
                aba.botao.addEventListener("click", function () { mostrarAbaNotificacoes(aba.nome); });
            }
        });

        function adicionarBotaoExpandir(linkEl, textoEl) {
            var expandirEl = document.createElement("button");
            expandirEl.type = "button";
            expandirEl.className = "item-notificacao-expandir";
            expandirEl.textContent = "Ver mais";

            expandirEl.addEventListener("click", function (evento) {
                // Impede que o clique também dispare a navegação do <a>
                // que envolve tudo isso.
                evento.preventDefault();
                evento.stopPropagation();

                var expandido = textoEl.classList.toggle("expandido");
                expandirEl.textContent = expandido ? "Ver menos" : "Ver mais";
            });

            linkEl.appendChild(expandirEl);
        }

        // Só oferece "Ver mais" quando o texto realmente estoura as 3
        // linhas do line-clamp — mensagens curtas (a maioria da triagem)
        // nunca precisam disso. Não dá pra medir isso na hora de montar
        // a lista (renderizarNotificacoes roda por trás mesmo com o
        // painel fechado — [hidden] zera scrollHeight/clientHeight dos
        // dois, a comparação nunca bate) — por isso isso roda de novo
        // toda vez que o painel É ABERTO, quando o layout de verdade já
        // existe. Idempotente: pula quem já tem o botão.
        function atualizarBotoesExpandir() {
            var textos = Array.prototype.slice.call(listaNotificacoesEl.querySelectorAll(".item-notificacao-texto"));

            [listaNotificacoesMinhasEl, listaNotificacoesConferenciasEl].forEach(function (lista) {
                if (lista) {
                    textos = textos.concat(Array.prototype.slice.call(lista.querySelectorAll(".item-notificacao-texto")));
                }
            });

            textos.forEach(function (textoEl) {
                var linkEl = textoEl.closest(".item-notificacao");

                if (linkEl.querySelector(".item-notificacao-expandir")) {
                    return;
                }

                if (textoEl.scrollHeight > textoEl.clientHeight + 1) {
                    adicionarBotaoExpandir(linkEl, textoEl);
                }
            });
        }

        botaoNotificacoesEl.addEventListener("click", function () {
            if (!painelNotificacoesEl.hidden) {
                atualizarBotoesExpandir();
            }
        });

        // Detecta quem é genuinamente NOVO entre um poll e outro, pra
        // alertar (som + sino chacoalhando + toast) só quando algo chega
        // de verdade — não a cada poll, e não na primeira carga da
        // página (senão tudo que já existia "alertaria" no F5, o que
        // seria barulho, não aviso). Itens não têm um id estável no
        // payload de /notificacoes — a chave é tipo+link+mensagem, que
        // já é única o bastante na prática (dois arquivos diferentes
        // nunca têm a mesma mensagem).
        var chavesNotificacoesConhecidas = null;

        function chaveNotificacao(item) {
            return item.tipo + "|" + item.link + "|" + item.mensagem;
        }

        function detectarNovasNotificacoes(itens) {
            var chavesAtuais = itens.map(chaveNotificacao);

            if (chavesNotificacoesConhecidas === null) {
                chavesNotificacoesConhecidas = new Set(chavesAtuais);
                return [];
            }

            var novas = itens.filter(function (item) {
                return !chavesNotificacoesConhecidas.has(chaveNotificacao(item));
            });

            chavesNotificacoesConhecidas = new Set(chavesAtuais);
            return novas;
        }

        // Beep curto sintetizado via Web Audio (sem depender de um
        // arquivo de áudio externo). Autoplay do navegador só libera som
        // depois de alguma interação real na página — como o primeiro
        // poll nunca alerta (só estabelece a base, ver
        // detectarNovasNotificacoes), na prática isso já roda bem depois
        // da pessoa ter clicado em algo, então não deveria ser bloqueado.
        // Envolto em try/catch por precaução — sem Web Audio, ou com o
        // navegador recusando por qualquer motivo, o resto do alerta
        // (sino chacoalhando + toast) continua funcionando normal.
        function tocarSomNotificacao() {
            try {
                var Contexto = window.AudioContext || window.webkitAudioContext;
                var contexto = new Contexto();
                var oscilador = contexto.createOscillator();
                var ganho = contexto.createGain();

                oscilador.type = "sine";
                oscilador.frequency.value = 880;
                ganho.gain.setValueAtTime(0.16, contexto.currentTime);
                ganho.gain.exponentialRampToValueAtTime(0.001, contexto.currentTime + 0.35);

                oscilador.connect(ganho);
                ganho.connect(contexto.destination);
                oscilador.start();
                oscilador.stop(contexto.currentTime + 0.35);
            } catch (erro) {
                // Web Audio indisponível/bloqueado — segue sem som.
            }
        }

        // Reinicia a animação mesmo se ela já rodou antes (void
        // offsetWidth força um reflow) — sem isso, chegar uma 2ª
        // notificação nova enquanto a animação da 1ª ainda não passou
        // não reiniciaria a "chacoalhada".
        function chacoalharSino() {
            botaoNotificacoesEl.classList.remove("botao-notificacoes-chacoalhando");
            void botaoNotificacoesEl.offsetWidth;
            botaoNotificacoesEl.classList.add("botao-notificacoes-chacoalhando");
        }

        // Mesmo mapeamento tipo -> cor que .item-notificacao-* já usa na
        // lista do sino (base.css) — replicado aqui pro popup ficar
        // consistente com ela, em vez de só verde/vermelho.
        function tomDoItemNotificacao(item) {
            if (item.tipo === "pronto") { return "sucesso"; }
            if (item.tipo === "triagem" || item.tipo === "conferencia_manual") { return "conferencia"; }
            if (item.tipo === "revisao") { return "revisao"; }
            return "erro";
        }

        // Um popup só, pra um lote de notificações que podem ser de
        // tipos diferentes — só usa a cor específica (sucesso/conferência/
        // revisão) quando TODAS as novidades do lote forem do mesmo tipo;
        // um lote misturado (ex: 1 sucesso + 1 conferência juntos) cai no
        // tom de atenção padrão (erro), mais seguro que arriscar mostrar
        // verde quando nem tudo é boa notícia.
        function tomDoLote(itens) {
            var tons = itens.map(tomDoItemNotificacao);
            var primeiro = tons[0];
            var todosIguais = tons.every(function (tom) { return tom === primeiro; });

            return todosIguais ? primeiro : "erro";
        }

        // Toast (reaproveita window.mostrarBanner/mostrarBannerDetalhado,
        // já usados pelos avisos de upload da Fila) — Henrique, 2026-08-07:
        // "aparecer um popup... para notificar rapido que chegou algo...
        // sem ter que clicar". Sistema e Conferências alertam em toasts
        // separados (mesma separação por categoria do resto do painel);
        // singular/plural escrito por extenso em cada bloco (não dá pra
        // só grudar um "s" em "Robô"/"Conferências" sem estragar a
        // concordância).
        function alertarNovasNotificacoes(novas) {
            if (novas.length === 0) {
                return;
            }

            tocarSomNotificacao();
            chacoalharSino();

            // Aba em segundo plano — soma no título pra chamar atenção
            // mesmo sem a pessoa estar olhando (Henrique, 2026-08-08:
            // "atrai a pessoa a olhar oq deu"). Com foco: (dispensável)
            // o painel já mostra tudo ao vivo, não precisa duplicar no
            // título.
            if (document.hidden) {
                notificacoesNaoVistas += novas.length;
                atualizarTituloNotificacoes();
            }

            // Henrique, diretoria, 2026-08-19: "Sistema" virou reservado
            // pra comunicados administrativos (feature futura — nenhuma
            // fonte emite tipo "comunicado" ainda, então fica vazio até
            // essa tela nascer). "Ferramentas" (antiga "Conferências")
            // passou a cobrir TUDO que não for pessoal nem comunicado —
            // triagem, erro, sucesso e revisão do Robô juntos.
            var novasMinhas = novas.filter(function (item) { return item.pessoal === true; });
            var novasSistema = novas.filter(function (item) { return !item.pessoal && item.tipo === "comunicado"; });
            var novasFerramentas = novas.filter(function (item) { return !item.pessoal && item.tipo !== "comunicado"; });

            if (novasSistema.length === 1) {
                window.mostrarBanner("Novo comunicado: " + novasSistema[0].mensagem, "erro");
            } else if (novasSistema.length > 1) {
                window.mostrarBannerDetalhado(
                    novasSistema.length + " novos comunicados — clique pra ver",
                    novasSistema.map(function (item) { return { titulo: item.ferramenta, detalhe: item.mensagem }; }),
                    "erro"
                );
            }

            // "Ferramentas" mistura sucesso do Robô (tipo "pronto") com
            // triagem/conferência/revisão/erro — tomDoLote (acima) dá o
            // tom certo pra cada tipo, igual à lista do sino já fazia.
            // Bug real corrigido aqui (Henrique, 2026-08-21): antes era
            // sempre "erro" fixo, então um sucesso do Robô saía em
            // vermelho no popup.
            if (novasFerramentas.length > 0) {
                var tomFerramentas = tomDoLote(novasFerramentas);

                if (novasFerramentas.length === 1) {
                    window.mostrarBanner("Nova notificação de Ferramentas: " + novasFerramentas[0].mensagem, tomFerramentas);
                } else {
                    window.mostrarBannerDetalhado(
                        novasFerramentas.length + " novas notificações de Ferramentas — clique pra ver",
                        novasFerramentas.map(function (item) { return { titulo: item.ferramenta, detalhe: item.mensagem }; }),
                        tomFerramentas
                    );
                }
            }

            // "Minhas" mistura boas notícias ("pronto") com pendências
            // (erro/revisão/conferência) — tomDoLote dá o tom certo pra
            // cada tipo; só sai verde quando TODAS as novidades da vez
            // forem "pronto".
            if (novasMinhas.length > 0) {
                var tomMinhas = tomDoLote(novasMinhas);

                if (novasMinhas.length === 1) {
                    window.mostrarBanner(novasMinhas[0].mensagem, tomMinhas);
                } else {
                    window.mostrarBannerDetalhado(
                        novasMinhas.length + " novidades suas — clique pra ver",
                        novasMinhas.map(function (item) { return { titulo: item.ferramenta, detalhe: item.mensagem }; }),
                        tomMinhas
                    );
                }
            }
        }

        function preencherListaNotificacoes(listaEl, itens) {
            listaEl.innerHTML = "";

            itens.forEach(function (item) {
                var linkEl = document.createElement("a");
                linkEl.className = "item-notificacao item-notificacao-" + item.tipo;
                if (item.descartavel) {
                    linkEl.className += " item-notificacao-descartavel";
                }
                linkEl.href = item.link;

                var origemEl = document.createElement("span");
                origemEl.className = "item-notificacao-origem";
                origemEl.textContent = item.ferramenta;

                var textoEl = document.createElement("span");
                textoEl.className = "item-notificacao-texto";
                textoEl.textContent = item.mensagem;

                linkEl.appendChild(origemEl);
                linkEl.appendChild(textoEl);

                // X só em notificações "não importantes" (Henrique,
                // 2026-08-13: "pronto" pode ser descartado na hora;
                // conferência/erro/revisão ficam até a pessoa resolver de
                // verdade, nunca por aqui). item.resolver é a rota que
                // marca Job.notificacao_resolvida — depois de descartar,
                // busca /notificacoes de novo pra já refletir em tudo
                // (lista, contadores, sino).
                if (item.descartavel && item.resolver) {
                    var descartarEl = document.createElement("button");
                    descartarEl.type = "button";
                    descartarEl.className = "item-notificacao-descartar";
                    descartarEl.setAttribute("aria-label", "Dispensar notificação");
                    descartarEl.textContent = "×";

                    descartarEl.addEventListener("click", function (evento) {
                        evento.preventDefault();
                        evento.stopPropagation();
                        descartarEl.disabled = true;

                        fetch(item.resolver, { method: "POST" })
                            .then(function (resp) {
                                if (!resp.ok) { throw new Error("falhou"); }
                                consultarNotificacoes();
                            })
                            .catch(function () { descartarEl.disabled = false; });
                    });

                    linkEl.appendChild(descartarEl);
                }

                listaEl.appendChild(linkEl);
            });
        }

        function renderizarNotificacoes(itens) {
            // Compara com o poll anterior ANTES de qualquer outra coisa
            // mexer no DOM — detectarNovasNotificacoes já atualiza o
            // registro do que é "conhecido" pro próximo tick, então só
            // pode rodar uma vez por render.
            var novas = detectarNovasNotificacoes(itens);

            // item.pessoal (Henrique, 2026-08-13) vai pra "Minhas",
            // independente do tipo — pendências do fluxo Manual/URGENTE
            // do PRÓPRIO usuário. Henrique, diretoria, 2026-08-19: do
            // restante, "Ferramentas" (antiga "Conferências") passou a
            // cobrir TUDO que o Robô gera — triagem, erro, sucesso,
            // revisão; "Sistema" ficou reservado só pra comunicados
            // administrativos (tipo "comunicado", feature futura — hoje
            // nenhuma fonte emite isso, então a aba fica vazia até
            // nascer). Se uma aba nem existe pra esse usuário
            // (Ferramentas depende de acesso a alguma ferramenta com
            // Robô), não sobra item dela no payload mesmo (o backend já
            // filtra antes de devolver — ver notificacoes_do_usuario),
            // então separar aqui é sempre seguro, existindo a aba ou não.
            var itensMinhas = itens.filter(function (item) { return item.pessoal === true; });
            var itensSistema = itens.filter(function (item) { return !item.pessoal && item.tipo === "comunicado"; });
            var itensConferencias = itens.filter(function (item) { return !item.pessoal && item.tipo !== "comunicado"; });

            preencherListaNotificacoes(listaNotificacoesEl, itensSistema);
            if (listaNotificacoesMinhasEl) {
                preencherListaNotificacoes(listaNotificacoesMinhasEl, itensMinhas);
            }
            if (listaNotificacoesConferenciasEl) {
                preencherListaNotificacoes(listaNotificacoesConferenciasEl, itensConferencias);
            }

            // Contador ao lado do título de cada aba — mesma ideia do
            // "Gerar relatórios"/"Relatórios" de cada ferramenta, só que
            // aqui atualizado ao vivo a cada poll (Henrique, 2026-08-07:
            // "consigo saber quantas notificações são em cada aba antes
            // de precisar entrar nela"). Some por completo em zero (não
            // mostra "0") — Henrique pediu isso explicitamente, diferente
            // do .contagem-aba original que sempre mostra o número.
            if (contagemAbaSistemaEl) {
                contagemAbaSistemaEl.textContent = itensSistema.length > 99 ? "99+" : String(itensSistema.length);
                contagemAbaSistemaEl.hidden = itensSistema.length === 0;
            }
            if (contagemAbaMinhasEl) {
                contagemAbaMinhasEl.textContent = itensMinhas.length > 99 ? "99+" : String(itensMinhas.length);
                contagemAbaMinhasEl.hidden = itensMinhas.length === 0;
            }
            if (contagemAbaConferenciasEl) {
                contagemAbaConferenciasEl.textContent = itensConferencias.length > 99 ? "99+" : String(itensConferencias.length);
                contagemAbaConferenciasEl.hidden = itensConferencias.length === 0;
            }

            // Painel já pode estar aberto quando um poll periódico
            // reconstrói a lista (não só na primeira carga) — nesse caso
            // dá pra medir certo na hora.
            if (!painelNotificacoesEl.hidden) {
                atualizarBotoesExpandir();
            }

            // Reaplica a visibilidade da aba ATUAL com o conteúdo recém
            // preenchido — cobre tanto a primeira carga quanto um poll
            // periódico chegando com o painel aberto numa aba que não é
            // "Sistema" (sem isso, o poll reapareceria a lista errada por
            // baixo da aba ativa).
            mostrarAbaNotificacoes(abaNotificacoesAtiva);

            if (itens.length > 0) {
                badgeNotificacoesEl.textContent = itens.length > 99 ? "99+" : String(itens.length);
                badgeNotificacoesEl.hidden = false;
            } else {
                badgeNotificacoesEl.hidden = true;
            }

            alertarNovasNotificacoes(novas);
        }

        function consultarNotificacoes() {
            // cache: "no-store" de propósito — Henrique reportou uma
            // notificação nova não aparecendo sem F5 (2026-08-07).
            // Verificado ao vivo que o polling em si atualizava certo
            // sem reload nenhum (não achado bug ali), mas isso aqui
            // fecha por completo a possibilidade de o navegador (ou
            // algum proxy no meio do caminho) servir uma resposta
            // cacheada em vez de bater no servidor de verdade.
            fetch("/notificacoes", { cache: "no-store" })
                .then(function (resposta) { return resposta.json(); })
                .then(function (dados) { renderizarNotificacoes(dados.itens || []); })
                .catch(function () {
                    // Falha de rede pontual — mantém o que já estava
                    // mostrado, tenta de novo no próximo evento/tick.
                });
        }

        // Título da aba enquanto ela está em segundo plano (Henrique,
        // 2026-08-08: "poderia aparecer algo tambem no nome da guia...
        // Tipo 'X notificações novas'" — confirmado: soma TODAS as
        // categorias juntas, sem distinção). Só conta quando a aba
        // realmente não está visível (document.hidden) — com ela em
        // foco, a pessoa já está vendo o sininho/painel se atualizar ao
        // vivo, não faz sentido "avisar" no título também. Restaura o
        // título original assim que a aba volta a ficar visível.
        var tituloOriginalDocumento = document.title;
        var notificacoesNaoVistas = 0;

        function atualizarTituloNotificacoes() {
            if (notificacoesNaoVistas === 0) {
                document.title = tituloOriginalDocumento;
                return;
            }

            var contagem = notificacoesNaoVistas > 99 ? "99+" : String(notificacoesNaoVistas);
            var sufixo = notificacoesNaoVistas === 1 ? "notificação nova" : "notificações novas";
            document.title = contagem + " " + sufixo + " — " + tituloOriginalDocumento;
        }

        document.addEventListener("visibilitychange", function () {
            if (document.hidden) {
                return;
            }

            notificacoesNaoVistas = 0;
            atualizarTituloNotificacoes();
            // Volta o foco pra aba é um ótimo momento de buscar de novo
            // na hora, sem esperar o SSE ou a rede de segurança — cobre
            // o caso raro de um evento SSE ter chegado enquanto a
            // conexão estava temporariamente instável.
            consultarNotificacoes();
        });

        // SSE (Server-Sent Events) via SharedWorker — Henrique, 2026-08-11:
        // cada aba abrindo sua PRÓPRIA conexão SSE estourava o limite de 6
        // conexões simultâneas por site que o navegador impõe (Chrome/Edge/
        // Firefox, HTTP/1.1) — com poucas abas do site abertas ao mesmo
        // tempo, qualquer navegação NOVA ficava "carregando" indefinidamente
        // esperando uma conexão livre, mesmo com o servidor respondendo na
        // hora (bug real, reproduzido ao vivo). O SharedWorker (ver
        // notificacoes_worker.js) mantém UMA ÚNICA conexão SSE compartilhada
        // entre todas as abas do site, não importa quantas estejam abertas.
        if (window.SharedWorker) {
            var worker = new SharedWorker("/static/notificacoes_worker.js?v=" + VERSAO_ESTATICOS);
            worker.port.onmessage = function (evento) {
                if (evento.data === "atualizar") {
                    consultarNotificacoes();
                }
            };
            worker.port.start();

            // Avisa o worker que essa aba fechou/navegou pra fora, pra ele
            // tirar a porta da lista — sem isso a lista só cresce pela
            // sessão inteira do navegador (Rodada 12, achado de qualidade
            // de código; inofensivo na prática, postMessage numa porta
            // morta não faz nada, mas nunca era limpo).
            window.addEventListener("pagehide", function () {
                worker.port.postMessage("desconectar");
            });
        } else if (window.EventSource) {
            // Sem suporte a SharedWorker (raro hoje em dia): volta pro
            // EventSource direto, por aba — funciona, só sofre de novo do
            // limite de conexões com muitas abas abertas.
            var eventos = new EventSource("/notificacoes/eventos");
            eventos.addEventListener("atualizar", consultarNotificacoes);
        }
        // Sem suporte a nenhum dos dois (navegador muito antigo), a rede de
        // segurança abaixo vira a única via — ainda funciona, só sem
        // instantaneidade nenhuma.

        consultarNotificacoes();

        // Rede de segurança, com ou sem SSE — bem espaçada de propósito
        // (ver comentário no topo do arquivo). Roda mesmo com a aba
        // escondida: diferente do polling antigo, aqui é só uma
        // garantia de "nunca ficar desatualizado por muito tempo mesmo
        // se o SSE falhar silenciosamente", não a via principal.
        setInterval(consultarNotificacoes, INTERVALO_NOTIFICACOES_MS_RESERVA);
    }
})();
