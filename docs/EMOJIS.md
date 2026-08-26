# 😀 Emojis do aplicativo

Esta versão usa emojis pertencentes à **própria aplicação Discord** do bot.

## Como funciona

O arquivo [`utils/emojis.py`](../utils/emojis.py) mantém os IDs de origem informados pelo Knox Dev. Ao iniciar, o bot lista os Application Emojis existentes e cria automaticamente os que estiverem faltando.

Depois da primeira tentativa, uma tarefa em segundo plano repete a verificação periodicamente. Isso permite que o mapa de IDs seja atualizado sem reiniciar o processo.

## Fallback

Se a API do Discord ou o CDN estiver temporariamente indisponível, o bot continua online e usa os IDs de origem como fallback. A sincronização automática tenta novamente depois.

## Limites

O Discord aplica limites e rate limits próprios às rotas de emojis. O sincronizador respeita respostas HTTP `429` e aguarda o `retry_after` retornado antes de tentar novamente.
