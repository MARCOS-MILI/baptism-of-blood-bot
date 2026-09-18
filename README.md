# Baptism of Blood: Bot de Dados

Bot de Discord que rola dados, guarda o histórico de cada rolagem (jogador, personagem, dado, resultado, data e hora) e usa rolagens específicas pra definir coisas do personagem: o Rank de magia e a Raça.

## Comandos

**Rolagens**

- `/rolar dado:1d20+3 motivo:teste de acerto personagem:Kairon Flagon` rola e salva no histórico. `motivo` e `personagem` são opcionais; sem `personagem`, vale o que você está usando no momento.
- `/historico usuario:@alguém limite:10 personagem:Akari Amaya` mostra as últimas rolagens de alguém (padrão: você mesmo). Com `personagem`, mostra só as daquele personagem.

**Personagens**

- `/personagem criar nome:...` cria um personagem e já passa a usar ele.
- `/personagem usar nome:...` troca o personagem que você está usando (as rolagens novas vão pro histórico dele).
- `/personagem listar` mostra os seus personagens, com Rank e Raça de cada um.

Cada jogador pode ter quantos personagens quiser. Nomes iguais só não podem se repetir dentro dos personagens da mesma pessoa.

**Definição do personagem** (uma rolagem só por personagem)

- `/magia_inicial` rola 1d100 e define o Rank de magia.
- `/raca_inicial` rola 1d100 e sorteia a Raça.
- `/minha_ficha` mostra o que já foi definido. Nos três, dá pra passar `personagem:` pra escolher qual (padrão: o que você está usando).

| 1d100 | Rank de magia |
|---|---|
| 1 a 45 | Comum |
| 46 a 75 | Raro |
| 76 a 95 | Super Raro |
| 96 a 99 | Lendário |
| 100 | Mítico |

| 1d100 | Raça |
|---|---|
| 1 a 85 | Humano |
| 86 a 95 | Vampiro |
| 96 a 100 | Meio humano, meio vampiro |

**Mestre** (só quem tem o cargo `Mestre` ou a permissão de Gerenciar Servidor)

- `/mestre apagar usuario:@alguém definicao:... personagem:...` apaga o Rank de magia, a Raça ou os dois, pro jogador poder rolar de novo. A rolagem antiga continua no histórico.
- `/mestre corrigir_magia usuario:@alguém rank:...` define o Rank na mão, sem rolar.
- `/mestre corrigir_raca usuario:@alguém raca:...` define a Raça na mão, sem rolar.

Sem `personagem`, vale o que o jogador está usando. Toda ação de mestre fica registrada no banco (quem fez, em quem, o que mudou). Um valor definido por mestre aparece na ficha como "definido por um mestre".

O nome do cargo pode ser trocado com a variável `MESTRE_ROLE` (padrão: `Mestre`).

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

Os comandos podem demorar até uma hora pra aparecer no Discord na primeira vez, e de novo quando entram comandos novos. É o próprio Discord sincronizando.

## Onde hospedar (pra ficar online 24/7)

Rodar `python bot.py` no seu computador funciona, mas o bot só fica online enquanto o computador estiver ligado. Pra ficar sempre ativo, precisa hospedar em algum lugar que rode continuamente:

- **Railway** (railway.app): o mais simples. Conecta no GitHub, ele detecta o Python sozinho e roda o bot continuamente. A cada push na branch `main` ele publica a versão nova.
- **Oracle Cloud Free Tier**: uma VM gratuita, mas com mais configuração manual.

## Guardar o histórico de verdade (Volume no Railway)

O Railway apaga o sistema de arquivos a cada deploy. Sem Volume, todo push no GitHub zera o histórico, os personagens e as fichas. Pra resolver, uma vez só:

1. No projeto do Railway, clica com o botão direito no canvas (ou usa o `Ctrl/Cmd + K`) e escolhe **Volume**.
2. Escolhe o serviço do bot.
3. Em **Mount path**, coloca `/data`.
4. Espera o redeploy terminar.

O bot detecta o Volume sozinho (o Railway cria a variável `RAILWAY_VOLUME_MOUNT_PATH`) e passa a guardar o banco em `/data/baptism_of_blood.db`. Pra conferir, abre os logs do deploy: tem que aparecer `origem: volume`. Se aparecer `origem: local`, o Volume não foi anexado ao serviço certo.

Plano B, se a detecção automática falhar: cria a variável `DB_PATH=/data/baptism_of_blood.db` no serviço. Ela tem prioridade sobre o Volume.

Depois disso, novos deploys não apagam mais nada. Vale lembrar que o Volume é o único lugar com os dados: se apagar o Volume, os dados vão junto.

## Variáveis de ambiente

| Variável | Pra que serve |
|---|---|
| `DISCORD_TOKEN` | Token do bot (obrigatória) |
| `MESTRE_ROLE` | Nome do cargo que usa `/mestre` (padrão: `Mestre`) |
| `DB_PATH` | Caminho do arquivo do banco (opcional, ganha do Volume) |
| `RAILWAY_VOLUME_MOUNT_PATH` | Criada pelo Railway sozinha quando tem Volume |

## Bancos antigos

Ao iniciar, o bot atualiza sozinho um banco criado antes dos personagens: as colunas novas são adicionadas e cada definição antiga (que era por jogador) vira um personagem com o nome do jogador.

## O que ainda falta

- Integrar esse histórico com o site (hoje são dois sistemas separados, sem comunicação entre eles).
