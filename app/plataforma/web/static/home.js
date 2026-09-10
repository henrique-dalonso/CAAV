// Card agrupado "Extratus" na grade de Ferramentas — reaproveita o
// mesmo mecanismo de painel flutuante do resto do site (bandeja de
// apps, card de perfil, popover "+N" da Fila do Robô), em vez de
// duplicar lógica de abrir/fechar/Esc/clique-fora. Ver
// window.configurarAlternador em base.js.
document.addEventListener("DOMContentLoaded", function () {
    if (!window.configurarAlternador) {
        return;
    }

    var painel = document.getElementById("lista-grupo-extratus");
    var botao = document.getElementById("botao-grupo-extratus");
    var caixa = painel ? painel.querySelector(".lista-grupo-caixa") : null;

    var fechar = window.configurarAlternador("botao-grupo-extratus", "lista-grupo-extratus");

    if (!painel || !botao || !caixa || !fechar) {
        return;
    }

    var MARGEM = 12;

    // Henrique, 2026-09-09: comportamento normal de dropdown — abre
    // ANCORADO embaixo do card sempre que couber; só quando não sobrar
    // espaço até o fim da janela (card perto do rodapé) é que cai pro
    // modo de tela cheia (.lista-grupo-extratus-central, ver CSS).
    // Roda no clique que ABRE o painel — configurarAlternador já deixou
    // "hidden" false nesse ponto (mesmo clique, listener registrado
    // antes), então dá pra medir a altura real da caixa antes do
    // navegador pintar qualquer coisa (sem "pulo" visível).
    function posicionar() {
        var retangulo = botao.getBoundingClientRect();
        var alturaCaixa = caixa.offsetHeight;
        var larguraCaixa = caixa.offsetWidth;
        var espacoAbaixo = window.innerHeight - retangulo.bottom;
        var cabeEmbaixo = espacoAbaixo >= (alturaCaixa + MARGEM);

        painel.classList.toggle("lista-grupo-extratus-central", !cabeEmbaixo);

        if (cabeEmbaixo) {
            var esquerda = Math.min(retangulo.left, window.innerWidth - larguraCaixa - MARGEM);
            esquerda = Math.max(esquerda, MARGEM);
            painel.style.top = (retangulo.bottom + 8) + "px";
            painel.style.left = esquerda + "px";
        } else {
            // Modo central cuida da própria posição via CSS (inset:0 +
            // flex centralizado) — limpa qualquer top/left do modo
            // ancorado de uma abertura anterior.
            painel.style.top = "";
            painel.style.left = "";
        }
    }

    botao.addEventListener("click", posicionar);

    // configurarAlternador já fecha ao clicar FORA do painel — mas no
    // modo central o painel é a própria camada de fundo (position:fixed
    // cobrindo a tela), então clicar no fundo conta como "dentro" do
    // painel pro mecanismo genérico. Fecha também quando o clique é no
    // fundo em si (não na caixa por dentro), igual a qualquer modal do
    // site. No modo ancorado isso nunca dispara (o painel não cobre a
    // tela, clicar fora dele já é tratado como "fora" normalmente).
    painel.addEventListener("click", function (evento) {
        if (evento.target === painel) {
            fechar(true);
        }
    });

    // Se a janela for redimensionada com o painel aberto, reavalia —
    // evita ficar preso num modo que não faz mais sentido pro novo
    // tamanho.
    window.addEventListener("resize", function () {
        if (!painel.hidden) {
            posicionar();
        }
    });

    // Trava o scroll do fundo só no modo central (ele cobre a tela,
    // igual a um modal — sem isso dava pra rolar a página por baixo do
    // painel). Observer em vez de travar/destravar em cada caminho que
    // fecha o painel (Esc, clique fora, clique no fundo, reabrir outro
    // painel) — todos eles chamam o `fechar` genérico compartilhado por
    // TODOS os painéis do site (configurarAlternador/alternadores em
    // base.js), então travar ali afetaria bandeja de apps/perfil/
    // notificações também; observar o estado real do painel evita isso
    // sem duplicar a lista de "todo caminho que fecha".
    var travandoScroll = false;
    function sincronizarScrollLock() {
        var deveTravar = !painel.hidden && painel.classList.contains("lista-grupo-extratus-central");
        if (deveTravar === travandoScroll) {
            return;
        }
        travandoScroll = deveTravar;
        document.body.style.overflow = deveTravar ? "hidden" : "";
    }
    new MutationObserver(sincronizarScrollLock).observe(painel, {
        attributes: true,
        attributeFilter: ["hidden", "class"],
    });
});
