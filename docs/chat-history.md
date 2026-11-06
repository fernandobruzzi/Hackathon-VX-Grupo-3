# Retomar conversas

A tela lista as conversas do usuário autenticado em `GET /api/v1/chat/sessions`, com título pela primeira mensagem e data de atualização. A lista tem paginação por `limit` (1 a 100, padrão 20) e `cursor` retornado pelo servidor.

Selecionar uma conversa consulta `GET /api/v1/chat/sessions/{session_id}`. A resposta contém todo o histórico em ordem, chamadas MCP com o número do turno, ficha persistida, centro e versão atual. O histórico não tem truncamento nem limite de mensagens; a paginação aplica-se apenas à lista de conversas. A leitura não chama o Agent nem refaz busca de similares. Escolhas e descartes permanecem no contexto já validado pelo servidor.

Ambas as leituras exigem `chat:use`. Somente o dono no mesmo tenant pode ler a sessão; outro dono ou tenant recebe 404, mesmo conhecendo o UUID. O identificador no navegador não concede acesso. A leitura informa `processing` enquanto há uma reserva recente; após 60 segundos uma reserva abandonada pode ser retomada pelo fluxo existente. Atualizar a conversa recarrega a versão do servidor antes de um novo envio.

Nova conversa limpa a seleção e começa outro UUID no próximo envio, preservando as anteriores no servidor. Falhas e conflitos podem ser recuperados atualizando a conversa selecionada.

Na interface, use “Retomar conversa” para escolher pelo título e data. “Mais conversas” carrega a próxima página; “Atualizar histórico” repete uma leitura que falhou. A seleção é explícita a cada visita, sem guardar UUID no navegador. Trocar de persona desmonta a conversa anterior e invalida requisições pendentes.

“Atualizar conversa” recarrega mensagens, ficha e versão após conflito ou turno em processamento. Enquanto a leitura ou um turno remoto está pendente, o envio fica bloqueado. Uma resposta de leitura descartada por Nova conversa não altera a nova sessão. Conversas enviadas para revisão recuperam também o resultado de submissão persistido, sem liberar outro envio.
