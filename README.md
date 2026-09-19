# Baptism of Blood: Bot de Dados

Bot de Discord que rola dados, guarda o histórico de cada rolagem (jogador, personagem, dado, resultado, data e hora), sorteia as definições do personagem (Rank de magia, Raça e Classe social), controla XP, nível e ranks, guarda classe e atributos de cada personagem e calcula sozinho os recursos (Vida, Sanidade, Mana e Estamina), limita as vagas de personagem por jogador e mantém um rank público de XP.

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

**Classe e atributos** (a ficha automática)

- `/classe classe:Caçador` escolhe a classe do personagem. Vale **uma vez só**; depois, só um mestre muda. Mostra a vantagem de perícias e o bônus de Vida, Sanidade, Mana e Estamina da classe.
- `/atributos forca:2 vitalidade:3 vontade:1` distribui os pontos de atributo. Só preenche o que quer mudar; sem nenhum número, só mostra como está. **Só dá pra aumentar** (pra diminuir, fala com um mestre), e o bot confere os pontos e os limites de criação da raça. Precisa ter sorteado a raça antes.

**Ficha, níveis e recursos**

- `/minha_ficha personagem:...` mostra nível, XP (e quanto falta pro próximo nível), Raça, Classe social, Rank de magia, Classe, Atributos, os pontos de atributo usados e **Vida, Sanidade, Mana e Estamina já calculados, somando nível a nível**, mais os Ranks das perícias especiais. Só você vê a resposta.
- `/niveis personagem:...` mostra o XP e as vantagens de cada nível, de 1 a 10, marcando o nível do seu personagem e o que vem no próximo.
- `/extrato_xp personagem:...` mostra de onde veio o XP do personagem: as últimas 10 entradas, com motivo, mestre e horário.
- `/rank tipo:personagens|jogadores limite:10` mostra o rank de XP total, **público** pra todo mundo. Em `jogadores`, cada um vale a soma do XP de todos os seus personagens. Quem tem 0 XP não aparece.
- `/calcular_recursos classe:... vitalidade:... forca:... vontade:... alma:... nivel:5` simula Vida, Sanidade, Mana e Estamina com os números que você digitar, mostrando a conta (por exemplo `Vitalidade 3 × 5 × 5 níveis = 75, mais 35 da classe`). O `nivel` vai de 1 a 10 e, sem ele, vale 1. A conta usa **o mesmo atributo em todos os níveis**, então é uma simulação; a conta exata, com o atributo que o personagem tinha em cada nível, é a da `/minha_ficha`.

## Regras que o bot segue

**XP e nível:** nível máximo 10. Todo personagem começa no nível 1, com 0 XP. Pra sair do nível N são necessários N × 1.000 XP, e o XP é somado (não zera a cada nível). O nível sobe sozinho quando o XP chega no número da tabela; o XP que passa do necessário vale pro nível seguinte, e dá pra subir mais de um nível de uma vez. No nível 10 o XP continua contando, mas não sobe mais. Só os mestres dão XP: em roleplay importante, missão de mestre e desenvolvimento do personagem, sempre por roleplay e não por ação avulsa.

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

**Atributos** (igual ao site): são 6 (Força, Destreza, Vitalidade, Razão, Vontade e Alma). Na criação são 6 pontos pra distribuir, e cada 2 níveis (2, 4, 6, 8 e 10) dá +1 ponto, então o total é 6 + nível ÷ 2 (11 no nível 10). Limites de criação: Humano tem 3 em Força, Destreza e Vitalidade e 6 em Razão; Vampiro tem 5 em Força, Destreza e Vitalidade; Vontade e Alma não têm limite. O Dhampir ainda não tem limite definido, então pra ele o bot só confere o total. Os pontos que vêm de nível podem passar do limite de criação, e é assim que o bot confere: o que passar do limite tem que caber nos pontos de nível.

**Recursos** (igual ao site): **a cada nível** o personagem soma de novo o valor de cada recurso, calculado com os atributos que ele tinha naquele nível. Por nível: Vida = Vitalidade × 5, Sanidade = Vontade × 5, Mana = (Alma + Vontade) × 3, Estamina = (Força + Vitalidade) × 3. O bônus da classe entra **uma vez só**, no fim. No nível 1 a conta vale uma vez, e cada nível novo soma outra. Destreza e Razão não entram nessas contas.

**Atributo da época:** o nível em que o personagem está sempre usa os atributos atuais. Quando ele sobe, o nível que ficou pra trás congela com os atributos daquele momento, e um aumento de atributo depois disso só vale daí pra frente. O ponto de atributo que vem ao subir de nível, se for distribuído logo com `/atributos`, já entra na conta do nível novo. Se o personagem ainda não distribuiu nada (Força, Vitalidade, Vontade e Alma zerados) na hora de subir, o bot não congela nada, e aquele nível continua usando os atributos atuais até congelar de verdade. Quando um mestre sobe vários níveis de uma vez, os níveis do meio congelam com os atributos do momento da subida. Se o nível baixa (XP negativo ou `/mestre corrigir_nivel`), os níveis do novo nível em diante deixam de estar congelados. O `/mestre atributos` só mexe no nível atual.

Exemplo, Caçador (bônus Vida 35, Sanidade 15, Mana 5, Estamina 20) com Força 1, Vitalidade 3, Vontade 2 e Alma 1 em todos os níveis:

| Nível | Vida | Sanidade | Mana | Estamina |
|---|---|---|---|---|
| 1 | 50 | 25 | 14 | 32 |
| 5 | 110 | 65 | 50 | 80 |
| 10 | 185 | 115 | 95 | 140 |

Com a Vitalidade em 3 nos níveis 1 a 3 e em 4 a partir do nível 4, a Vida do Caçador fica 80 no nível 3, 100 no nível 4 e 120 no nível 5.

| Classe | Vida | Sanidade | Mana | Estamina |
|---|---|---|---|---|
| Caçador | 35 | 15 | 5 | 20 |
| Feiticeiros | 20 | 20 | 25 | 5 |
| Ladrão | 25 | 20 | 10 | 15 |
| Mestre de Forja | 15 | 35 | 15 | 20 |
| Mundano | 10 | 15 | 10 | 10 |
| Sábio | 15 | 35 | 20 | 5 |

**Ranks das perícias especiais**: Ritualismo, Alquimia, Forja, Culinária e Fé têm Rank de 0 a 10. Quem dá um Rank novo são os mestres.

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
- `/mestre atributos usuario:@alguém forca:9 ...` define atributos na mão, **sem conferir pontos nem limites** (e pode diminuir). Preenche só os que quer mudar. Serve pra corrigir erro ou dar pontos extras por história.
- `/mestre corrigir_classe usuario:@alguém classe:...` define a classe na mão, mesmo depois de o jogador já ter escolhido.
- `/mestre exportar` manda pra você, só você vendo, uma cópia de segurança do banco de dados (um arquivo `.db` consistente, mesmo com o bot rodando). Tem os dados de todos os jogadores, então guarda em lugar seguro. Fica registrado. Se o banco passar do limite de upload do servidor, o bot avisa e manda baixar pelo Railway.

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
- `tests/`: testes automáticos (não conectam no Discord). Pra rodar, da pasta do bot: `python tests/test_rules.py`, `python tests/test_db.py` e `python tests/test_bot.py`. O `tests/legacy_schemas.py` guarda o formato exato dos bancos antigos, pra testar a migração.

## Bancos antigos

Ao iniciar, o bot atualiza sozinho um banco criado em versões anteriores (o esquema atual é a versão 6, e a atualização é só aditiva, nunca apaga nem reescreve coluna existente): as colunas e tabelas novas são criadas, quem já passou do nível 1 ganha os níveis de trás congelados com os atributos de hoje (a tabela `level_attributes`, que também guarda o atributo da época dali pra frente), o XP de cada personagem passa a ser o do começo do nível em que ele já estava, a raça que se chamava "Meio humano, meio vampiro" vira "Dhampir" e, no formato mais antigo de todos, cada definição por jogador vira um personagem com o nome do jogador.

## O que ainda falta

- Integrar esse histórico com o site (hoje são dois sistemas separados, sem comunicação entre eles).
- Disciplinas vampíricas (grau 0 a 5) ainda não aparecem na ficha do bot.
- Pontos de perícia (25 na criação, +2 por nível) ainda não são controlados pelo bot.
