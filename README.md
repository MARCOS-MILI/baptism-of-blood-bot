# Baptism of Blood — Bot de Dados

Bot de Discord que rola dados, guarda o histórico de cada rolagem (usuário, dado, resultado, data e hora) e usa rolagens específicas pra definir coisas do personagem, como o Rank de magia inicial (1d100, seguindo a tabela do sistema).

## Comandos

- `/rolar dado:1d20+3 motivo:teste de acerto` — rola e salva no histórico.
- `/historico usuario:@alguém limite:10` — mostra as últimas rolagens de alguém (padrão: você mesmo).
- `/magia_inicial` — rola 1d100 uma vez e define o Rank de magia do seu personagem (Comum, Raro, Super Raro, Lendário ou Mítico).
- `/minha_ficha` — mostra os resultados de definição já salvos (Rank de magia, e Raça quando essa regra existir).

Tudo fica salvo num arquivo `baptism_of_blood.db` (SQLite), que sobrevive a reinícios do bot.

## Como configurar

1. Cria uma aplicação em https://discord.com/developers/applications, adiciona um Bot nela e copia o Token.
2. Na aba OAuth2 > URL Generator, marca `bot` e `applications.commands`, com permissão de enviar mensagens, e usa o link gerado pra convidar o bot pro seu servidor.
3. Instala as dependências:
   ```
   pip install -r requirements.txt
   ```
4. Cria um arquivo `.env` na mesma pasta com:
   ```
   DISCORD_TOKEN=seu_token_aqui
   ```
5. Roda o bot:
   ```
   python bot.py
   ```

Os comandos (`/rolar`, `/historico`, etc.) podem demorar até uma hora pra aparecer no Discord na primeira vez; isso é normal, é o próprio Discord sincronizando.

## Onde hospedar (pra ficar online 24/7)

Rodar `python bot.py` no seu computador funciona, mas o bot só fica online enquanto o computador estiver ligado e o programa rodando. Pra ele ficar sempre ativo, precisa hospedar em algum lugar que rode continuamente. Duas opções confiáveis:

- **Railway** (railway.app) — o mais simples: conecta no GitHub, ele detecta o Python sozinho e roda o bot continuamente. Tem um saldo gratuito mensal, suficiente pra um bot pequeno como esse.
- **Oracle Cloud Free Tier** — uma VM realmente gratuita pra sempre, mas exige mais configuração manual (é um servidor Linux de verdade).

Evite sites de "hospedagem gratuita de bot" pouco conhecidos que aparecem em buscas; muitos não são confiáveis a longo prazo.

## O que ainda falta (pendente de decisão)

- Regra de sorteio de Raça (hoje é escolha na criação, não existe rolagem pra isso ainda).
- Guardar o histórico por personagem, não só por usuário, pra quem jogar mais de um personagem.
- Comando pra um mestre corrigir ou apagar uma rolagem de definição (tipo se `/magia_inicial` for usado errado).
- Integrar esse histórico com o site (hoje são dois sistemas separados, sem comunicação entre eles).
