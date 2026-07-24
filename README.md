# Centro de Experiência do Colaborador — Alonso & Verdiani

Plataforma interna do escritório. Hoje abriga uma ferramenta, o **Extratus**
(transforma processos judiciais grandes em relatórios curtos com parecer);
mais ferramentas entram depois, seguindo a mesma base de login e permissão.

> Status atual: a geração de relatório do Extratus ainda usa um texto de
> exemplo — a integração real com IA (Claude/GPT/Gemini) ainda não foi
> ligada. Tudo em volta (fila de PDFs, triagem por confiança, histórico,
> login, administração) já está funcionando de verdade.

## Estrutura do projeto

```
app/
├── plataforma/            ← o "sistema": login, usuários, permissão, admin
│   ├── db/                   (Usuario, Ferramenta, UsuarioFerramenta)
│   └── web/                   (site raiz, login, home, administração)
└── ferramentas/
    └── extratus/           ← tudo específico do Extratus
        ├── core/               (lógica: detectar processo, gerar docx...)
        ├── db/                  (Job — histórico de processamento)
        ├── web/                 (páginas do Extratus dentro do site)
        ├── config/              (prompt, template Word, config.json)
        ├── dados/               (entrada_pdfs, processados, erros...)
        ├── logs/
        └── scripts/

banco/plataforma.db        ← banco único, compartilhado entre sistema e ferramentas
scripts/criar_usuario.py   ← script de sistema (bootstrap do primeiro admin)
tests/                      (espelha a estrutura acima: plataforma/ e ferramentas/)
```

Cada ferramenta nova entra como uma pasta nova dentro de `app/ferramentas/`,
reaproveitando login/permissão/admin de `app/plataforma/` — sem duplicar nada.

## Como rodar (modo desenvolvimento, no seu próprio computador)

Sempre a partir da pasta principal do projeto:

```
.venv\Scripts\python -m uvicorn app.plataforma.web.main:app --reload
```

Ou clique duas vezes em `app\ferramentas\extratus\scripts\iniciar_servidor.bat`.

Acesse `http://127.0.0.1:8000` no navegador.

## Primeiro acesso

Ainda não existe nenhum usuário cadastrado na primeira vez que o banco é criado. Crie o primeiro (marque como administrador) rodando:

```
.venv\Scripts\python scripts\criar_usuario.py
```

Depois disso, novos usuários podem ser criados direto pela tela **Administração** (visível só pra quem é admin), sem precisar rodar script nenhum.

## O que cada pasta guarda

| Caminho | O que tem |
|---|---|
| `app/ferramentas/extratus/dados/entrada_pdfs/` | PDFs esperando processamento |
| `app/ferramentas/extratus/dados/processados/` | PDFs processados com confiança alta |
| `app/ferramentas/extratus/dados/revisao/` | PDFs processados, mas que pedem conferência humana (confiança média/baixa na identificação do processo) |
| `app/ferramentas/extratus/dados/erros/` | PDFs que falharam de verdade (não deram pra ler, gerar relatório, etc.) |
| `app/ferramentas/extratus/dados/relatorios_prontos/` | Os `.docx` gerados |
| `banco/plataforma.db` | Banco de dados único (usuários, permissões, histórico de processamento) |
| `app/ferramentas/extratus/logs/extratus.log` | Log de execução do Extratus |
| `app/ferramentas/extratus/config/config.json` | Nomes das pastas de dados acima, editável à mão |
| `app/ferramentas/extratus/config/instrucoes_relatorio.txt` | Prompt usado pela IA (escrito pelo Max) |
| `app/ferramentas/extratus/config/relatorio_template.docx` | Modelo Word do relatório final — pode ser editado direto no Word |
| `.env` | Segredos (chave de sessão, chave de IA) — **nunca commitar** |

## Rodar pela linha de comando, sem o site

Processa tudo que estiver na pasta de entrada de uma vez, sem precisar abrir o navegador:

```
.venv\Scripts\python -m app.ferramentas.extratus.main
```

## Rodar como serviço (pra ficar ligado sozinho, sem terminal aberto)

Isso ainda **não foi instalado** — é só o guia de quando for a hora de colocar isso rodando de verdade num computador do escritório, sem depender de alguém deixar um terminal aberto.

**Opção 1 — NSSM (recomendado, mais robusto)**

1. Baixe o [NSSM](https://nssm.cc/download) e extraia num lugar fixo (ex: `C:\nssm`).
2. Abra o `cmd` como administrador e rode:
   ```
   C:\nssm\nssm.exe install CentroExperiencia
   ```
3. Na janela que abre:
   - **Path**: caminho do `python.exe` dentro de `.venv\Scripts\`
   - **Startup directory**: a pasta do projeto
   - **Arguments**: `-m uvicorn app.plataforma.web.main:app --host 0.0.0.0 --port 8000`
4. Confirme. O serviço aparece no `services.msc` do Windows, liga sozinho com o computador, e reinicia sozinho se cair.

**Opção 2 — Agendador de Tarefas do Windows (mais simples, menos robusto)**

1. Abra o **Agendador de Tarefas** → Criar Tarefa.
2. Gatilho: "Ao iniciar o computador".
3. Ação: executar `app\ferramentas\extratus\scripts\iniciar_servidor.bat`.
4. Marque "Executar mesmo se o usuário não estiver conectado".

Diferença prática: o Agendador não reinicia sozinho se o programa travar no meio; o NSSM sim.

## Testes automatizados

```
.venv\Scripts\python -m pytest tests\ -v
```

## Segurança — o que já existe e o que ainda falta

Já existe: login por usuário/senha (com senha em hash, nunca em texto puro), controle de quais ferramentas cada pessoa pode usar, área de administração restrita a admins, chaves sensíveis fora do controle de versão.

Ainda falta antes de considerar isso "pronto pra produção pesada": HTTPS (hoje o tráfego não é criptografado, ok numa rede interna confiável, mas vale revisar), e a integração real de IA (com as decisões de custo/fornecedor e conformidade de dados ainda pendentes de aprovação da diretoria).
