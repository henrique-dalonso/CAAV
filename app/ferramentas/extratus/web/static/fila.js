(function () {
    "use strict";

    // ---------------------------------------------------------------
    // Upload de PDFs — dropzone, cartões de arquivo, popover "+N",
    // dedupe client-side e envio via XHR (progresso real, sem recarregar
    // a página até o fim). Ver [[extratus-fila-motor-redesign]].
    // ---------------------------------------------------------------

    var LIMITE_CARTOES_VISIVEIS = 5;
    var LIMITE_TAMANHO_BYTES = 350 * 1024 * 1024;
    var DURACAO_SAIDA_MS = 420; // combina com a transition de .arquivo-cartao no CSS

    // Chave do sessionStorage pro "Desfazer último envio" — namespaced
    // pelo caminho da URL (/extratus/... ou /extratus-aburesi/...) pra
    // os dois módulos nunca lerem o registro um do outro, mesmo abertos
    // ao mesmo tempo no mesmo navegador (sessionStorage é por origem,
    // não por caminho). Usada tanto por quem dispara o envio quanto pelo
    // bloco que decide se mostra o botão, mais abaixo neste arquivo.
    function chaveUltimoEnvio() {
        return "extratus_ultimo_envio:" + window.location.pathname.split("/")[1];
    }

    // Compartilhada entre o modo de seleção (mais abaixo) e o polling —
    // enquanto alguém está no meio de marcar checkboxes pra remover,
    // o polling não pode redesenhar a lista de Pendentes por baixo dos
    // pés da pessoa (perderia a seleção). Ver bloco de polling.
    var modoSelecaoAtivo = false;

    var form = document.getElementById("form-upload-fila");
    var zona = document.getElementById("zona-soltar-fila");
    var campoUpload = document.getElementById("campo-pdfs-fila");
    var loteEl = document.getElementById("upload-lote");
    var contagemEl = document.getElementById("upload-lote-contagem");
    var cartoesEl = document.getElementById("upload-cartoes");
    var maisWrapEl = document.getElementById("upload-mais-wrap");
    var maisBotaoEl = document.getElementById("botao-mais-arquivos");
    var maisListaEl = document.getElementById("upload-mais-lista");
    var botaoDesfazer = document.getElementById("botao-desfazer-fila");
    var botaoRemoverTodos = document.getElementById("botao-remover-todos-fila");
    var botaoEnviar = document.getElementById("botao-enviar-fila");
    var progressoEl = document.getElementById("upload-progresso");
    var progressoBarraEl = document.getElementById("upload-progresso-barra");
    var progressoTextoEl = document.getElementById("upload-progresso-texto");

    if (form && zona && campoUpload && botaoEnviar) {
        var arquivos = []; // [{ id, file }] — nunca é alterado durante o envio (fonte da verdade pra restaurar em caso de erro)
        var proximoId = 1;
        var enviando = false;

        // Pilha de estados anteriores de "arquivos" — cada ação que muda
        // a seleção (adicionar um lote, remover um, remover todos) empilha
        // o estado ANTERIOR aqui antes de aplicar a mudança. "Desfazer"
        // só desempilha e volta pra esse estado, um passo de cada vez.
        // Só cobre a etapa de montar o lote (antes de enviar) — depois
        // que os arquivos já foram de fato enviados ela é zerada, porque
        // desfazer um envio de verdade é outra história (ver conversa
        // sobre "Desfazer envio").
        var historico = [];

        // Nomes já presentes na fila (Pendentes + Processando), lidos do
        // que o servidor já renderizou nesta página — cobre o caso mais
        // comum (reenviar um arquivo que já está na esteira agora). Não
        // cobre histórico de lotes antigos/já concluídos — isso depende
        // da triagem real (nome + número de processo), que é um passo
        // futuro deste redesenho, não construído ainda.
        var nomesNaFila = {};
        document.querySelectorAll(".fila-item-nome[title]").forEach(function (span) {
            nomesNaFila[span.getAttribute("title")] = true;
        });

        function formatarTamanho(bytes) {
            if (bytes < 1024) { return bytes + " B"; }
            if (bytes < 1024 * 1024) { return (bytes / 1024).toFixed(0) + " KB"; }
            return (bytes / (1024 * 1024)).toFixed(1).replace(".", ",") + " MB";
        }

        function nomeJaSelecionado(lista, nome) {
            return lista.some(function (item) { return item.file.name === nome; });
        }

        function porId(id) {
            return arquivos.filter(function (item) { return item.id === id; })[0];
        }

        function iconePdfSVG() {
            // A "etiqueta" vermelha precisa ficar TODA dentro da folha —
            // antes ela começava quase em cima da borda esquerda (x=3.2
            // contra a borda em x=3), cortando visualmente a moldura
            // (Henrique, 2026-08-07, "carinha de coisa barata"). Agora
            // fica centralizada com margem real dos dois lados (folha vai
            // de x=3 a x=21, etiqueta de x=5 a x=19). `user-select:none`
            // no <svg> raiz (herda pros filhos) impede selecionar o texto
            // "PDF" com o mouse — ícone decorativo, não é texto de verdade.
            return '<svg viewBox="0 0 24 28" fill="none" aria-hidden="true" style="user-select:none;">' +
                '<path d="M3 1.5h12.5L21 7v19a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 26V3A1.5 1.5 0 0 1 4.5 1.5Z" ' +
                'fill="var(--cor-cartao)" stroke="var(--cor-texto-suave)" stroke-width="1.3"/>' +
                '<path d="M15.5 1.5V7H21" fill="none" stroke="var(--cor-texto-suave)" stroke-width="1.3" stroke-linejoin="round"/>' +
                '<rect x="5" y="16" width="14" height="7" rx="1.2" fill="#dc2626"/>' +
                '<text x="12" y="21.2" text-anchor="middle" font-family="Arial, sans-serif" font-size="6.6" font-weight="700" fill="white">PDF</text>' +
                '</svg>';
        }

        function sincronizarInputReal() {
            var dt = new DataTransfer();
            arquivos.forEach(function (item) { dt.items.add(item.file); });
            campoUpload.files = dt.files;
        }

        function atualizarBotaoDesfazer() {
            if (botaoDesfazer) {
                botaoDesfazer.disabled = historico.length === 0 || enviando;
            }
        }

        // Empilha o estado atual antes de trocar pra "novoArquivos" — todo
        // ponto que muda a seleção (adicionar, remover um, remover todos)
        // passa por aqui, então "desfazer" sempre tem de onde voltar.
        function aplicarMudanca(novoArquivos) {
            historico.push(arquivos.slice());
            arquivos = novoArquivos;
            atualizarBotaoDesfazer();
        }

        function desfazer() {
            if (historico.length === 0) {
                return;
            }
            arquivos = historico.pop();
            sincronizarInputReal();
            renderizar();
        }

        function removerArquivo(id) {
            aplicarMudanca(arquivos.filter(function (item) { return item.id !== id; }));
            sincronizarInputReal();
            renderizar();
        }

        function removerTodos() {
            aplicarMudanca([]);
            sincronizarInputReal();
            renderizar();
        }

        function criarBotaoRemover(id, nome) {
            var botao = document.createElement("button");
            botao.type = "button";
            botao.className = "arquivo-cartao-remover";
            botao.setAttribute("aria-label", "Remover " + nome);
            botao.textContent = "×";
            botao.addEventListener("click", function (evento) {
                evento.preventDefault();
                evento.stopPropagation();
                removerArquivo(id);
            });
            return botao;
        }

        function criarCartao(item) {
            var cartao = document.createElement("div");
            cartao.className = "arquivo-cartao";
            cartao.dataset.id = item.id;

            var icone = document.createElement("span");
            icone.className = "arquivo-cartao-icone";
            icone.innerHTML = iconePdfSVG();

            var nome = document.createElement("span");
            nome.className = "arquivo-cartao-nome truncavel";
            nome.dataset.dica = item.file.name;
            nome.textContent = item.file.name;

            var tamanho = document.createElement("span");
            tamanho.className = "arquivo-cartao-tamanho";
            tamanho.textContent = formatarTamanho(item.file.size);

            cartao.appendChild(criarBotaoRemover(item.id, item.file.name));
            cartao.appendChild(icone);
            cartao.appendChild(nome);
            cartao.appendChild(tamanho);
            return cartao;
        }

        function criarLinhaPopover(item) {
            var linha = document.createElement("li");

            var nome = document.createElement("span");
            nome.className = "upload-mais-item-nome truncavel";
            nome.dataset.dica = item.file.name;
            nome.textContent = item.file.name;

            var tamanho = document.createElement("span");
            tamanho.className = "upload-mais-item-tamanho";
            tamanho.textContent = formatarTamanho(item.file.size);

            linha.appendChild(nome);
            linha.appendChild(tamanho);
            linha.appendChild(criarBotaoRemover(item.id, item.file.name));
            return linha;
        }

        function atualizarTextoBotaoEnviar(total) {
            var textoBotao = document.getElementById("botao-enviar-fila-texto");
            if (!textoBotao) {
                return;
            }
            if (total === 0) {
                textoBotao.textContent = "Enviar pra fila";
            } else if (total === 1) {
                textoBotao.textContent = "Enviar 1 PDF pra fila";
            } else {
                textoBotao.textContent = "Enviar " + total + " PDFs pra fila";
            }
        }

        function atualizarResumo(total) {
            var totalBytes = arquivos.reduce(function (soma, item) { return soma + item.file.size; }, 0);
            var rotuloArquivos = total === 1 ? "1 arquivo selecionado" : total + " arquivos selecionados";
            contagemEl.textContent = rotuloArquivos + " · " + formatarTamanho(totalBytes) + " no total";
            atualizarTextoBotaoEnviar(total);
        }

        function preencherPopover(restantes) {
            if (restantes.length > 0) {
                maisWrapEl.hidden = false;
                maisBotaoEl.textContent = "+" + restantes.length;
                maisListaEl.innerHTML = "";
                restantes.forEach(function (item) {
                    maisListaEl.appendChild(criarLinhaPopover(item));
                });
            } else {
                maisWrapEl.hidden = true;
                painelFechar();
            }
        }

        // Redesenho completo (antes de enviar) — chamado a cada
        // adição/remoção manual, é barato o bastante pra refazer tudo do
        // zero. #upload-mais-wrap nunca é removido do DOM (só escondido
        // via [hidden]) pra não perder o listener já ligado nele
        // (window.configurarAlternador, chamado uma única vez lá embaixo)
        // — por isso os cartões são inseridos SEMPRE antes dele
        // (insertBefore), nunca via innerHTML no container inteiro.
        function renderizar() {
            var total = arquivos.length;
            // Mesmo com 0 arquivos selecionados, a barra de ações continua
            // visível se ainda dá pra desfazer (ex: acabou de clicar
            // "Remover todos" e pode querer trazer tudo de volta) — só
            // some de vez quando não há nem seleção nem histórico.
            loteEl.hidden = total === 0 && historico.length === 0;
            botaoEnviar.disabled = total === 0 || enviando;
            botaoRemoverTodos.disabled = total === 0 || enviando;
            atualizarBotaoDesfazer();

            if (total === 0) {
                Array.prototype.slice.call(cartoesEl.querySelectorAll(".arquivo-cartao")).forEach(function (el) { el.remove(); });
                maisWrapEl.hidden = true;
                contagemEl.textContent = "Nenhum arquivo selecionado.";
                atualizarTextoBotaoEnviar(0);
                return;
            }

            var visiveis = arquivos.slice(0, LIMITE_CARTOES_VISIVEIS);
            var restantes = arquivos.slice(LIMITE_CARTOES_VISIVEIS);

            Array.prototype.slice.call(cartoesEl.querySelectorAll(".arquivo-cartao")).forEach(function (el) { el.remove(); });
            visiveis.forEach(function (item, indice) {
                var cartao = criarCartao(item);
                cartao.style.animationDelay = (indice * 45) + "ms";
                cartoesEl.insertBefore(cartao, maisWrapEl);
            });

            preencherPopover(restantes);
            atualizarResumo(total);
        }

        function adicionarArquivos(lista) {
            var recusados = []; // [{ nome, motivo }] — motivo específico, não uma frase genérica "ou X ou Y"
            var novosArquivos = arquivos.slice();

            Array.prototype.forEach.call(lista, function (file) {
                var nomeMinusculo = file.name.toLowerCase();

                if (!nomeMinusculo.endsWith(".pdf")) {
                    recusados.push({ nome: file.name, motivo: "Não é um arquivo PDF" });
                    return;
                }

                if (file.size > LIMITE_TAMANHO_BYTES) {
                    recusados.push({ nome: file.name, motivo: "Maior que 350MB" });
                    return;
                }

                if (nomesNaFila[file.name] || nomeJaSelecionado(novosArquivos, file.name)) {
                    recusados.push({ nome: file.name, motivo: "Já está na fila ou já foi selecionado" });
                    return;
                }

                novosArquivos.push({ id: proximoId++, file: file });
            });

            // Um erro só: cabe inteiro numa linha, com o motivo já junto —
            // não precisa de painel expansível. Vários de uma vez: um
            // resumo vago ("duplicado ou grande demais?") não ajuda
            // ninguém a saber qual arquivo tinha qual problema, então
            // vira um toast clicável com a lista nome+motivo.
            if (recusados.length === 1) {
                window.mostrarBanner("\"" + recusados[0].nome + "\" não foi adicionado: " + recusados[0].motivo + ".", "erro");
            } else if (recusados.length > 1) {
                window.mostrarBannerDetalhado(
                    recusados.length + " arquivos não foram adicionados — clique pra ver os motivos",
                    recusados.map(function (r) { return { titulo: r.nome, detalhe: r.motivo }; }),
                    "erro"
                );
            }

            if (novosArquivos.length !== arquivos.length) {
                aplicarMudanca(novosArquivos);
            }

            sincronizarInputReal();
            renderizar();
        }

        // Painel "+N" reaproveita o mesmo mecanismo de abrir/fechar do
        // resto do site (bandeja de apps, card de perfil) — só um painel
        // aberto por vez, fecha ao clicar fora ou apertar Esc.
        var painelFechar = function () {};
        if (window.configurarAlternador) {
            painelFechar = window.configurarAlternador("botao-mais-arquivos", "painel-mais-arquivos") || painelFechar;
        }

        campoUpload.addEventListener("change", function () {
            adicionarArquivos(this.files);
        });

        zona.addEventListener("dragover", function (evento) {
            evento.preventDefault();
            zona.classList.add("arrastando");
        });

        zona.addEventListener("dragleave", function () {
            zona.classList.remove("arrastando");
        });

        zona.addEventListener("drop", function (evento) {
            evento.preventDefault();
            zona.classList.remove("arrastando");
            adicionarArquivos(evento.dataTransfer.files);
        });

        botaoRemoverTodos.addEventListener("click", removerTodos);

        if (botaoDesfazer) {
            botaoDesfazer.addEventListener("click", desfazer);
        }

        form.addEventListener("submit", function (evento) {
            if (enviando || arquivos.length === 0) {
                evento.preventDefault();
                return;
            }

            evento.preventDefault();
            enviarLote();
        });

        // Envia um arquivo por requisição (não um FormData gigante com o
        // lote inteiro) — assim um PDF ruim/duplicado não trava os outros,
        // e se a conexão cair no meio, tudo que já tinha sido aceito
        // continua salvo de verdade no servidor (só o resto precisa ser
        // reenviado). Também dá progresso e "concluído" reais por
        // arquivo, em vez de estimados por bytes acumulados.
        function enviarLote() {
            enviando = true;
            botaoEnviar.disabled = true;
            botaoRemoverTodos.disabled = true;
            // Depois que o envio começa, "desfazer" pro estado de antes
            // não faz mais sentido — os arquivos já estão a caminho do
            // servidor, não dá pra "cancelar" isso com um clique local
            // (ver conversa sobre "Desfazer envio").
            historico = [];
            atualizarBotaoDesfazer();
            loteEl.classList.add("upload-lote-enviando");
            painelFechar();

            var ordem = arquivos.slice();
            var total = ordem.length;
            var indice = 0;
            var enviadosOk = 0;
            var falhas = []; // [{ nome, motivo }]

            var visivelIds = Array.prototype.map.call(
                cartoesEl.querySelectorAll(".arquivo-cartao"),
                function (el) { return Number(el.dataset.id); }
            );
            var esperaIds = ordem
                .map(function (item) { return item.id; })
                .filter(function (id) { return visivelIds.indexOf(id) === -1; });

            function avancarFila(id) {
                var indiceVisivel = visivelIds.indexOf(id);
                if (indiceVisivel !== -1) {
                    visivelIds.splice(indiceVisivel, 1);
                }

                var elConcluido = cartoesEl.querySelector('.arquivo-cartao[data-id="' + id + '"]');
                if (elConcluido) {
                    elConcluido.classList.add("arquivo-cartao-saindo");
                    setTimeout(function () { elConcluido.remove(); }, DURACAO_SAIDA_MS);
                }

                if (esperaIds.length > 0) {
                    var proximoId = esperaIds.shift();
                    visivelIds.push(proximoId);
                    var novoCartao = criarCartao(porId(proximoId));
                    cartoesEl.insertBefore(novoCartao, maisWrapEl);
                }

                preencherPopover(esperaIds.map(porId));
            }

            progressoEl.hidden = false;
            progressoBarraEl.style.width = "0%";
            progressoTextoEl.textContent = "Enviando... (0/" + total + ")";

            function finalizarEnvio() {
                enviando = false;
                loteEl.classList.remove("upload-lote-enviando");
                progressoEl.hidden = true;

                if (falhas.length === 0) {
                    // Guarda quais arquivos foram desse envio (só no
                    // sessionStorage, não no servidor) pra oferecer
                    // "Desfazer último envio" na próxima carga da página
                    // (ver bloco dedicado mais abaixo neste arquivo).
                    sessionStorage.setItem(chaveUltimoEnvio(), JSON.stringify({
                        nomes: ordem.map(function (item) { return item.file.name; }),
                        quando: Date.now()
                    }));
                    window.location = form.action.replace(/\/upload$/, "") +
                        "?sucesso=" + encodeURIComponent(enviadosOk + " PDF(s) enviado(s) pra fila do Motor.");
                    return;
                }

                // Alguns falharam: o que deu certo já está salvo de
                // verdade no servidor, não precisa (nem deve) ser
                // reenviado — some da lista local. Só o que falhou
                // continua nos cartões, pronto pra tentar de novo com um
                // clique em "Enviar pra fila".
                botaoRemoverTodos.disabled = false;
                arquivos = arquivos.filter(function (item) {
                    return falhas.some(function (f) { return f.nome === item.file.name; });
                });
                sincronizarInputReal();
                renderizar();

                if (falhas.length === 1) {
                    window.mostrarBanner('"' + falhas[0].nome + '" não foi enviado: ' + falhas[0].motivo + ".", "erro");
                } else {
                    window.mostrarBannerDetalhado(
                        enviadosOk + " de " + total + " enviados, " + falhas.length + " falharam — clique pra ver os motivos",
                        falhas.map(function (f) { return { titulo: f.nome, detalhe: f.motivo }; }),
                        "erro"
                    );
                }
            }

            function tratarResultado(item, sucesso, motivo) {
                if (sucesso) {
                    enviadosOk += 1;
                    avancarFila(item.id);
                } else {
                    falhas.push({ nome: item.file.name, motivo: motivo });
                    var elFalhou = cartoesEl.querySelector('.arquivo-cartao[data-id="' + item.id + '"]');
                    if (elFalhou) {
                        elFalhou.classList.add("arquivo-cartao-falhou");
                    }
                }

                indice += 1;
                progressoTextoEl.textContent = "Enviando... (" + indice + "/" + total + ")";
                enviarProximo();
            }

            function enviarProximo() {
                if (indice >= total) {
                    finalizarEnvio();
                    return;
                }

                var item = ordem[indice];
                var dados = new FormData();
                dados.append("arquivos", item.file);

                var xhr = new XMLHttpRequest();
                xhr.open("POST", form.action, true);
                xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");

                xhr.upload.addEventListener("progress", function (evento) {
                    if (evento.lengthComputable) {
                        var fracaoAtual = evento.loaded / evento.total;
                        var pctGeral = Math.round(((indice + fracaoAtual) / total) * 100);
                        progressoBarraEl.style.width = pctGeral + "%";
                    }
                });

                xhr.addEventListener("load", function () {
                    if (xhr.status < 200 || xhr.status >= 300) {
                        tratarResultado(item, false, "erro " + xhr.status + " no servidor");
                        return;
                    }

                    try {
                        var resposta = JSON.parse(xhr.responseText);
                        if (resposta.enviados > 0) {
                            tratarResultado(item, true, null);
                        } else {
                            var motivo = (resposta.rejeitados && resposta.rejeitados[0]) || "recusado pelo servidor";
                            tratarResultado(item, false, motivo);
                        }
                    } catch (erro) {
                        tratarResultado(item, false, "resposta inesperada do servidor");
                    }
                });

                xhr.addEventListener("error", function () {
                    tratarResultado(item, false, "falha de rede");
                });

                xhr.send(dados);
            }

            enviarProximo();
        }
    }

    // ---------------------------------------------------------------
    // "Desfazer último envio" — desfazer de verdade, depois que os
    // arquivos já foram pro servidor (diferente do "Desfazer" de cima,
    // que só desfaz montagem local do lote). Só funciona enquanto o
    // Motor ainda não reivindicou os arquivos pro próximo lote (o
    // próprio POST /fila/remover-varios, já existente, ignora com
    // segurança qualquer arquivo já reivindicado e avisa isso na
    // mensagem — reaproveitado aqui sem nenhuma mudança no servidor).
    // ---------------------------------------------------------------

    (function () {
        var botaoDesfazerEnvio = document.getElementById("botao-desfazer-envio");

        if (!form || !botaoDesfazerEnvio) {
            return;
        }

        var EXPIRA_MS = 10 * 60 * 1000; // 10 min — só pra não deixar o botão oferecido pra sempre, não é o que garante segurança (isso é o servidor)
        var chave = chaveUltimoEnvio();
        var registroBruto = sessionStorage.getItem(chave);

        if (registroBruto) {
            try {
                var registro = JSON.parse(registroBruto);
                if (Date.now() - registro.quando < EXPIRA_MS && registro.nomes && registro.nomes.length > 0) {
                    botaoDesfazerEnvio.hidden = false;
                } else {
                    sessionStorage.removeItem(chave);
                }
            } catch (erro) {
                sessionStorage.removeItem(chave);
            }
        }

        botaoDesfazerEnvio.addEventListener("click", function () {
            var dados = sessionStorage.getItem(chave);
            if (!dados) {
                return;
            }

            var nomes;
            try {
                nomes = JSON.parse(dados).nomes || [];
            } catch (erro) {
                sessionStorage.removeItem(chave);
                return;
            }

            sessionStorage.removeItem(chave);

            var formTemp = document.createElement("form");
            formTemp.method = "post";
            formTemp.action = form.action.replace(/\/upload$/, "/remover-varios");
            formTemp.style.display = "none";

            nomes.forEach(function (nome) {
                var input = document.createElement("input");
                input.type = "hidden";
                input.name = "nomes";
                input.value = nome;
                formTemp.appendChild(input);
            });

            document.body.appendChild(formTemp);
            formTemp.submit();
        });
    })();

    // ---------------------------------------------------------------
    // Modo de seleção da coluna Pendentes (checkboxes, remover em lote).
    // ---------------------------------------------------------------

    var botaoSelecionar = document.getElementById("botao-selecionar-fila");
    var acoes = document.getElementById("fila-acoes-selecao");
    var checkTodos = document.getElementById("check-selecionar-todos-fila");
    var botaoRemover = document.getElementById("botao-remover-selecionados");
    var botaoCancelar = document.getElementById("botao-cancelar-selecao-fila");
    var listaPendentesEl = document.getElementById("lista-pendentes");

    if (!botaoSelecionar || !acoes || !listaPendentesEl) {
        return;
    }

    // Consultadas DE NOVO a cada chamada (não guardadas numa variável só
    // uma vez) — o polling pode adicionar/remover <li> a qualquer
    // momento, então uma NodeList fixa capturada no carregamento da
    // página ficaria desatualizada assim que a fila mudasse.
    function obterCheckboxes() {
        return listaPendentesEl.querySelectorAll(".fila-item-checkbox");
    }

    function obterChecks() {
        return listaPendentesEl.querySelectorAll(".fila-item-check");
    }

    function atualizarBotaoRemover() {
        var checks = obterChecks();
        var algumMarcado = Array.prototype.some.call(checks, function (c) { return c.checked; });
        var todosMarcados = checks.length > 0 && Array.prototype.every.call(checks, function (c) { return c.checked; });

        botaoRemover.disabled = !algumMarcado;
        checkTodos.checked = todosMarcados;
    }

    function entrarModoSelecao() {
        modoSelecaoAtivo = true;
        botaoSelecionar.disabled = true;
        acoes.hidden = false;
        obterCheckboxes().forEach(function (c) { c.hidden = false; });
        atualizarBotaoRemover();
    }

    function sairModoSelecao() {
        modoSelecaoAtivo = false;
        botaoSelecionar.disabled = false;
        acoes.hidden = true;
        obterCheckboxes().forEach(function (c) { c.hidden = true; });
        obterChecks().forEach(function (c) { c.checked = false; });
        checkTodos.checked = false;
    }

    botaoSelecionar.addEventListener("click", entrarModoSelecao);
    botaoCancelar.addEventListener("click", sairModoSelecao);

    checkTodos.addEventListener("change", function () {
        obterChecks().forEach(function (c) { c.checked = checkTodos.checked; });
        atualizarBotaoRemover();
    });

    // Delegação de evento (um listener só, no container) em vez de um
    // listener por checkbox — cobre tanto os que já existiam quanto os
    // que o polling adicionar depois, sem precisar religar nada.
    listaPendentesEl.addEventListener("change", function (evento) {
        if (evento.target.classList.contains("fila-item-check")) {
            atualizarBotaoRemover();
        }
    });

    // ---------------------------------------------------------------
    // Polling — a cada poucos segundos, pergunta ao servidor o estado
    // atual da fila (GET /fila/estado) e atualiza Pendentes/Processando
    // sozinho, sem precisar de F5. Pausa quando a aba não está visível
    // (Page Visibility API) pra não gastar à toa com a aba minimizada/em
    // outra guia.
    //
    // FICA NO MESMO ESCOPO do "Modo de seleção" acima de propósito (não
    // é mais um (function(){...})() próprio) — precisa enxergar
    // modoSelecaoAtivo (declarada lá no topo deste arquivo) pra saber
    // quando NÃO mexer na lista de Pendentes. Bug real encontrado
    // 2026-08-07: esse bloco já foi um IIFE separado, sem acesso a essa
    // variável — em modo estrito isso derrubava aplicarEstado() com um
    // ReferenceError em TODO ciclo, silenciosamente engolido pelo
    // .catch() do fetch (pensado só pra falha de rede) — então a
    // bolinha nunca virava amarela sozinha, só com F5. Henrique reportou
    // isso ao vivo.
    // ---------------------------------------------------------------

    var INTERVALO_POLLING_MS = 5000;

    var listaPendentesEl = document.getElementById("lista-pendentes");
    var listaProcessandoEl = document.getElementById("lista-processando");
    var vazioPendentesEl = document.getElementById("vazio-pendentes");
    var vazioProcessandoEl = document.getElementById("vazio-processando");
    var contagemPendentesEl = document.getElementById("contagem-pendentes");
    var contagemProcessandoEl = document.getElementById("contagem-processando");
    var botaoSelecionarEl = document.getElementById("botao-selecionar-fila");
    var secaoConferenciasEl = document.getElementById("secao-conferencias");
    var listaConferenciasEl = document.getElementById("lista-conferencias");
    var contagemConferenciasEl = document.getElementById("contagem-conferencias");

    if (!listaPendentesEl || !listaProcessandoEl) {
        return;
    }

    // "item" aqui é {nome, status, aguardando_conferencia} pra quem vem
    // de Pendentes (checagem_fila.py — "aprovado" é o único status que
    // passa pro motor; "aguardando_conferencia" é true nas 3
    // inconsistências reais, que agora têm bolinha VERMELHA própria,
    // distinta do laranja de "ainda checando" — Henrique, 2026-08-07)
    // ou só {nome, status: "verde"} pra quem já está em Processando (não
    // passa pela checagem, esse status nunca muda, "aguardando_
    // conferencia" fica undefined/falsy nesse caso, sem problema).
    // Lupa no fim da linha, só nos pendentes vermelhos — indício sempre
    // visível de que dá pra clicar (Henrique, 2026-08-07: "como adivinho
    // que da para passar o mouse em cima e clicar?"), não só uma
    // descoberta no hover. CSS (extratus.css) cuida da reação no hover.
    function criarIconeVerConferencia() {
        var icone = document.createElement("span");
        icone.className = "fila-item-ver-conferencia";
        icone.setAttribute("aria-hidden", "true");
        icone.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
            '<circle cx="11" cy="11" r="7"></circle>' +
            '<line x1="21" y1="21" x2="16.65" y2="16.65"></line>' +
            '</svg>';
        return icone;
    }

    function classeBolinha(item) {
        if (item.status === "verde") { return "bolinha-verde"; }
        if (item.status === "aprovado") { return "bolinha-amarela"; }
        if (item.aguardando_conferencia) { return "bolinha-vermelha"; }
        return "bolinha-laranja";
    }

    function tituloBolinha(item) {
        if (item.status === "verde") { return "Em processamento pelo Motor"; }
        if (item.status === "aprovado") { return "Aguardando o Motor"; }
        if (item.aguardando_conferencia) { return "Aguardando conferência"; }
        return "Em checagem";
    }

    function atualizarBolinha(li, item) {
        var bolinha = li.querySelector(".bolinha-status");
        if (!bolinha) {
            return;
        }
        bolinha.className = "bolinha-status " + classeBolinha(item);
        bolinha.dataset.dica = tituloBolinha(item);
        bolinha.setAttribute("aria-label", tituloBolinha(item));

        // O próprio <li> também precisa acompanhar ao vivo — um item
        // pode entrar ou sair de "aguardando conferência" enquanto a
        // página já está aberta (ex: outra pessoa resolveu pelo painel).
        li.classList.toggle("fila-item-clicavel", !!item.aguardando_conferencia);
        var iconeExistente = li.querySelector(".fila-item-ver-conferencia");
        if (item.aguardando_conferencia) {
            li.dataset.dica = "Clique para ver em 'Conferências'";
            if (!iconeExistente) {
                li.appendChild(criarIconeVerConferencia());
            }
        } else {
            delete li.dataset.dica;
            if (iconeExistente) {
                iconeExistente.remove();
            }
        }
    }

    function criarItemFila(item, comCheckbox) {
        var li = document.createElement("li");
        li.dataset.nome = item.nome;
        li.className = "fila-item-entrando";

        if (item.aguardando_conferencia) {
            li.classList.add("fila-item-clicavel");
            li.dataset.dica = "Clique para ver em 'Conferências'";
        }

        if (comCheckbox) {
            var label = document.createElement("label");
            label.className = "fila-item-checkbox";
            label.hidden = !modoSelecaoAtivo;

            var input = document.createElement("input");
            input.type = "checkbox";
            input.name = "nomes";
            input.value = item.nome;
            input.className = "check-input fila-item-check";

            var caixa = document.createElement("span");
            caixa.className = "check-caixa check-caixa-pequena";

            label.appendChild(input);
            label.appendChild(caixa);
            li.appendChild(label);
        }

        // Checkbox vem ANTES da bolinha no início da linha (Henrique,
        // 2026-08-07: "os quadradinhos... exibidos à direita da bolinha,
        // fica esquisito" — a ordem de inserção no DOM decide a ordem
        // visual aqui, já que a lista é flex sem `order` custom).
        var bolinha = document.createElement("span");
        bolinha.className = "bolinha-status " + classeBolinha(item);
        bolinha.dataset.dica = tituloBolinha(item);
        bolinha.setAttribute("aria-label", tituloBolinha(item));
        li.appendChild(bolinha);

        var nomeSpan = document.createElement("span");
        nomeSpan.className = "fila-item-nome";
        nomeSpan.dataset.dica = item.nome;
        nomeSpan.textContent = item.nome;
        li.appendChild(nomeSpan);

        if (item.aguardando_conferencia) {
            li.appendChild(criarIconeVerConferencia());
        }

        return li;
    }

    // Só adiciona/remove/atualiza o que realmente mudou (comparando por
    // nome de arquivo) — nunca joga tudo fora e redesenha do zero, senão
    // a lista "pisca" inteira a cada 5s mesmo quando nada mudou, e
    // qualquer animação de entrada perderia o sentido. "itensNovos" é
    // [{nome, status, aguardando_conferencia}] — muda sozinho com o
    // tempo pro MESMO nome (ex: laranja virando amarelo assim que a
    // checagem aprova), por isso tem uma passada própria só pra
    // atualizar quem já estava.
    function sincronizarLista(listaEl, itensNovos, comCheckbox) {
        var existentes = {};
        Array.prototype.forEach.call(listaEl.children, function (li) {
            existentes[li.dataset.nome] = li;
        });

        var itemPorNome = {};
        itensNovos.forEach(function (item) { itemPorNome[item.nome] = item; });

        // Sai: quem estava na tela e não está mais na resposta do servidor.
        Object.keys(existentes).forEach(function (nome) {
            if (!(nome in itemPorNome)) {
                var elSaindo = existentes[nome];
                elSaindo.classList.add("fila-item-saindo");
                setTimeout(function () { elSaindo.remove(); }, 320);
            }
        });

        // Continua: mesmo nome de antes, só atualiza a bolinha se o
        // status mudou (ex: terminou de checar).
        Object.keys(existentes).forEach(function (nome) {
            if (nome in itemPorNome) {
                atualizarBolinha(existentes[nome], itemPorNome[nome]);
            }
        });

        // Reordena pra bater com a ordem que o servidor mandou (em
        // Pendentes, prioriza vermelho > laranja > amarelo — Henrique,
        // 2026-08-07) e, de quebra, entra quem ainda não estava na tela.
        // appendChild com um nó que já existe no DOM só MOVE ele pra nova
        // posição (não duplica) — por isso um loop só resolve as duas
        // coisas: reordenar quem já existia e inserir os novos no lugar
        // certo. Quem está saindo (acima) fica de fora desse loop de
        // propósito — não faz sentido mover um item que já está sumindo.
        itensNovos.forEach(function (item) {
            listaEl.appendChild(existentes[item.nome] || criarItemFila(item, comCheckbox));
        });
    }

    // Base pra montar as URLs de aprovar/descartar de um card de
    // Conferências montado ao vivo — deriva do action do form de upload
    // (mesmo truque já usado abaixo pra achar a URL de /fila/estado),
    // assim esse arquivo continua igual nos dois módulos (Relatórios
    // usa /extratus/..., Aburesi usa /extratus-aburesi/...) sem precisar
    // saber o prefixo na mão.
    var baseAcaoConferencia = form
        ? form.action.replace(/\/upload$/, "/conferencia/")
        : "fila/conferencia/";

    function criarItemConferencia(item) {
        var li = document.createElement("li");
        li.className = "conferencia-item";
        li.dataset.id = item.id;
        li.dataset.nome = item.nome;

        var info = document.createElement("div");
        info.className = "conferencia-item-info";

        var nomeEl = document.createElement("span");
        // NÃO usa .truncavel aqui — desde a Round 3 (Henrique, 2026-08-07)
        // esse nome tem comportamento próprio de clique (expande OU abre
        // o PDF), controlado por um listener dedicado mais abaixo; usar a
        // classe genérica faria um card criado ao vivo (via polling) cair
        // de volta no comportamento antigo (só alterna corte, nunca abre
        // o PDF). Ver o listener de "conferencia-item-nome" mais abaixo.
        nomeEl.className = "conferencia-item-nome";
        nomeEl.dataset.dica = item.nome;
        nomeEl.textContent = item.nome;
        info.appendChild(nomeEl);

        var motivoEl = document.createElement("span");
        motivoEl.className = "conferencia-item-motivo";
        var motivoForte = document.createElement("strong");
        motivoForte.textContent = "Motivo:";
        motivoEl.appendChild(motivoForte);
        motivoEl.appendChild(document.createTextNode(
            " " + item.mensagem + (item.processo_detectado ? " — processo " + item.processo_detectado : "")
        ));
        info.appendChild(motivoEl);

        li.appendChild(info);

        var acoes = document.createElement("div");
        acoes.className = "conferencia-item-acoes";

        var formAprovar = document.createElement("form");
        formAprovar.method = "post";
        formAprovar.action = baseAcaoConferencia + item.id + "/aprovar";
        formAprovar.className = "form-conferencia";

        var dicaAprovar;

        if (item.tipo === "processo_nao_encontrado") {
            // Sem confirmação em popup pra esse tipo — digitar o número
            // certo (obrigatório) já cumpre esse papel, ver o listener
            // de submit mais abaixo.
            formAprovar.classList.add("form-conferencia-manual");
            dicaAprovar = "Libera esse arquivo pra fila do Motor, com o número de processo informado";

            var campo = document.createElement("div");
            campo.className = "conferencia-campo-processo";
            campo.hidden = true;

            var input = document.createElement("input");
            input.type = "text";
            input.name = "processo";
            input.placeholder = "0000000-00.0000.0.00.0000";
            input.pattern = "\\d{7}-\\d{2}\\.\\d{4}\\.\\d\\.\\d{2}\\.\\d{4}";
            input.inputMode = "numeric";
            input.autocomplete = "off";
            // "required" NÃO entra aqui — um campo required dentro de um
            // container hidden ainda reprova checkValidity() do navegador,
            // que roda ANTES do evento "submit" disparar, bloqueando o
            // clique em silêncio antes do listener abaixo ter a chance de
            // revelar o campo. Ligado ali, só quando fica visível de
            // verdade. Bug real achado testando ao vivo (2026-08-07).

            campo.appendChild(input);
            formAprovar.appendChild(campo);
        } else {
            formAprovar.dataset.confirm = "Confirma que quer liberar " + item.nome + " pra fila mesmo assim?";
            dicaAprovar = "Libera esse arquivo pra fila do Motor, mesmo com a inconsistência encontrada";
        }

        var botaoAprovar = document.createElement("button");
        botaoAprovar.type = "submit";
        botaoAprovar.className = "botao botao-pequeno botao-conferencia-aprovar";
        botaoAprovar.textContent = "Aprovar";
        botaoAprovar.dataset.dica = dicaAprovar;
        formAprovar.appendChild(botaoAprovar);
        acoes.appendChild(formAprovar);

        var formDescartar = document.createElement("form");
        formDescartar.method = "post";
        formDescartar.action = baseAcaoConferencia + item.id + "/descartar";
        formDescartar.className = "form-conferencia";
        formDescartar.dataset.confirm = "Descartar " + item.nome + " da fila? Essa ação não pode ser desfeita.";
        formDescartar.dataset.perigo = "true";

        var botaoDescartar = document.createElement("button");
        botaoDescartar.type = "submit";
        botaoDescartar.className = "botao-remover-fila botao-conferencia-descartar";
        botaoDescartar.textContent = "Descartar";
        botaoDescartar.dataset.dica = "Remove esse arquivo da fila pra sempre — não pode ser desfeito";
        formDescartar.appendChild(botaoDescartar);
        acoes.appendChild(formDescartar);

        li.appendChild(acoes);

        return li;
    }

    // Igual ao sincronizarLista de Pendentes/Processando (só entra/sai o
    // que realmente mudou) — mas por "id" do registro, não por nome de
    // arquivo, e NUNCA mexe num card que já existia (só adiciona/remove).
    // Importante: se alguém está no meio de digitar o número do processo
    // num card de "processo não encontrado" quando um poll chega, esse
    // card não pode ser recriado do zero — perderia o que a pessoa já
    // tinha digitado.
    function sincronizarConferencias(itensNovos) {
        if (!listaConferenciasEl) {
            return;
        }

        var existentes = {};
        Array.prototype.forEach.call(listaConferenciasEl.children, function (li) {
            existentes[li.dataset.id] = li;
        });

        var idsNovos = {};
        itensNovos.forEach(function (item) { idsNovos[String(item.id)] = true; });

        Object.keys(existentes).forEach(function (id) {
            if (!(id in idsNovos)) {
                existentes[id].remove();
            }
        });

        itensNovos.forEach(function (item) {
            if (!existentes[String(item.id)]) {
                listaConferenciasEl.appendChild(criarItemConferencia(item));
            }
        });

        if (secaoConferenciasEl) {
            secaoConferenciasEl.hidden = itensNovos.length === 0;
        }
        if (contagemConferenciasEl) {
            contagemConferenciasEl.textContent = itensNovos.length;
        }
    }

    // Delegado (não um listener por form encontrado na hora que a
    // página carrega) — precisa cobrir card de Conferências montado
    // depois, via polling. Primeiro clique em "Prosseguir" só revela o
    // campo de número do processo (nunca envia); o campo sendo
    // "required" com o formato certo já barra um envio vazio/errado
    // sozinho, sem precisar de validação extra em JS.
    document.addEventListener("submit", function (evento) {
        var alvo = evento.target;

        if (!alvo.classList || !alvo.classList.contains("form-conferencia-manual")) {
            return;
        }

        var campo = alvo.querySelector(".conferencia-campo-processo");

        if (campo && campo.hidden) {
            evento.preventDefault();
            campo.hidden = false;
            var input = campo.querySelector("input");
            if (input) {
                // Só passa a ser obrigatório agora que está visível de
                // verdade — ver comentário em criarItemConferencia.
                input.required = true;
                input.focus();
            }
        }
    });

    // Máscara do número do processo (CNJ) — digitar só números já monta
    // "0000000-00.0000.0.00.0000" sozinho, e colar um número já formatado
    // (ou só os dígitos) também funciona igual, porque os dois caem no
    // mesmo evento "input". Henrique (2026-08-07): "não precisar a pessoa
    // colocar os pontos e traços" e "se eu der ctrl+v... já cola certinho".
    // Delegado (não amarra listener só nos campos que já existem) pelo
    // mesmo motivo de sempre — cobre card montado depois via polling.
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
            if (!partes[i]) {
                break;
            }
            formatado += separadores[i] + partes[i];
        }
        return { texto: formatado, digitos: digitos };
    }

    document.addEventListener("input", function (evento) {
        var alvo = evento.target;

        if (!alvo.matches || !alvo.matches(".conferencia-campo-processo input")) {
            return;
        }

        var resultado = formatarProcessoCNJ(alvo.value);
        alvo.value = resultado.texto;

        // Assim que os 20 dígitos do CNJ estiverem completos, já manda o
        // foco pro botão de Aprovar — Henrique: "quando chegar no último
        // número, o tab-index já vai direto, sozinho, pro botão."
        if (resultado.digitos.length === 20) {
            var form = alvo.closest("form");
            var botao = form ? form.querySelector(".botao-conferencia-aprovar") : null;
            if (botao) {
                botao.focus();
            }
        }
    });

    // Clique num pendente com bolinha vermelha (aguardando conferência)
    // leva até o card correspondente lá em cima, com rolagem suave, e
    // pisca ele — Henrique: "dá uma piscadinha, mostrando onde está na
    // fila de conferências." Ignora clique dentro do checkbox de seleção
    // (não deveria disparar isso também).
    document.addEventListener("click", function (evento) {
        var linha = evento.target.closest(".fila-item-clicavel");

        if (!linha || evento.target.closest(".fila-item-checkbox")) {
            return;
        }

        var card = listaConferenciasEl
            ? listaConferenciasEl.querySelector('[data-nome="' + CSS.escape(linha.dataset.nome) + '"]')
            : null;

        if (!card) {
            return;
        }

        card.scrollIntoView({ behavior: "smooth", block: "center" });
        card.classList.remove("conferencia-item-destacado");
        void card.offsetWidth; // força reflow — permite reiniciar a animação se já rodou antes
        card.classList.add("conferencia-item-destacado");
    });

    // Clique no nome de um arquivo em Conferências: se o nome está cortado
    // (mais largo que o espaço disponível), o primeiro clique só expande —
    // igual ao .truncavel de sempre. Se já não está mais cortado (nome
    // curto desde o início, ou segundo clique depois de expandir), abre o
    // PDF original numa nova guia pra conferir o conteúdo sem baixar
    // (Henrique, 2026-08-07). Não precisa checar a classe "expandido" à
    // parte — o próprio scrollWidth já reflete a mudança de white-space
    // assim que ela é aplicada, então essa comparação sozinha já cobre os
    // três casos (nunca cortado, primeiro clique, segundo clique).
    document.addEventListener("click", function (evento) {
        var alvo = evento.target.closest(".conferencia-item-nome");

        if (!alvo) {
            return;
        }

        if (alvo.scrollWidth > alvo.clientWidth + 1) {
            alvo.classList.add("expandido");
            return;
        }

        var card = alvo.closest(".conferencia-item");
        if (card && card.dataset.id) {
            window.open(baseAcaoConferencia + card.dataset.id + "/ver", "_blank", "noopener");
        }
    });

    function aplicarEstado(estado) {
        if (contagemPendentesEl) {
            contagemPendentesEl.textContent = estado.pendentes.length;
        }
        if (contagemProcessandoEl) {
            contagemProcessandoEl.textContent = estado.processando.length;
        }
        if (vazioProcessandoEl) {
            vazioProcessandoEl.hidden = estado.processando.length > 0;
        }
        var itensProcessando = estado.processando.map(function (nome) {
            return { nome: nome, status: "verde" };
        });
        sincronizarLista(listaProcessandoEl, itensProcessando, false);

        if (estado.conferencias) {
            sincronizarConferencias(estado.conferencias);
        }

        // Pendentes é a única lista com interação (checkboxes) — enquanto
        // alguém está selecionando pra remover, não mexe nela; só
        // contagem/Processando continuam ao vivo. Retoma no próximo tick
        // depois que a pessoa sair do modo de seleção.
        if (modoSelecaoAtivo) {
            return;
        }

        if (vazioPendentesEl) {
            vazioPendentesEl.hidden = estado.pendentes.length > 0;
        }
        if (botaoSelecionarEl) {
            botaoSelecionarEl.hidden = estado.pendentes.length === 0;
        }
        // estado.pendentes já vem como [{nome, status}] do servidor.
        sincronizarLista(listaPendentesEl, estado.pendentes, true);
    }

    function consultarEstado() {
        if (document.hidden) {
            return;
        }

        fetch(form ? form.action.replace(/\/upload$/, "/estado") : "fila/estado")
            .then(function (resposta) { return resposta.ok ? resposta.json() : null; })
            .then(function (estado) {
                if (estado) {
                    aplicarEstado(estado);
                }
            })
            .catch(function () {
                // Silencioso de propósito — uma falha de rede pontual no
                // polling não deveria virar um aviso pra quem só está
                // olhando a fila; o próximo tick tenta de novo sozinho.
            });
    }

    setInterval(consultarEstado, INTERVALO_POLLING_MS);

    // Ao voltar pra essa aba depois de um tempo fora, busca na hora em
    // vez de esperar o próximo tick do setInterval (até 5s de atraso) —
    // sensação de "atualizado na hora que eu olhei", não "espera um
    // pouco depois de eu olhar".
    document.addEventListener("visibilitychange", function () {
        if (!document.hidden) {
            consultarEstado();
        }
    });
})();
