// Card agrupado "Extratus" na grade de Ferramentas — reaproveita o
// mesmo mecanismo de painel flutuante do resto do site (bandeja de
// apps, card de perfil, popover "+N" da Fila do Robô), em vez de
// duplicar lógica de abrir/fechar/Esc/clique-fora. Ver
// window.configurarAlternador em base.js.
document.addEventListener("DOMContentLoaded", function () {
    if (!window.configurarAlternador) {
        return;
    }

    var fechar = window.configurarAlternador("botao-grupo-extratus", "lista-grupo-extratus");
    var painel = document.getElementById("lista-grupo-extratus");

    // configurarAlternador já fecha ao clicar FORA do painel — mas aqui
    // o painel é a própria camada de fundo escurecida (position:fixed,
    // inset:0), então clicar no fundo conta como "dentro" do painel pro
    // mecanismo genérico. Fecha também quando o clique é no fundo em si
    // (não na caixa por dentro), igual a qualquer modal do site.
    if (painel && fechar) {
        painel.addEventListener("click", function (evento) {
            if (evento.target === painel) {
                fechar(true);
            }
        });
    }
});
