(function () {
    "use strict";

    // ---------------------------------------------------------------
    // Upload — igual em espírito ao de fila.js (dropzone, cartões,
    // dedupe), mas bem mais simples: teto rígido de 5 arquivos (nunca
    // precisa do popover "+N" que a Fila tem), e a confirmação antes de
    // enviar é ESSENCIAL aqui (Henrique, 2026-08-11: "evitar
    // paspalhadas") — reaproveita o mesmo modal estilizado que
    // Conferências já usa em todo o site (form[data-confirm], ver
    // base.js), só que a mensagem muda dinamicamente com a quantidade de
    // arquivos selecionados. Envio é um POST de formulário de verdade
    // (não XHR) — depois de confirmado, a página recarrega e o polling
    // abaixo já mostra tudo em triagem.
    // ---------------------------------------------------------------

    var MAXIMO_ARQUIVOS = 5;
    var LIMITE_TAMANHO_BYTES = 100 * 1024 * 1024;

    var form = document.getElementById("form-upload-manual");
    var zona = document.getElementById("zona-soltar-manual");
    var campoUpload = document.getElementById("campo-pdfs-manual");
    var loteEl = document.getElementById("upload-lote-manual");
    var contagemEl = document.getElementById("upload-lote-contagem-manual");
    var cartoesEl = document.getElementById("upload-cartoes-manual");
    var botaoRemoverTodos = document.getElementById("botao-remover-todos-manual");
    var botaoEnviar = document.getElementById("botao-enviar-manual");

    if (form && zona && campoUpload && botaoEnviar) {
        var arquivos = []; // [{ id, file }]
        var proximoId = 1;

        function formatarTamanho(bytes) {
            if (bytes < 1024) { return bytes + " B"; }
            if (bytes < 1024 * 1024) { return (bytes / 1024).toFixed(0) + " KB"; }
            return (bytes / (1024 * 1024)).toFixed(1).replace(".", ",") + " MB";
        }

        function nomeJaSelecionado(nome) {
            return arquivos.some(function (item) { return item.file.name === nome; });
        }

        function sincronizarInputReal() {
            var dt = new DataTransfer();
            arquivos.forEach(function (item) { dt.items.add(item.file); });
            campoUpload.files = dt.files;
        }

        function iconePdfSVG() {
            return '<svg viewBox="0 0 24 28" fill="none" aria-hidden="true" style="user-select:none;">' +
                '<path d="M3 1.5h12.5L21 7v19a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 26V3A1.5 1.5 0 0 1 4.5 1.5Z" ' +
                'fill="var(--cor-cartao)" stroke="var(--cor-texto-suave)" stroke-width="1.3"/>' +
                '<path d="M15.5 1.5V7H21" fill="none" stroke="var(--cor-texto-suave)" stroke-width="1.3" stroke-linejoin="round"/>' +
                '<rect x="5" y="16" width="14" height="7" rx="1.2" fill="#dc2626"/>' +
                '<text x="12" y="21.2" text-anchor="middle" font-family="Arial, sans-serif" font-size="6.6" font-weight="700" fill="white">PDF</text>' +
                '</svg>';
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

        function atualizarTextoBotaoEnviar(total) {
            var textoBotao = document.getElementById("botao-enviar-manual-texto");
            if (!textoBotao) { return; }
            textoBotao.textContent = total === 0 ? "Enviar" : total === 1 ? "Enviar 1 PDF" : "Enviar " + total + " PDFs";
        }

        // Mensagem do modal de confirmação muda com a quantidade — lida
        // em tempo real por base.js na hora do submit (form.dataset.confirm),
        // não precisa recarregar listener nenhum.
        function atualizarConfirmacao(total) {
            if (total === 0) {
                form.dataset.confirm = "";
                return;
            }
            var plural = total === 1 ? "1 arquivo" : total + " arquivos";
            form.dataset.confirm = "Confirma o envio de " + plural + "? Depois de confirmado, o processamento " +
                "começa sozinho e não pode mais ser cancelado.";
        }

        function renderizar() {
            var total = arquivos.length;
            loteEl.hidden = total === 0;
            botaoEnviar.disabled = total === 0;
            botaoRemoverTodos.disabled = total === 0;
            atualizarConfirmacao(total);
            atualizarTextoBotaoEnviar(total);

            Array.prototype.slice.call(cartoesEl.querySelectorAll(".arquivo-cartao")).forEach(function (el) { el.remove(); });

            if (total === 0) {
                contagemEl.textContent = "Nenhum arquivo selecionado.";
                return;
            }

            arquivos.forEach(function (item) {
                cartoesEl.appendChild(criarCartao(item));
            });

            var totalBytes = arquivos.reduce(function (soma, item) { return soma + item.file.size; }, 0);
            var rotulo = total === 1 ? "1 arquivo selecionado" : total + " arquivos selecionados";
            contagemEl.textContent = rotulo + " · " + formatarTamanho(totalBytes) + " no total";
        }

        function removerArquivo(id) {
            arquivos = arquivos.filter(function (item) { return item.id !== id; });
            sincronizarInputReal();
            renderizar();
        }

        function removerTodos() {
            arquivos = [];
            sincronizarInputReal();
            renderizar();
        }

        function adicionarArquivos(lista) {
            var recusados = [];

            Array.prototype.forEach.call(lista, function (file) {
                if (arquivos.length >= MAXIMO_ARQUIVOS) {
                    recusados.push({ nome: file.name, motivo: "máximo de " + MAXIMO_ARQUIVOS + " arquivos por envio" });
                    return;
                }

                var nomeMinusculo = file.name.toLowerCase();

                if (!nomeMinusculo.endsWith(".pdf")) {
                    recusados.push({ nome: file.name, motivo: "não é um arquivo PDF" });
                    return;
                }

                if (file.size > LIMITE_TAMANHO_BYTES) {
                    recusados.push({ nome: file.name, motivo: "maior que 100MB" });
                    return;
                }

                if (nomeJaSelecionado(file.name)) {
                    recusados.push({ nome: file.name, motivo: "já foi selecionado" });
                    return;
                }

                arquivos.push({ id: proximoId++, file: file });
            });

            if (recusados.length === 1) {
                window.mostrarBanner("\"" + recusados[0].nome + "\" não foi adicionado: " + recusados[0].motivo + ".", "erro");
            } else if (recusados.length > 1) {
                window.mostrarBannerDetalhado(
                    recusados.length + " arquivos não foram adicionados — clique pra ver os motivos",
                    recusados.map(function (r) { return { titulo: r.nome, detalhe: r.motivo }; }),
                    "erro"
                );
            }

            sincronizarInputReal();
            renderizar();
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
    }

    // ---------------------------------------------------------------
    // Polling — GET /extratus/estado a cada poucos segundos, igual em
    // espírito ao de fila.js, mas mais simples: sem modo de seleção
    // (aqui não existe "remover da fila", só Conferências e dispensar
    // um card já concluído/com erro).
    // ---------------------------------------------------------------

    var INTERVALO_POLLING_MS = 4000;

    var listaPendentesEl = document.getElementById("lista-pendentes-manual");
    var listaProcessandoEl = document.getElementById("lista-processando-manual");
    var vazioPendentesEl = document.getElementById("vazio-pendentes-manual");
    var vazioProcessandoEl = document.getElementById("vazio-processando-manual");
    var contagemPendentesEl = document.getElementById("contagem-pendentes-manual");
    var contagemProcessandoEl = document.getElementById("contagem-processando-manual");
    var secaoConferenciasEl = document.getElementById("secao-conferencias");
    var listaConferenciasEl = document.getElementById("lista-conferencias");
    var contagemConferenciasEl = document.getElementById("contagem-conferencias");

    if (!listaPendentesEl || !listaProcessandoEl) {
        return;
    }

    // Lupa no fim da linha, só nos pendentes com bolinha vermelha —
    // mesmo padrão de fila.js (Henrique, 2026-08-07: "como adivinho que
    // dá pra passar o mouse em cima e clicar?").
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

    // Henrique, 2026-08-12: uma inconsistência (falha de leitura,
    // duplicidade, processo não encontrado) NÃO some de Pendentes — só
    // vira bolinha vermelha, igual à Fila do Motor, até ser resolvida em
    // Conferências. `preencherItemPendente` também é usado pra ATUALIZAR
    // um <li> que já existia (ex: laranja virando vermelho sem precisar
    // recriar o elemento), não só pra montar um novo.
    function preencherItemPendente(li, item) {
        li.dataset.id = item.id;
        li.innerHTML = "";

        li.classList.toggle("fila-item-clicavel", !!item.aguardando_conferencia);
        if (item.aguardando_conferencia) {
            li.dataset.dica = "Clique para ver em 'Conferências'";
        } else {
            delete li.dataset.dica;
        }

        var bolinha = document.createElement("span");
        bolinha.className = "bolinha-status " + (item.aguardando_conferencia ? "bolinha-vermelha" : "bolinha-laranja");
        bolinha.dataset.dica = item.aguardando_conferencia ? "Aguardando conferência" : "Em triagem";
        bolinha.setAttribute("aria-label", bolinha.dataset.dica);
        li.appendChild(bolinha);

        var nomeSpan = document.createElement("span");
        nomeSpan.className = "fila-item-nome";
        nomeSpan.dataset.dica = item.nome;
        nomeSpan.textContent = item.nome;
        li.appendChild(nomeSpan);

        if (item.aguardando_conferencia) {
            li.appendChild(criarIconeVerConferencia());
        }
    }

    function criarItemPendente(item) {
        var li = document.createElement("li");
        preencherItemPendente(li, item);
        return li;
    }

    // Também usado pra ATUALIZAR um item que já existia na lista (ex:
    // "processando" virando "concluido" sem esperar um F5) — mesma razão
    // de preencherItemPendente acima.
    function preencherItemProcessando(li, item) {
        li.dataset.id = item.id;
        li.innerHTML = "";

        var bolinha = document.createElement("span");
        bolinha.className = "bolinha-status";
        li.appendChild(bolinha);

        var nomeSpan = document.createElement("span");
        nomeSpan.className = "fila-item-nome";
        nomeSpan.dataset.dica = item.nome;
        nomeSpan.textContent = item.nome;
        li.appendChild(nomeSpan);

        if (item.status === "concluido") {
            bolinha.classList.add("bolinha-verde");
            bolinha.dataset.dica = "Concluído";
            bolinha.setAttribute("aria-label", "Concluído");

            var link = document.createElement("a");
            link.className = "botao-minimal";
            link.href = "/extratus/relatorios?processo=" + encodeURIComponent(item.processo_detectado || "");
            link.textContent = "Ver relatório";
            li.appendChild(link);

            li.appendChild(criarBotaoDispensar(item.id));
        } else if (item.status === "erro") {
            bolinha.classList.add("bolinha-vermelha");
            bolinha.dataset.dica = item.erro_mensagem || "Falha no processamento";
            bolinha.setAttribute("aria-label", "Erro");

            var aviso = document.createElement("span");
            aviso.className = "aviso-discreto";
            aviso.textContent = item.erro_mensagem || "Falha no processamento.";
            li.appendChild(aviso);

            li.appendChild(criarBotaoDispensar(item.id));
        } else {
            bolinha.classList.add("bolinha-verde");
            bolinha.dataset.dica = "Gerando relatório";
            bolinha.setAttribute("aria-label", "Gerando relatório");
        }
    }

    function criarItemProcessando(item) {
        var li = document.createElement("li");
        preencherItemProcessando(li, item);
        return li;
    }

    function criarBotaoDispensar(id) {
        var botao = document.createElement("button");
        botao.type = "button";
        botao.className = "botao-remover-fila botao-dispensar-processamento";
        botao.dataset.id = id;
        botao.dataset.dica = "Tirar da lista";
        botao.textContent = "×";
        return botao;
    }

    // "atualizarItem" (opcional) é chamado nos itens que JÁ existiam na
    // lista — sem ele, um <li> criado como "Em triagem" (laranja) nunca
    // saberia virar "Aguardando conferência" (vermelho) sozinho, só com
    // F5 (bug real reportado por Henrique, 2026-08-12: "esses pendentes
    // ficou EXCLUSIVAMENTE para exibir os em triagem no momento").
    function sincronizarLista(listaEl, itensNovos, criarItem, atualizarItem) {
        var existentes = {};
        Array.prototype.forEach.call(listaEl.children, function (li) {
            existentes[li.dataset.id] = li;
        });

        var itemPorId = {};
        itensNovos.forEach(function (item) { itemPorId[String(item.id)] = item; });

        Object.keys(existentes).forEach(function (id) {
            if (!(id in itemPorId)) {
                existentes[id].remove();
            }
        });

        itensNovos.forEach(function (item) {
            var chave = String(item.id);
            var existente = existentes[chave];

            if (existente) {
                if (atualizarItem) {
                    atualizarItem(existente, item);
                }
            } else {
                listaEl.appendChild(criarItem(item));
            }
        });
    }

    function criarItemConferencia(item) {
        var li = document.createElement("li");
        li.className = "conferencia-item";
        li.dataset.id = item.id;
        li.dataset.nome = item.nome;

        var info = document.createElement("div");
        info.className = "conferencia-item-info";

        var nomeEl = document.createElement("span");
        nomeEl.className = "conferencia-item-nome truncavel";
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

        if (item.tipo === "duplicado_relatorio") {
            var linkRelatorio = document.createElement("a");
            linkRelatorio.className = "botao-minimal";
            linkRelatorio.href = (item.link_relatorio || "/extratus/relatorios") + "?processo=" + encodeURIComponent(item.processo_detectado || "");
            linkRelatorio.dataset.dica = "Abre o relatório já existente pra esse processo";
            linkRelatorio.textContent = "Ir ao relatório";
            acoes.appendChild(linkRelatorio);
        }

        var formAprovar = document.createElement("form");
        formAprovar.method = "post";
        formAprovar.action = "/extratus/conferencia/" + item.id + "/aprovar";
        formAprovar.className = "form-conferencia";

        var dicaAprovar;

        if (item.tipo === "processo_nao_encontrado" || item.tipo === "falha_leitura") {
            formAprovar.classList.add("form-conferencia-manual");
            dicaAprovar = "Libera esse arquivo pra gerar o relatório, com o número de processo informado";

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

            campo.appendChild(input);
            formAprovar.appendChild(campo);
        } else {
            formAprovar.dataset.confirm = "Confirma que quer gerar o relatório de " + item.nome + " mesmo assim?";
            dicaAprovar = "Libera esse arquivo pra gerar o relatório, mesmo com a inconsistência encontrada";
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
        formDescartar.action = "/extratus/conferencia/" + item.id + "/descartar";
        formDescartar.className = "form-conferencia";
        formDescartar.dataset.confirm = "Descartar " + item.nome + "? Essa ação não pode ser desfeita.";
        formDescartar.dataset.perigo = "true";

        var botaoDescartar = document.createElement("button");
        botaoDescartar.type = "submit";
        botaoDescartar.className = "botao-remover-fila botao-conferencia-descartar";
        botaoDescartar.textContent = "Descartar";
        botaoDescartar.dataset.dica = "Descarta esse arquivo pra sempre — não pode ser desfeito";
        formDescartar.appendChild(botaoDescartar);
        acoes.appendChild(formDescartar);

        li.appendChild(acoes);

        return li;
    }

    function sincronizarConferencias(itensNovos) {
        if (!listaConferenciasEl) { return; }

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

    // Delegado — cobre também card de Conferências montado depois via
    // polling (mesmo padrão de fila.js).
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
                input.required = true;
                input.focus();
            }
        }
    });

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
        return { texto: formatado, digitos: digitos };
    }

    document.addEventListener("input", function (evento) {
        var alvo = evento.target;

        if (!alvo.matches || !alvo.matches(".conferencia-campo-processo input")) {
            return;
        }

        var resultado = formatarProcessoCNJ(alvo.value);
        alvo.value = resultado.texto;

        if (resultado.digitos.length === 20) {
            var form = alvo.closest("form");
            var botao = form ? form.querySelector(".botao-conferencia-aprovar") : null;
            if (botao) { botao.focus(); }
        }
    });

    // Dispensar um card "Concluído"/"Erro" já finalizado — só remove da
    // tela (fetch, sem recarregar a página).
    document.addEventListener("click", function (evento) {
        var botao = evento.target.closest(".botao-dispensar-processamento");

        if (!botao) { return; }

        var id = botao.dataset.id;
        var li = botao.closest("li");

        fetch("/extratus/processamento/" + id + "/descartar", { method: "POST" })
            .then(function (resposta) {
                if (resposta.ok && li) { li.remove(); }
            })
            .catch(function () {});
    });

    // Clique num pendente com bolinha vermelha (aguardando conferência)
    // leva até o card correspondente lá em cima — mesmo padrão de
    // fila.js, só que casando por data-id (mais direto que por nome).
    document.addEventListener("click", function (evento) {
        var linha = evento.target.closest(".fila-item-clicavel");

        if (!linha) { return; }

        var card = listaConferenciasEl
            ? listaConferenciasEl.querySelector('[data-id="' + CSS.escape(linha.dataset.id) + '"]')
            : null;

        if (!card) { return; }

        card.scrollIntoView({ behavior: "smooth", block: "center" });
        card.classList.remove("conferencia-item-destacado");
        void card.offsetWidth;
        card.classList.add("conferencia-item-destacado");
    });

    function aplicarEstado(estado) {
        if (contagemPendentesEl) {
            contagemPendentesEl.textContent = estado.pendentes.length;
        }
        if (contagemProcessandoEl) {
            contagemProcessandoEl.textContent = estado.processando.length;
        }
        if (vazioPendentesEl) {
            vazioPendentesEl.hidden = estado.pendentes.length > 0;
        }
        if (vazioProcessandoEl) {
            vazioProcessandoEl.hidden = estado.processando.length > 0;
        }

        sincronizarLista(listaPendentesEl, estado.pendentes, criarItemPendente, preencherItemPendente);
        sincronizarLista(listaProcessandoEl, estado.processando, criarItemProcessando, preencherItemProcessando);

        if (estado.conferencias) {
            sincronizarConferencias(estado.conferencias);
        }
    }

    function consultarEstado() {
        if (document.hidden) { return; }

        fetch("/extratus/estado")
            .then(function (resposta) { return resposta.ok ? resposta.json() : null; })
            .then(function (estado) {
                if (estado) { aplicarEstado(estado); }
            })
            .catch(function () {});
    }

    setInterval(consultarEstado, INTERVALO_POLLING_MS);

    document.addEventListener("visibilitychange", function () {
        if (!document.hidden) { consultarEstado(); }
    });
})();
