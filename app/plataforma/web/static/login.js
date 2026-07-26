// Fundo reage suavemente à posição do mouse (parallax discreto).
// Some sozinho pra quem pediu menos movimento no sistema (acessibilidade).
(function () {
    "use strict";

    // "Reduzir movimento" desliga a respiração automática de fundo (ver
    // login.css), mas não este efeito — ele só se move em resposta direta
    // ao que a pessoa está fazendo com o mouse, não é movimento ambiente.
    var raiz = document.documentElement;

    window.addEventListener("mousemove", function (evento) {
        var x = (evento.clientX / window.innerWidth - 0.5) * 2;
        var y = (evento.clientY / window.innerHeight - 0.5) * 2;

        raiz.style.setProperty("--mouse-x", x.toFixed(3));
        raiz.style.setProperty("--mouse-y", y.toFixed(3));
    });
})();
