(function () {
    "use strict";

    var campoBusca = document.querySelector(".campo-busca");
    var abas = document.querySelectorAll(".aba-relatorios-robo");
    var itens = document.querySelectorAll(".relatorio-item");
    var avisoVazio = document.querySelector(".filtro-vazio");
    var avisoSemSolicitacoes = document.getElementById("aviso-sem-solicitacoes-robo");
    var listaEl = document.getElementById("lista-relatorios-robo");
    var campoDataDe = document.getElementById("filtro-data-de");
    var campoDataAte = document.getElementById("filtro-data-ate");
    var campoSolicitante = document.getElementById("filtro-solicitante");

    if (!campoBusca || !itens.length) {
        return;
    }

    // Henrique, 2026-09-02: quem nunca solicitou nada ao Robô não tem
    // como aparecer pré-selecionado no dropdown "Solicitado por" (não
    // existe opção pra isso, de propósito — ver relatorios_robo.py). O
    // jeito de mesmo assim abrir a tela "filtrada em mim" é um flag à
    // parte, sem depender de nenhum valor de filtro de verdade: começa
    // forçando a lista inteira escondida (com a mensagem dedicada no
    // lugar), e qualquer interação real com QUALQUER filtro desliga isso
    // de vez — a pessoa nunca fica presa, só não vê o acervo inteiro sem
    // querer logo de cara.
    var filtroInicialForcado = !!(avisoSemSolicitacoes && avisoSemSolicitacoes.dataset.ativo === "true");

    // "Todos" é a aba padrão (Henrique, 2026-08-21, mudou de ideia em
    // relação à decisão de 2026-08-08 abaixo) — mostra do mais antigo
    // pro mais novo (column-reverse no CSS), diferente das outras 3
    // abas (Sucesso, Revisão, Erro — essas continuam mais novo primeiro,
    // "em ordem de grau de fudido").
    var statusAtivo = "todos";

    function aplicarFiltros() {
        if (filtroInicialForcado) {
            itens.forEach(function (item) { item.style.display = "none"; });
            if (avisoVazio) { avisoVazio.style.display = "none"; }
            // "block", não "" — esses <p> nascem com o atributo `hidden`
            // (não só sem classe de display nenhuma), e limpar o inline
            // style só devolve o controle pro `[hidden]` nativo do
            // navegador, que continua escondendo. Precisa de um valor
            // concreto pra vencer de vez (mesma pegadinha catalogada em
            // base.css, ex: .bandeja-apps[hidden]).
            if (avisoSemSolicitacoes) { avisoSemSolicitacoes.style.display = "block"; }
            return;
        }

        if (avisoSemSolicitacoes) {
            avisoSemSolicitacoes.style.display = "none";
        }

        var termo = campoBusca.value.trim().toLowerCase();
        var dataDe = campoDataDe ? campoDataDe.value : "";
        var dataAte = campoDataAte ? campoDataAte.value : "";
        var solicitanteId = campoSolicitante ? campoSolicitante.value : "";
        var visiveis = 0;

        itens.forEach(function (item) {
            var passaStatus = statusAtivo === "todos" || item.dataset.status === statusAtivo;
            var passaBusca = !termo || item.dataset.busca.indexOf(termo) !== -1;
            // Comparação de string funciona direto porque data-criado-em
            // e o <input type="date"> usam o mesmo formato ISO (AAAA-MM-DD).
            var passaData = (!dataDe || item.dataset.criadoEm >= dataDe)
                && (!dataAte || item.dataset.criadoEm <= dataAte);
            // Henrique, diretoria, 2026-08-27: filtro "Solicitado por" —
            // data-solicitante-id vem vazio quando o arquivo apareceu na
            // pasta por fora do upload da tela (ver job.solicitante_id,
            // carregado desde ChecagemFila.solicitante_id/
            // checagem_fila.registrar_pendente).
            var passaSolicitante = !solicitanteId || item.dataset.solicitanteId === solicitanteId;
            var mostrar = passaStatus && passaBusca && passaData && passaSolicitante;

            // Mesma pegadinha do [hidden] vs display de autor já
            // resolvida em relatorios_manuais.js — style.display direto
            // em vez do atributo.
            item.style.display = mostrar ? "" : "none";

            if (mostrar) {
                visiveis += 1;
            }
        });

        if (avisoVazio) {
            // Mesmo motivo do "block" acima — este <p> também nasce com
            // `hidden`.
            avisoVazio.style.display = visiveis === 0 ? "block" : "none";
        }
    }

    campoBusca.addEventListener("input", function () {
        filtroInicialForcado = false;
        aplicarFiltros();
    });

    // Henrique, 2026-08-26: o calendário de cada campo se ajusta pelo
    // que já foi escolhido no outro — não faz sentido "Até" permitir uma
    // data antes de "De" (nem o contrário). Quem for preenchido PRIMEIRO
    // vira o limite do outro; limpar o campo remove o limite de novo.
    if (campoDataDe) {
        campoDataDe.addEventListener("change", function () {
            filtroInicialForcado = false;
            if (campoDataAte) {
                campoDataAte.min = campoDataDe.value || "";
            }
            aplicarFiltros();
        });
    }
    if (campoDataAte) {
        campoDataAte.addEventListener("change", function () {
            filtroInicialForcado = false;
            if (campoDataDe) {
                campoDataDe.max = campoDataAte.value || "";
            }
            aplicarFiltros();
        });
    }

    if (campoSolicitante) {
        campoSolicitante.addEventListener("change", function () {
            filtroInicialForcado = false;
            aplicarFiltros();
        });
    }

    abas.forEach(function (aba) {
        aba.addEventListener("click", function () {
            filtroInicialForcado = false;
            abas.forEach(function (a) { a.classList.remove("aba-relatorios-robo-ativa"); });
            aba.classList.add("aba-relatorios-robo-ativa");
            statusAtivo = aba.dataset.status;

            if (listaEl) {
                listaEl.classList.toggle("lista-relatorios-invertida", statusAtivo === "todos");
            }

            aplicarFiltros();
        });
    });

    // Clicar no nome/meta do relatório baixa, igual à Relatórios manual
    // — .truncavel é tratado globalmente em base.js, não conflita.
    document.querySelectorAll(".relatorio-info-clicavel").forEach(function (bloco) {
        bloco.addEventListener("click", function () {
            window.location = bloco.dataset.download;
        });
    });

    // Nome do PDF de origem — ver comentário equivalente em
    // relatorios_manuais.js (Relatórios URGENTES) — mesma lógica.
    document.querySelectorAll(".link-pdf-original").forEach(function (link) {
        link.addEventListener("click", function (evento) {
            evento.stopPropagation();
        });
    });

    // Deep-link do botão "Ir ao relatório" (Conferências manuais,
    // web/routes/gerar_relatorio.py, ?processo=...) — pré-preenche a busca, troca
    // pra aba certa (o item pode estar em Sucesso/Revisão/Erro — mesmo
    // com "Todos" sendo o padrão, um deep-link deve destacar a aba
    // específica do item, não deixar em "Todos") e dá scroll+destaque no
    // item certo.
    var processoInicial = campoBusca.dataset.processoInicial;
    if (processoInicial) {
        var alvoPreCheck = document.querySelector('.relatorio-item[data-processo="' + CSS.escape(processoInicial) + '"]');
        if (alvoPreCheck) {
            var abaCerta = document.querySelector('.aba-relatorios-robo[data-status="' + alvoPreCheck.dataset.status + '"]');
            if (abaCerta) {
                abas.forEach(function (a) { a.classList.remove("aba-relatorios-robo-ativa"); });
                abaCerta.classList.add("aba-relatorios-robo-ativa");
                statusAtivo = alvoPreCheck.dataset.status;
            }
        }
        campoBusca.value = processoInicial;
        // Um deep-link sempre vence — nunca pode ficar escondido atrás do
        // filtro "só o que é meu" (padrão ou forçado), mesmo relatório
        // sendo de outra pessoa.
        filtroInicialForcado = false;
    }

    // Henrique, 2026-09-02: valor INICIAL do dropdown "Solicitado por" —
    // só pra quem tem pelo menos 1 solicitação de verdade (ver
    // sem_solicitacoes_proprias/filtroInicialForcado acima, o caso
    // oposto). Continua trocável livremente depois, igual ao "Solicitados
    // por mim" da tela manual.
    var solicitantePadrao = campoSolicitante ? campoSolicitante.dataset.padrao : "";
    if (solicitantePadrao && !processoInicial) {
        campoSolicitante.value = solicitantePadrao;
    }

    // "Todos" é o padrão agora — aplica a inversão de lista já na carga
    // inicial, não só quando alguém clica na aba (mesmo motivo do toggle
    // dentro do listener de clique acima).
    if (listaEl) {
        listaEl.classList.toggle("lista-relatorios-invertida", statusAtivo === "todos");
    }

    aplicarFiltros();

    if (processoInicial) {
        var alvo = document.querySelector('.relatorio-item[data-processo="' + CSS.escape(processoInicial) + '"]');
        if (alvo) {
            alvo.scrollIntoView({ behavior: "smooth", block: "center" });
            alvo.classList.add("relatorio-item-destacado");
            setTimeout(function () { alvo.classList.remove("relatorio-item-destacado"); }, 2400);
        }
    }

    // ---------------------------------------------------------------
    // "Baixar todos" + modo de seleção (checkboxes, baixar/excluir em
    // lote) — Henrique, 2026-09-02. Mesmo padrão de seleção já usado na
    // Fila do Robô (fila.js): botão "Selecionar" liga o modo, checkboxes
    // ficam escondidos até lá, "Selecionar todos" e o(s) botão(ões) de
    // ação habilitam/desabilitam junto com a contagem de marcados.
    // ---------------------------------------------------------------
    var botaoBaixarTodos = document.getElementById("botao-baixar-todos-robo");
    var botaoSelecionarRobo = document.getElementById("botao-selecionar-robo");
    var acoesSelecaoRobo = document.getElementById("relatorios-robo-acoes-selecao");
    var checkTodosRobo = document.getElementById("check-selecionar-todos-robo");
    var botaoBaixarSelecionados = document.getElementById("botao-baixar-selecionados-robo");
    var botaoExcluirSelecionados = document.getElementById("botao-excluir-selecionados-robo");
    var botaoCancelarSelecaoRobo = document.getElementById("botao-cancelar-selecao-robo");
    var formBaixarLoteRobo = document.getElementById("form-baixar-lote-robo");
    var formExcluirLoteRobo = document.getElementById("form-excluir-lote-robo");

    // Um relatório só entra em "baixar" quando tem arquivo de verdade —
    // Henrique, 2026-09-02: "o botão não pode incluir os com erro (revisão
    // sim, erro não)". `.botao-download:not(.botao-fantasma)` já reflete
    // isso (o template só desenha o ícone de baixar quando `job.
    // relatorio_path` existe, e "erro" nunca tem esse campo preenchido) —
    // checa os dois de propósito redundante, igual o backend faz.
    function relatorioTemArquivo(item) {
        return item.dataset.status !== "erro" && !!item.querySelector(".botao-download:not(.botao-fantasma)");
    }

    function submeterIdsEmLote(form, ids) {
        form.innerHTML = "";
        ids.forEach(function (id) {
            var campo = document.createElement("input");
            campo.type = "hidden";
            campo.name = "ids";
            campo.value = id;
            form.appendChild(campo);
        });
        form.submit();
    }

    // Henrique, 2026-09-02: "confirmação antes de baixar, pra evitar
    // download acidental de uma pasta GIGANTE" — mesmo modal já usado em
    // "Excluir selecionados", só que sem o vermelho de perigo (baixar não
    // é destrutivo, só pode ser sem querer/grande demais).
    function confirmarEBaixar(form, ids) {
        if (ids.length === 0) {
            return;
        }

        var mensagem = ids.length === 1
            ? "Baixar 1 relatório?"
            : "Baixar " + ids.length + " relatórios num arquivo .zip?";

        window.confirmarAcao(mensagem, function () {
            submeterIdsEmLote(form, ids);
        });
    }

    if (botaoBaixarTodos && formBaixarLoteRobo) {
        botaoBaixarTodos.addEventListener("click", function () {
            // "Todos" aqui respeita o que a tela está mostrando NA HORA —
            // filtros de data/status/solicitante/busca já aplicados, não
            // o histórico inteiro.
            var ids = Array.prototype.filter.call(itens, function (item) {
                return item.style.display !== "none" && relatorioTemArquivo(item);
            }).map(function (item) { return item.dataset.jobId; });

            confirmarEBaixar(formBaixarLoteRobo, ids);
        });
    }

    if (botaoSelecionarRobo && acoesSelecaoRobo) {
        function obterChecksRobo() {
            return listaEl.querySelectorAll(".relatorio-item-check");
        }

        function idsMarcados() {
            return Array.prototype.filter.call(obterChecksRobo(), function (c) { return c.checked; })
                .map(function (c) { return c.dataset.jobId; });
        }

        function atualizarBotoesSelecaoRobo() {
            var checks = obterChecksRobo();
            var algumMarcado = Array.prototype.some.call(checks, function (c) { return c.checked; });
            var todosMarcados = checks.length > 0 && Array.prototype.every.call(checks, function (c) { return c.checked; });

            if (botaoBaixarSelecionados) { botaoBaixarSelecionados.disabled = !algumMarcado; }
            if (botaoExcluirSelecionados) { botaoExcluirSelecionados.disabled = !algumMarcado; }
            if (checkTodosRobo) { checkTodosRobo.checked = todosMarcados; }
        }

        function entrarModoSelecaoRobo() {
            // Henrique, 2026-09-02 (3ª rodada): "Selecionar" some de vez
            // (não só esmaece) — igual "Baixar todos" — pra dar lugar aos
            // botões novos da barra de seleção, sem ficar um botão
            // desabilitado sobrando em cima.
            botaoSelecionarRobo.hidden = true;
            acoesSelecaoRobo.hidden = false;
            if (botaoBaixarTodos) { botaoBaixarTodos.hidden = true; }
            listaEl.querySelectorAll(".relatorio-item-checkbox").forEach(function (c) { c.hidden = false; });
            atualizarBotoesSelecaoRobo();
        }

        function sairModoSelecaoRobo() {
            botaoSelecionarRobo.hidden = false;
            acoesSelecaoRobo.hidden = true;
            if (botaoBaixarTodos) { botaoBaixarTodos.hidden = false; }
            listaEl.querySelectorAll(".relatorio-item-checkbox").forEach(function (c) { c.hidden = true; });
            obterChecksRobo().forEach(function (c) { c.checked = false; });
            if (checkTodosRobo) { checkTodosRobo.checked = false; }
        }

        botaoSelecionarRobo.addEventListener("click", entrarModoSelecaoRobo);
        botaoCancelarSelecaoRobo.addEventListener("click", sairModoSelecaoRobo);

        if (checkTodosRobo) {
            checkTodosRobo.addEventListener("change", function () {
                obterChecksRobo().forEach(function (c) { c.checked = checkTodosRobo.checked; });
                atualizarBotoesSelecaoRobo();
            });
        }

        // Delegação no container (não um listener por checkbox) — mesmo
        // motivo de fila.js: mais simples de manter, e já cobre qualquer
        // linha que passe a existir se essa lista um dia virar dinâmica.
        listaEl.addEventListener("change", function (evento) {
            if (evento.target.classList.contains("relatorio-item-check")) {
                atualizarBotoesSelecaoRobo();
            }
        });

        if (botaoBaixarSelecionados && formBaixarLoteRobo) {
            botaoBaixarSelecionados.addEventListener("click", function () {
                confirmarEBaixar(formBaixarLoteRobo, idsMarcados());
            });
        }

        if (botaoExcluirSelecionados && formExcluirLoteRobo) {
            botaoExcluirSelecionados.addEventListener("click", function () {
                var ids = idsMarcados();
                if (ids.length === 0) {
                    return;
                }

                var mensagem = ids.length === 1
                    ? "Excluir 1 relatório selecionado permanentemente? O arquivo e o PDF de origem serão apagados. Essa ação não pode ser desfeita."
                    : "Excluir " + ids.length + " relatórios selecionados permanentemente? Os arquivos e os PDFs de origem serão apagados. Essa ação não pode ser desfeita.";

                window.confirmarAcao(mensagem, function () {
                    submeterIdsEmLote(formExcluirLoteRobo, ids);
                }, true);
            });
        }
    }
})();
