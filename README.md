# Extratus

Ferramenta interna da **Alonso & Verdiani** pra transformar processos judiciais grandes em relatórios curtos com parecer. Faz parte do **Centro de Experiência do Colaborador**, o portal interno do escritório (hoje só o Extratus está disponível ali, mais ferramentas podem entrar depois).

> Status atual: a geração de relatório ainda usa um texto de exemplo — a integração real com IA (Claude/GPT/Gemini) ainda não foi ligada. Tudo em volta (fila de PDFs, triagem por confiança, histórico, login) já está funcionando de verdade.

## Como rodar (modo desenvolvimento, no seu próprio computador)

Sempre a partir da pasta principal do projeto:

```
.venv\Scripts\python -m uvicorn app.web.main:app --reload
```

Ou clique duas vezes em `scripts\iniciar_servidor.bat`.

Acesse `http://127.0.0.1:8000` no navegador.

## Primeiro acesso

Ainda não existe nenhum usuário cadastrado na primeira vez que o banco é criado. Crie o primeiro (marque como administrador) rodando:

```
.venv\Scripts\python scripts\criar_usuario.py
```

Depois disso, novos usuários podem ser criados direto pela tela **Administração** (visível só pra quem é admin), sem precisar rodar script nenhum.

## O que cada pasta guarda

| Pasta | O que tem |
|---|---|
| `entrada_pdfs/` | PDFs esperando processamento |
| `processados/` | PDFs processados com confiança alta |
| `revisao/` | PDFs processados, mas que pedem conferência humana (confiança média/baixa na identificação do processo) |
| `erros/` | PDFs que falharam de verdade (não deram pra ler, gerar relatório, etc.) |
| `relatorios_prontos/` | Os `.docx` gerados |
| `historico/extratus.db` | Banco de dados (histórico de processamento + usuários) |
| `logs/extratus.log` | Log de execução |
| `config/config.json` | Nomes das pastas acima, editável à mão |
| `config/instrucoes_relatorio.txt` | Prompt usado pela IA (escrito pelo Max) |
| `config/relatorio_template.docx` | Modelo Word do relatório final — pode ser editado direto no Word |
| `.env` | Segredos (chave de sessão, chave de IA) — **nunca commitar** |

## Rodar pela linha de comando, sem o site

Processa tudo que estiver em `entrada_pdfs/` de uma vez, sem precisar abrir o navegador:

```
.venv\Scripts\python -m app.main
```

## Rodar como serviço (pra ficar ligado sozinho, sem terminal aberto)

Isso ainda **não foi instalado** — é só o guia de quando for a hora de colocar isso rodando de verdade num computador do escritório, sem depender de alguém deixar um terminal aberto.

**Opção 1 — NSSM (recomendado, mais robusto)**

1. Baixe o [NSSM](https://nssm.cc/download) e extraia num lugar fixo (ex: `C:\nssm`).
2. Abra o `cmd` como administrador e rode:
   ```
   C:\nssm\nssm.exe install Extratus
   ```
3. Na janela que abre:
   - **Path**: caminho do `python.exe` dentro de `.venv\Scripts\`
   - **Startup directory**: a pasta do projeto
   - **Arguments**: `-m uvicorn app.web.main:app --host 0.0.0.0 --port 8000`
4. Confirme. O serviço aparece no `services.msc` do Windows, liga sozinho com o computador, e reinicia sozinho se cair.

**Opção 2 — Agendador de Tarefas do Windows (mais simples, menos robusto)**

1. Abra o **Agendador de Tarefas** → Criar Tarefa.
2. Gatilho: "Ao iniciar o computador".
3. Ação: executar `scripts\iniciar_servidor.bat`.
4. Marque "Executar mesmo se o usuário não estiver conectado".

Diferença prática: o Agendador não reinicia sozinho se o programa travar no meio; o NSSM sim.

## Testes automatizados

```
.venv\Scripts\python -m pytest tests\ -v
```

## Segurança — o que já existe e o que ainda falta

Já existe: login por usuário/senha (com senha em hash, nunca em texto puro), controle de quais ferramentas cada pessoa pode usar, área de administração restrita a admins, chaves sensíveis fora do controle de versão.

Ainda falta antes de considerar isso "pronto pra produção pesada": HTTPS (hoje o tráfego não é criptografado, ok numa rede interna confiável, mas vale revisar), e a integração real de IA (com as decisões de custo/fornecedor e conformidade de dados ainda pendentes de aprovação da diretoria).
