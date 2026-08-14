// SharedWorker do sininho de notificações — Henrique, 2026-08-11: cada
// aba abrindo sua PRÓPRIA conexão SSE (EventSource) pra /notificacoes/
// eventos estourava o limite de 6 conexões simultâneas por site que o
// navegador impõe (Chrome/Edge/Firefox, HTTP/1.1) — com 5-6 abas do site
// abertas ao mesmo tempo (comum em uso/teste normal), qualquer navegação
// NOVA ficava "carregando" indefinidamente, esperando uma conexão livre,
// mesmo com o servidor respondendo instantaneamente (confirmado com
// medição direta contra o servidor: nada acima de 0.2s). Bug reproduzido
// ao vivo: a 6ª aba simplesmente não terminava de carregar.
//
// Este worker roda UMA VEZ por origem (compartilhado entre todas as
// abas do mesmo site, não uma cópia por aba) e é quem de fato mantém a
// conexão SSE aberta — só 1 conexão, não importa quantas abas estejam
// abertas. Cada aba (base.js) se conecta a este worker via MessagePort
// e recebe um aviso "atualizar" repassado daqui, sem precisar da sua
// própria conexão SSE.

var portas = [];
var eventos = null;

function garantirConexaoSSE() {
    if (eventos) {
        return;
    }

    eventos = new EventSource("/notificacoes/eventos");

    eventos.addEventListener("atualizar", function () {
        portas.forEach(function (porta) {
            porta.postMessage("atualizar");
        });
    });

    // EventSource reconecta sozinho se a conexão cair — mesmo
    // comportamento que já valia quando isso rodava direto em base.js.
}

self.addEventListener("connect", function (evento) {
    var porta = evento.ports[0];
    portas.push(porta);

    // A aba avisa (base.js, evento "pagehide") quando fecha/navega pra
    // fora — sem isso a lista de portas só cresce pela sessão inteira do
    // navegador, nunca encolhe (Rodada 12, achado de qualidade de
    // código). SharedWorker não tem um evento nativo de "porta fechou".
    porta.addEventListener("message", function (evento) {
        if (evento.data === "desconectar") {
            portas = portas.filter(function (p) { return p !== porta; });
        }
    });

    garantirConexaoSSE();

    porta.start();
});
