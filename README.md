# Baptism of Blood: Bot de Dados

Bot de Discord que rola dados, guarda o histórico de cada rolagem (jogador, personagem, dado, resultado, data e hora), sorteia as definições do personagem (Rank de magia, Raça e Classe social), controla XP, nível e ranks, limita as vagas de personagem por jogador, mantém um rank público de XP e calcula os recursos (Vida, Sanidade, Mana e Estamina).

## Comandos dos jogadores

**Rolagens**

- `/rolar dado:1d20+3 motivo:teste de acerto personagem:Kairon Flagon` rola e salva no histórico. `motivo` e `personagem` são opcionais; sem `personagem`, vale o que você está usando no momento.
- `/historico usuario:@alguém limite:10 personagem:Akari Amaya` mostra as últimas rolagens de alguém (padrão: você mesmo). Com `personagem`, mostra só as daquele personagem. A data e a hora aparecem no fuso de quem está lendo.

**Personagens**

- `/personagem criar nome:...` cria um personagem e já passa a usar ele.
- `/personagem usar nome:...` troca o personagem que você está usando (as rolagens novas vão pro histórico dele).
- `/personagem listar` mostra os seus personagens, com nível, XP, Rank, Raça e Estado de cada um, e quantas vagas você usa.
- `/personagem excluir nome:...` exclui um personagem seu **pra sempre**, depois de pedir confirmação com botões. A ficha, o XP, o extrato e os ranks somem sem volta e a vaga é liberada. As rolagens antigas continuam no histórico.

**Vagas de personagem:** cada jogador pode ter até 3 personagens. Os mestres podem liberar vagas extras, na mão (`/mestre vagas`), até 10 no total. Nomes iguais só não podem se repetir dentro dos personagens da mesma pessoa.

**Sorteios de criação** (uma rolagem só por personagem)

- `/magia_inicial` rola 1d100 e define o Rank de magia.
- `/raca_inicial` rola 1d100 e sorteia a Raça.
- `/classe_social` rola 1d100 e sorteia o Estado. Quem cai no 1º Estado rola outro 1d100 na hora, pra saber se é Alto ou Baixo Clero.

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
| 96 a 100 | Dhampir (meio humano, meio vampiro) |

| 1d100 | Classe social |
|---|---|
| 1 a 80 | 3º Estado (Povo) |
| 81 a 91 | 2º Estado (Nobreza) |
| 92 a 99 | 1º Estado (Clero), com segundo sorteio |
| 100 | O mestre decide (o bot avisa o cargo Mestre) |

| Segundo 1d100 (só do 1º Estado) | Clero |
|---|---|
| 1 a 49 | Baixo Clero |
| 50 a 100 | Alto Clero |

**Ficha, níveis e recursos**

- `/minha_ficha personagem:...` mostra nível, XP (e quanto falta pro próximo nível), Raça, Classe social, Rank de magia e os Ranks das perícias especiais. Só você vê a resposta.
- `/niveis personagem:...` mostra o XP e as vantagens de cada nível, de 1 a 10, marcando o nível do seu personagem e o que vem no próximo.
- `/extrato_xp personagem:...` mostra de onde veio o XP do personagem: as últimas 10 entradas, com motivo, mestre e horário.
- `/rank tipo:personagens|jogadores limite:10` mostra o rank de XP total, **público** pra todo mundo. Em `jogadores`, cada um vale a soma do XP de todos os seus personagens. Quem tem 0 XP não aparece.
- `/calcular_recursos classe:... vitalidade:... forca:... vontade:... alma:...` calcula Vida, Sanidade, Mana e Estamina, mostrando a conta. Serve pra ajustar a Vida depois de distribuir pontos de atributo.

## Regras que o bot segue

**XP e nível:** nível máximo 10. Todo personagem começa no nível 1, com 0 XP. Pra sair do nível N são necessários N × 1.000 XP, e o XP é somado (não zera a cada nível). O nível sobe sozinho quando o XP chega no número da tabela; o XP que passa do necessário vale pro nível seguinte, e dá pra subir mais de um nível de uma vez. No nível 10 o XP continua contando, mas não sobe mais. Só os mestres dão XP, em roleplay importante, missão ou evento.

| Nível | XP total pra chegar | Vantagens |
|---|---|---|
| 1 | 0 | Ficha inicial |
| 2 | 1.000 | +2 Perícia, +1 Atributo, habilidade |
| 3 | 3.000 | +2 Perícia |
| 4 | 6.000 | +2 Perícia, +1 Atributo, habilidade |
| 5 | 10.000 | +2 Perícia |
| 6 | 15.000 | +2 Perícia, +1 Atributo, habilidade |
| 7 | 21.000 | +2 Perícia |
| 8 | 28.000 | +2 Perícia, +1 Atributo, habilidade |
| 9 | 36.000 | +2 Perícia |
| 10 | 45.000 | +2 Perícia, +1 Atributo, habilidade |

**Ganhos por nível** (igual ao site): a cada nível ganho, +2 pontos de Perícia. A cada 2 níveis (2, 4, 6, 8 e 10), +1 ponto de Atributo e uma habilidade nova ou melhorada. Até o nível 10 são 18 pontos de Perícia, 5 de Atributo e 5 habilidades. **Vampiros e Dhampirs** ganham ainda +1 ponto de Disciplina nesses níveis pares (5 no total). Na criação, o Vampiro começa com 4 pontos de Disciplina e o Dhampir com 3.

**Recursos** (igual ao site): Vida = Vitalidade × 5, Sanidade = Vontade × 5, Mana = (Alma + Vontade) × 3, Estamina = (Força + Vitalidade) × 3, sempre mais o bônus da classe. O nível não dá Vida direto; o que aumenta a Vida são os pontos de atributo colocados em Vitalidade. Destreza e Razão não entram nessas contas.

| Classe | Vida | Sanidade | Mana | Estamina |
|---|---|---|---|---|
| Caçador | 35 | 15 | 5 | 20 |
| Feiticeiros | 20 | 20 | 25 | 5 |
| Ladrão | 25 | 20 | 10 | 15 |
| Mestre de Forja | 15 | 35 | 15 | 20 |
| Mundano | 10 | 15 | 10 | 10 |
| Sábio | 15 | 35 | 20 | 5 |

**Ranks das perícias especiais**: Ritualismo, Alquimia, Forja, Culinária e Fé têm Rank de 0 a 10. Quem dá um grau novo são os mestres.

## Comandos de mestre

Só quem tem o cargo `Mestre` ou a permissão de Gerenciar Servidor. Sem `personagem`, vale o que o jogador está usando.

- `/mestre dar_xp usuario:@alguém quantidade:500 motivo:... personagem:...` soma XP no personagem, mostra a barra e marca o jogador. Se o XP passar do que o nível pede, o nível sobe sozinho e o bot diz o que o personagem ganhou. Número negativo tira XP (o XP nunca fica abaixo de zero); se isso derrubar o nível, o bot avisa que os pontos daquele nível precisam ser ajustados na ficha. Tudo entra no extrato do jogador.
- `/mestre upar usuario:@alguém niveis:1 motivo:...` é um atalho: dá exatamente o XP que falta pro personagem subir (máximo 10).
- `/mestre corrigir_nivel usuario:@alguém nivel:...` põe o personagem no começo de um nível, com o XP mínimo dele, pra consertar um erro.
- `/mestre rank_pericia usuario:@alguém pericia:... rank:...` define o Rank (0 a 10) de uma perícia especial.
- `/mestre apagar usuario:@alguém definicao:...` apaga Rank de magia, Raça, Classe social ou tudo isso, pro jogador poder rolar de novo. A rolagem antiga continua no histórico.
- `/mestre corrigir_magia`, `/mestre corrigir_raca` e `/mestre corrigir_estado` definem o valor na mão, sem rolar. O `corrigir_estado` é o jeito de resolver o 100 do sorteio de Classe social.
- `/mestre ficha usuario:@alguém personagem:...` mostra a ficha completa de um personagem de outro jogador (só o mestre vê).
- `/mestre jogador usuario:@alguém` mostra quantos personagens a pessoa tem, quantas vagas usa, o XP de cada um e quantos personagens ela já excluiu.
- `/mestre vagas usuario:@alguém extras:2` define quantas vagas **extras** o jogador tem, além das 3 normais (o número é o total de extras, não soma com o que já tinha). O teto é 10 personagens no total.
- `/mestre excluir_personagem usuario:@alguém personagem:...` exclui pra sempre o personagem de outro jogador, depois de pedir confirmação, e avisa o jogador no canal.

Toda ação de mestre fica registrada no banco (quem fez, em quem, o que mudou). Um valor definido por mestre aparece na ficha como "definido por um mestre".

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

Os comandos podem demorar um pouco pra aparecer no Discord na primeira vez, e de novo quando entram comandos novos. É o próprio Discord sincronizando.

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
| `LIMITE_PERSONAGENS` | Vagas de personagem que todo jogador tem (padrão: `3`) |
| `LIMITE_MAXIMO_PERSONAGENS` | Teto de personagens por jogador, contando as vagas extras (padrão: `10`) |
| `DB_PATH` | Caminho do arquivo do banco (opcional, ganha do Volume) |
| `RAILWAY_VOLUME_MOUNT_PATH` | Criada pelo Railway sozinha quando tem Volume |

## Arquivos

- `bot.py`: os comandos.
- `dice.py`: notação de dados e as tabelas de sorteio (magia, raça, classe social, clero).
- `rules.py`: regras do sistema (XP e níveis, ganhos por nível, classes, perícias especiais, cálculo de recursos). Se uma regra mudar no site, muda aqui.
- `db.py`: banco SQLite (histórico, personagens, XP e extrato, vagas, ranks, personagens excluídos, registro das ações de mestre).
- `tests/`: testes automáticos (não conectam no Discord). Pra rodar, da pasta do bot: `python tests/test_db.py` e `python tests/test_bot.py`. O `tests/legacy_schemas.py` guarda o formato exato dos bancos antigos, pra testar a migração.

## Bancos antigos

Ao iniciar, o bot atualiza sozinho um banco criado em versões anteriores: as colunas e tabelas novas são criadas, o XP de cada personagem passa a ser o do começo do nível em que ele já estava, a raça que se chamava "Meio humano, meio vampiro" vira "Dhampir" e, no formato mais antigo de todos, cada definição por jogador vira um personagem com o nome do jogador.

## O que ainda falta

- Integrar esse histórico com o site (hoje são dois sistemas separados, sem comunicação entre eles).
- Disciplinas vampíricas (grau 0 a 5) ainda não aparecem na ficha do bot.
- A ficha ainda não guarda atributos nem classe; por isso o `/calcular_recursos` pede os números na hora.
