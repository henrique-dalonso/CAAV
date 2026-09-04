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

    function validarFormularioAntesDeEnviar(form) {
        var primeiroInvalido = null;

        form.querySelectorAll("[required]").forEach(function (campo) {
            if (!campo.value || !campo.value.trim()) {
                mostrarErro(campo, "Preencha este campo.");
                if (!primeiroInvalido) { primeiroInvalido = campo; }
            } else {
                limparErro(campo);
            }
        });

        return primeiroInvalido;
    }

    // -----------------------------------------------------------------
    // Anexos (home.html) — mesma arquitetura do upload da Fila do Robô
    // (app/ferramentas/extratus/web/static/fila.js: array próprio como
    // fonte da verdade, cartão com ícone/nome/tamanho/remover, dedupe
    // client-side avisando por toast, DataTransfer pra sincronizar o
    // <input> real), adaptada pro espaço menor e pros 4 tipos de arquivo
    // do Crivus. Henrique, 2026-09-04.
    // -----------------------------------------------------------------

    var dropzone = document.getElementById("dropzone-crivus");

    if (dropzone) {
        var campoArquivos = document.getElementById("arquivos");
        var cliqueEl = document.getElementById("dropzone-crivus-clique");
        var cartoesEl = document.getElementById("dropzone-crivus-cartoes");
        var botaoLimpar = document.getElementById("botao-limpar-anexos");

        var arquivos = []; // [{ id, file }] — fonte da verdade
        var proximoId = 1;

        var EXTENSOES_ACEITAS = [".pdf", ".docx", ".png", ".jpg", ".jpeg"];
        var LIMITE_TAMANHO_BYTES = 5 * 1024 * 1024;
        var maximoTexto = dropzone.dataset.maximo;
        var MAXIMO_ARQUIVOS = maximoTexto ? parseInt(maximoTexto, 10) : null;

        function extensaoDe(nomeArquivo) {
            var pontoIndice = nomeArquivo.lastIndexOf(".");
            return pontoIndice === -1 ? "" : nomeArquivo.slice(pontoIndice).toLowerCase();
        }

        function formatarTamanho(bytes) {
            if (bytes < 1024) { return bytes + " B"; }
            if (bytes < 1024 * 1024) { return (bytes / 1024).toFixed(0) + " KB"; }
            return (bytes / (1024 * 1024)).toFixed(1).replace(".", ",") + " MB";
        }

        function nomeJaSelecionado(nome, tamanho) {
            return arquivos.some(function (item) { return item.file.name === nome && item.file.size === tamanho; });
        }

        // Mesma folha de papel do ícone de PDF do Extratus (fila.js),
        // generalizada pra mostrar a extensão real na etiqueta colorida,
        // com uma cor por tipo — Henrique pediu miniatura "da mesmíssima
        // forma que no Extratus, adaptada pra esse espaço".
        function iconeArquivoSVG(extensao) {
            var cores = {
                ".pdf": { cor: "#dc2626", rotulo: "PDF" },
                ".docx": { cor: "#2563eb", rotulo: "DOC" },
                ".png": { cor: "#7c3aed", rotulo: "PNG" },
                ".jpg": { cor: "#7c3aed", rotulo: "JPG" },
                ".jpeg": { cor: "#7c3aed", rotulo: "JPG" },
            };
            var info = cores[extensao] || { cor: "#6b7280", rotulo: "?" };

            return '<svg viewBox="0 0 24 28" fill="none" aria-hidden="true" style="user-select:none;">' +
                '<path d="M3 1.5h12.5L21 7v19a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 26V3A1.5 1.5 0 0 1 4.5 1.5Z" ' +
                'fill="var(--cor-cartao)" stroke="var(--cor-texto-suave)" stroke-width="1.3"/>' +
                '<path d="M15.5 1.5V7H21" fill="none" stroke="var(--cor-texto-suave)" stroke-width="1.3" stroke-linejoin="round"/>' +
                '<rect x="4.5" y="16" width="15" height="7" rx="1.2" fill="' + info.cor + '"/>' +
                '<text x="12" y="21.2" text-anchor="middle" font-family="Arial, sans-serif" font-size="6" font-weight="700" fill="white">' + info.rotulo + '</text>' +
                '</svg>';
        }

        function sincronizarInputReal() {
            var dt = new DataTransfer();
            arquivos.forEach(function (item) { dt.items.add(item.file); });
            campoArquivos.files = dt.files;
        }

        function criarBotaoRemover(id, nome) {
            var botao = document.createElement("button");
            botao.type = "button";
            botao.className = "anexo-cartao-remover";
            botao.setAttribute("aria-label", "Remover " + nome);
            botao.textContent = "×";
            botao.addEventListener("click", function (evento) {
                evento.preventDefault();
                evento.stopPropagation();
                arquivos = arquivos.filter(function (item) { return item.id !== id; });
                sincronizarInputReal();
                renderizar();
            });
            return botao;
        }

        function criarCartao(item) {
            var cartao = document.createElement("div");
            cartao.className = "anexo-cartao";

            var icone = document.createElement("span");
            icone.className = "anexo-cartao-icone";
            icone.innerHTML = iconeArquivoSVG(extensaoDe(item.file.name));

            var nome = document.createElement("span");
            nome.className = "anexo-cartao-nome truncavel";
            nome.dataset.dica = item.file.name;
            nome.textContent = item.file.name;

            var tamanho = document.createElement("span");
            tamanho.className = "anexo-cartao-tamanho";
            tamanho.textContent = formatarTamanho(item.file.size);

            cartao.appendChild(criarBotaoRemover(item.id, item.file.name));
            cartao.appendChild(icone);
            cartao.appendChild(nome);
            cartao.appendChild(tamanho);
            return cartao;
        }

        function renderizar() {
            cartoesEl.innerHTML = "";

            if (!arquivos.length) {
                cliqueEl.hidden = false;
                cartoesEl.hidden = true;
                botaoLimpar.hidden = true;
                return;
            }

            cliqueEl.hidden = true;
            cartoesEl.hidden = false;
            botaoLimpar.hidden = false;

            // Mostra até 3 lado a lado; o resto (só acontece sem limite
            // fixo, coordenador/admin) vira "+N" — mesmo padrão do
            // Extratus (popover "+N" da Fila do Robô), versão enxuta.
            var LIMITE_VISUAL = 3;
            var visiveis = arquivos.slice(0, LIMITE_VISUAL);
            var resto = arquivos.length - visiveis.length;

            visiveis.forEach(function (item) {
                cartoesEl.appendChild(criarCartao(item));
            });

            if (resto > 0) {
                var maisChip = document.createElement("span");
                maisChip.className = "anexo-cartao anexo-cartao-mais";
                maisChip.textContent = "+" + resto;
                cartoesEl.appendChild(maisChip);
            }
        }

        function adicionarArquivos(lista) {
            var recusados = []; // [{ nome, motivo }]

            Array.prototype.forEach.call(lista, function (file) {
                var extensao = extensaoDe(file.name);

                if (EXTENSOES_ACEITAS.indexOf(extensao) === -1) {
                    recusados.push({ nome: file.name, motivo: "Tipo de arquivo não aceito (PDF, DOCX, PNG ou JPEG)" });
                    return;
                }

                if (file.size > LIMITE_TAMANHO_BYTES) {
                    recusados.push({ nome: file.name, motivo: "Maior que 5MB" });
                    return;
                }

                if (nomeJaSelecionado(file.name, file.size)) {
                    recusados.push({ nome: file.name, motivo: "Já foi anexado" });
                    return;
                }

                if (MAXIMO_ARQUIVOS && arquivos.length >= MAXIMO_ARQUIVOS) {
                    recusados.push({ nome: file.name, motivo: "Limite de " + MAXIMO_ARQUIVOS + " arquivos atingido" });
                    return;
                }

                arquivos.push({ id: proximoId++, file: file });
            });

            // Um erro só: cabe numa linha, com o motivo já junto. Vários de
            // uma vez: toast clicável com a lista nome+motivo — mesmo
            // critério do upload da Fila do Robô (fila.js).
            if (recusados.length === 1 && window.mostrarBanner) {
                window.mostrarBanner("\"" + recusados[0].nome + "\" não foi adicionado: " + recusados[0].motivo + ".", "erro");
            } else if (recusados.length > 1 && window.mostrarBannerDetalhado) {
                window.mostrarBannerDetalhado(
                    recusados.length + " arquivos não foram adicionados — clique pra ver os motivos",
                    recusados.map(function (r) { return { titulo: r.nome, detalhe: r.motivo }; }),
                    "erro"
                );
            }

            sincronizarInputReal();
            renderizar();
        }

        dropzone.addEventListener("click", function (evento) {
            if (evento.target.closest(".anexo-cartao-remover") || evento.target.closest(".anexo-cartao")) { return; }
            campoArquivos.click();
        });

        campoArquivos.addEventListener("change", function () {
            adicionarArquivos(campoArquivos.files);
            // Limpo pra sempre poder reabrir o mesmo arquivo (o browser
            // não dispara "change" de novo se o valor não mudar).
            campoArquivos.value = "";
        });

        botaoLimpar.addEventListener("click", function () {
            arquivos = [];
            sincronizarInputReal();
            renderizar();
        });
    }

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

    // -----------------------------------------------------------------
    // Navegação sem reload — Henrique, 2026-09-04: "não deve ter reload
    // da página algum, deve ser tudo sequencial". Todo formulário do
    // Crivus (analisar, salvar item, desnecessário, reverter, ciência do
    // alerta, concluir) vai por fetch — o servidor continua devolvendo
    // páginas HTML completas via redirect (nada mudou nas rotas), só o
    // JS troca #crivus-conteudo em vez de deixar o navegador navegar de
    // verdade. Cabeçalho/menu/sino nunca são tocados (ficam fora de
    // #crivus-conteudo), então o estado deles não se perde na troca.
    // -----------------------------------------------------------------

    function elementoConteudo() {
        return document.getElementById("crivus-conteudo");
    }

    function substituirConteudo(html, novaUrl, novoTitulo) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        var novoConteudo = doc.getElementById("crivus-conteudo");
        var atual = elementoConteudo();

        if (novoConteudo && atual) {
            atual.innerHTML = novoConteudo.innerHTML;
        }

        if (novoTitulo) { document.title = novoTitulo; }
        if (novaUrl) { window.history.pushState({}, "", novaUrl); }
    }

    function mostrarCarregandoAnalise() {
        var atual = elementoConteudo();
        if (!atual) { return; }

        atual.innerHTML =
            '<div class="crivus-carregando">' +
            '<div class="crivus-carregando-barra"><div class="crivus-carregando-barra-interna"></div></div>' +
            '<p class="crivus-carregando-texto" id="crivus-carregando-texto">Realizando leitura</p>' +
            "</div>";

        var textoEl = document.getElementById("crivus-carregando-texto");
        var pontos = 0;
        return window.setInterval(function () {
            pontos = (pontos + 1) % 4;
            textoEl.textContent = "Realizando leitura" + ".".repeat(pontos);
        }, 450);
    }

    function eFormularioCrivus(form) {
        return form && form.action && form.action.indexOf("/crivus/leitor-individual") !== -1;
    }

    document.addEventListener("submit", function (evento) {
        var form = evento.target;
        if (!eFormularioCrivus(form)) { return; }

        evento.preventDefault();

        if (form.classList.contains("form-crivus")) {
            var invalido = validarFormularioAntesDeEnviar(form);
            if (invalido) {
                invalido.focus();
                return;
            }
        }

        var ehAnalise = form.classList.contains("form-crivus");
        var intervaloPontos = ehAnalise ? mostrarCarregandoAnalise() : null;

        var formData = new FormData(form);
        // formaction (botão "Marcar desnecessário" dentro do form de
        // "salvar") — FormData não sabe disso sozinho, precisa vir do
        // botão que efetivamente disparou o submit.
        var botaoSubmit = evento.submitter;
        var destino = (botaoSubmit && botaoSubmit.getAttribute("formaction")) || form.action;

        fetch(destino, { method: "POST", body: formData })
            .then(function (resposta) { return resposta.text().then(function (html) { return { html: html, url: resposta.url }; }); })
            .then(function (resultado) {
                if (intervaloPontos) { window.clearInterval(intervaloPontos); }
                var tituloDoc = new DOMParser().parseFromString(resultado.html, "text/html").title;
                substituirConteudo(resultado.html, resultado.url, tituloDoc);
            })
            .catch(function () {
                if (intervaloPontos) { window.clearInterval(intervaloPontos); }
                if (window.mostrarBanner) {
                    window.mostrarBanner("Falha de conexão — tente novamente.", "erro");
                }
            });
    });

    document.addEventListener("click", function (evento) {
        var link = evento.target.closest('a[href^="/crivus/leitor-individual"]');
        if (!link) { return; }

        evento.preventDefault();
        fetch(link.href)
            .then(function (resposta) { return resposta.text().then(function (html) { return { html: html, url: resposta.url }; }); })
            .then(function (resultado) {
                var tituloDoc = new DOMParser().parseFromString(resultado.html, "text/html").title;
                substituirConteudo(resultado.html, resultado.url, tituloDoc);
            })
            .catch(function () {
                window.location.href = link.href;
            });
    });
})();
