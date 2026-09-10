// Card agrupado "Extratus" na grade de Ferramentas — reaproveita o
// mesmo mecanismo de painel flutuante do resto do site (bandeja de
// apps, card de perfil, popover "+N" da Fila do Robô), em vez de
// duplicar lógica de abrir/fechar/Esc/clique-fora. Ver
// window.configurarAlternador em base.js.
document.addEventListener("DOMContentLoaded", function () {
    if (window.configurarAlternador) {
        window.configurarAlternador("botao-grupo-extratus", "lista-grupo-extratus");
    }
});
