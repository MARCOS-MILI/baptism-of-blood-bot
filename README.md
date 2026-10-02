# Baptism of Blood: Bot de Dados

Bot de Discord que rola dados, guarda o histórico de cada rolagem (jogador, personagem, dado, resultado, data e hora), sorteia as definições do personagem (Rank de magia, Raça e Classe social), controla XP, nível e ranks, guarda classe e atributos de cada personagem e calcula sozinho os recursos (Vida, Sanidade, Mana e Estamina), limita as vagas de personagem por jogador e mantém um rank público de XP.

## Comandos dos jogadores

**Rolagens**

- `/rolar dado:1d20+3 motivo:teste de acerto personagem:Kairon Flagon` rola e salva no histórico. `motivo` e `personagem` são opcionais; sem `personagem`, vale o que você está usando no momento. Com o `#` na frente o dado rola **várias vezes, cada uma separada**: `3#d20+5` rola o d20+5 três vezes (de 1 a 10) e o cartão mostra uma linha por rolagem e o maior e o menor no fim, como uma vantagem que o jogador escolhe. No histórico, cada rolagem vira uma linha.
- `/habilidade` mostra a habilidade inicial da sua classe. O Clérigo (Mãos que Curam ou Bênção) e o Ladrão (Mão Leve ou Língua de Prata) oferecem duas. **Normalmente a pessoa escolhe a habilidade junto com a classe, nos botões do menu de classe** (ver "Botões"). Se faltou, `/habilidade` (ou o `/classe` sem `habilidade`) já mostra dois botões, e o botão **Habilidade** da ficha também; `/habilidade escolha:Bênção` faz o mesmo digitando. Vale uma vez e fica na ficha (o mestre refaz trocando a classe com `/mestre corrigir_classe`). O bot só mostra o texto; quem usa a habilidade e cobra o custo é a mesa.
- **Dados direto no chat, sem barra:** escreve `d20`, `d20+5` ou `2d6-1` numa mensagem e o bot rola, responde na própria mensagem e salva no histórico, como o `/rolar`. Com um `+` na frente, o que vem depois do dado vira o motivo: `+d20+5 ataque com a espada`. Sem o `+`, a mensagem inteira precisa ser só o dado, então conversa normal ("d20 é o melhor dado") nunca rola. Vale a mesma regra da ficha pronta do `/rolar` (os mestres passam direto). No d20, um 20 ou um 1 natural ganha um destaque visual, sem efeito nenhum de regra. Precisa do **Message Content Intent** ligado (ver "Dados por texto" abaixo).
- `/historico usuario:@alguém limite:10 personagem:Akari Amaya` mostra as últimas rolagens de alguém (padrão: você mesmo). Com `personagem`, mostra só as daquele personagem. A data e a hora aparecem no fuso de quem está lendo.

**Personagens**

- `/personagem criar nome:...` cria um personagem e já passa a usar ele.
- `/personagem usar nome:...` troca o personagem que você está usando (as rolagens novas vão pro histórico dele).
- `/personagem listar` mostra os seus personagens, com nível, XP, Rank, Raça e Estado de cada um, e quantas vagas você usa.
- `/personagem excluir nome:...` exclui um personagem seu **pra sempre**, depois de pedir confirmação com botões. A ficha, o XP, o extrato e os ranks somem sem volta e a vaga é liberada. As rolagens antigas continuam no histórico.

**Vagas de personagem:** cada jogador pode ter até 3 personagens. Os mestres podem liberar vagas extras, na mão (`/mestre vagas`), até 10 no total. Nomes iguais só não podem se repetir dentro dos personagens da mesma pessoa.

**Ordem da criação e ficha pronta**

A criação do personagem tem uma ordem, e o bot vai guiando:

1. `/personagem criar`
2. Os sorteios de raça e de classe social, em qualquer ordem: `/raca_inicial` e `/classe_social`
3. `/classe`, que só abre depois desses dois sorteios
4. `/magia_inicial`, **só pra quem tem magia** (ver abaixo), que só abre depois da raça e da classe
5. `/atributos`, que só abre depois de escolher a classe e, se o personagem tem magia, de sortear o Rank de magia

A ficha só fica **pronta** com a raça e a classe social sorteadas (um 100 na classe social conta só depois que um mestre decide o Estado), a classe escolhida, o Rank de magia sorteado (se o personagem tem magia) e os 6 pontos de atributo da criação distribuídos. Enquanto não estiver pronta, o bot **bloqueia** `/rolar` e `/extrato_xp` (que usam o personagem em uso, ou o do campo `personagem:`) e `/historico` e `/rank` (que só abrem quando pelo menos um dos seus personagens estiver pronto). A mensagem de bloqueio mostra o passo a passo com o que já foi feito (✅), o próximo (▶️), o que ainda está fechado (🔒) e o que está com o mestre (⏳). Ficam sempre abertos: `/ajuda`, `/help`, `/personagem`, `/minha_ficha` (que avisa o que falta), `/niveis`, `/calcular_recursos` e os próprios passos da criação, na ordem. Os mestres passam direto por tudo isso. Se um mestre apagar um sorteio (`/mestre apagar`), a ficha do jogador volta a ficar incompleta até ele rolar de novo.

Personagens que já existiam e ainda não têm classe e atributos também precisam completar a ficha pra usar os comandos bloqueados.

**Quem tem magia:** só tem Rank de magia quem é **Vampiro** ou **Dhampir** (de qualquer classe) ou das classes **Feiticeiros** e **Mestre de Forja**, igual ao site. Humano Mundano, por exemplo, não tem. Quem não tem magia não sorteia o Rank: o `/magia_inicial` explica o motivo e o passo simplesmente não vale pra esse personagem, então a ficha fica pronta sem ele. Como o Rank depende da raça e da classe, ele vem **depois** das duas. A ficha mostra "sem magia" pra quem não tem. Se um Rank já estava guardado de antes (por exemplo, de um Humano Mundano), ele continua lá, com um aviso na ficha, e um mestre pode tirar com `/mestre apagar`. Os mestres podem dar o Rank a quem não tem magia com `/mestre corrigir_magia`, e o bot avisa quando corrigir a raça ou a classe muda se o personagem tem magia.

**Ajuda**

- `/ajuda` (ou `/help`) mostra o seu passo a passo e a lista de comandos, com um resumo de cada um. Com `comando:` (por exemplo `/ajuda comando:atributos`), explica um comando com exemplo e diz quando dá pra usar. Os comandos de mestre só aparecem na lista pra quem é mestre.

**Sorteios de criação**

- `/raca_inicial` rola 1d100 e sorteia a Raça.
- `/classe_social` rola 1d100 e sorteia o Estado. Quem cai no 1º Estado rola outro 1d100 na hora, pra saber se é Alto ou Baixo Clero.
- `/magia_inicial` rola 1d100 e define o Rank de magia, **só pra quem tem magia** e só depois da raça e da classe (a tabela do Rank está logo abaixo). É **uma rolagem só** por personagem; quem tem uma habilidade que dá vantagem combina com um mestre, na mão.

**Três chances (raça e classe social).** Cada personagem tem até **3 rolagens** de raça e até **3** de classe social. Rolar de novo **troca** o resultado pelo novo (a última vale), e o bot **sempre pergunta antes** (botões Rolar de novo e Manter), porque não dá pra voltar atrás. Nos botões da ficha, o botão fica como "Raça (2)" 🔄, com o número de chances que sobram. As chances fecham quando: as 3 acabam; o personagem **escolhe a classe** (o resto da ficha depende da raça); a classe social cai no **100** (o mestre decide); ou um mestre define o valor na mão (`/mestre corrigir_raca` e `/mestre corrigir_estado`). `/mestre apagar` devolve as 3 chances. Todas as rolagens ficam no histórico. Quem já tinha raça ou classe social sorteada antes dessa versão conta como 1 chance gasta. O número de chances é a constante `CREATION_ROLL_ATTEMPTS`, em `rules.py`.

**Resultados especiais.** Alguns resultados raríssimos nos sorteios de criação não definem nada: o cartão sai só com interrogações, o bot marca o cargo Mestre e um mestre decide o destino do personagem (`/mestre corrigir_raca`, `corrigir_estado`, `corrigir_magia`, ou `/mestre apagar` pra devolver as chances). Enquanto isso, o jogador não rola de novo e a ficha não fica pronta. Os detalhes ficam só no código, de propósito.

**Os cartões não mostram o dado** da raça nem da classe social (só o resultado, com "tentativa 1 de 3" no rodapé); a rolagem continua valendo e aparece no `/historico`. O Rank de magia continua mostrando o 1d100.

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

- `/classe classe:Caçador` escolhe a classe do personagem. Vale **uma vez só**; depois, só um mestre muda. Mostra a vantagem de perícias, o bônus de Vida, Sanidade, Mana e Estamina, e a habilidade da classe. No Clérigo e no Ladrão dá pra escolher a habilidade junto: `/classe classe:Clérigo habilidade:Bênção` (a classe e a habilidade entram juntas, ou nenhuma). Sem `habilidade`, o cartão já vem com dois botões pra escolher.
- `/atributos forca:2 vitalidade:3 vontade:1` distribui os pontos de atributo. Só preenche o que quer mudar; sem nenhum número, só mostra como está. **Só dá pra aumentar** (pra diminuir, fala com um mestre), e o bot confere os pontos e os limites de criação da raça. Precisa ter sorteado a raça antes.

**Ficha, níveis e recursos**

- `/minha_ficha personagem:...` mostra (com botões, veja "Botões" abaixo) nível, XP (e quanto falta pro próximo nível), Raça, Classe social, Rank de magia, Classe, Atributos, os pontos de atributo usados e **Vida, Sanidade, Mana e Estamina já calculados, somando nível a nível**, mais os Ranks das perícias especiais. Só você vê a resposta.
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

## Disciplinas

Só **Vampiro e Dhampir** têm. São dez: Potência, Celeridade, Ofuscação, Presença, Domínio, Vidência, Proteísmo, Hemomancia, Sanguessugia e Regeneração, com grau de 0 a 5.

- **Pontos:** o Vampiro começa com 4 e o Dhampir com 3, e os dois ganham +1 a cada 2 níveis (2, 4, 6, 8 e 10). 1 ponto = 1 grau.
- **Como o jogador gasta:** botão **Disciplinas** na ficha (só aparece pra Vampiro e Dhampir), ou o comando `/disciplinas`. Abre um menu das dez; escolher uma mostra o texto de cada grau, e o botão **Subir** gasta 1 ponto e sobe 1 grau. O jogador **só aumenta** e só até o **grau 3**; os graus 4 e 5 só o mestre concede (`/mestre disciplina`) e não gastam ponto. Qualquer um pode usar o `/disciplinas` só pra ler os textos.
- **Sanguessugia:** ainda sem texto nos graus 1 a 3, então fica **bloqueada pra todo mundo** (jogador e mestre), marcada "em desenvolvimento". Quando o texto estiver pronto, é só trocar `SANGUESSUGIA_LIBERADA` pra `True` em `rules.py` e preencher os graus dela em `lore.py`. Não precisa mexer no banco.
- **Não trava a ficha pronta:** um Vampiro pode terminar a criação sem gastar nenhum ponto de Disciplina e gastar depois.
- A ficha ganha o campo **Disciplinas** (pontos usados e o grau de cada uma). O texto de cada grau fica em `lore.py` (`DISCIPLINAS`). Os graus 4 e 5 são sempre "em aberto".

## Abas da ficha e barras de Vida, Sanidade, Mana e Estamina

A ficha (`/minha_ficha`) agora tem uma linha de **abas** no topo: **📋 Ficha** (os passos da criação, atributos e atalhos) e **❤️ Vitais**. A aba onde a pessoa está fica azul e parada; é só apertar a outra pra trocar. As próximas telas (perícias, habilidades) entram nessa mesma linha.

Na aba **Vitais** a pessoa vê quatro barras (▰▰▰▱▱) com o atual e o máximo de cada vital. Escolhe a barra no menu e usa os botões **-10 -5 -1 +1 +5 +10** pra descer ou subir; **Valor exato** abre um formulário e **Restaurar tudo** é o descanso. A vida ficando em 0 pinta o cartão de cinza e avisa. O máximo vem do cálculo por nível (precisa ter escolhido a classe). O bot guarda quanto o personagem **perdeu**, não o valor atual (tabela `character_vitals`): assim, se o máximo sobe com o nível, o atual sobe junto, e o atual nunca passa do máximo.

## O visual das telas

**Todas** as telas do bot usam o desenho do servidor, o mesmo das raças e dos Estados: **sem título de embed**. O cabeçalho enfeitado (emoji da cruz, ornamento e a inicial em negrito matemático) abre a descrição, a frase de época vem em citação pequena e em negrito, e o conteúdo da tela vem depois; quando faz sentido, o nome do personagem vai na linha do autor.

Como funciona: `vitrine.tela(title=..., description=..., color=...)` recebe o título como o `discord.Embed` recebia ("🎲 Bandeja de dados"), tira o emoji, enfeita o resto e acrescenta a frase. Todo embed novo com título deve usar `tela` (e não `discord.Embed(title=...)`). Quem monta a tela inteira à mão usa `vitrine.embed_decorado(rotulo, frase, corpo, cor, autor=..., rodape=...)`.

**As frases de época** (a linguagem de 1790, com "vós" e "vosso") ficam num lugar só: `FRASES_DA_EPOCA` e `PREFIXOS_DA_EPOCA` no `vitrine.py`. Dá pra editar à vontade; tela sem frase mostra só o cabeçalho. As instruções de uso e as mensagens de erro continuam em português claro, de propósito.

**Ficam de fora, de propósito:** os cartões de rolagem de dado (saem dezenas de vezes por cena e o cabeçalho empurraria o chat), o resultado especial dos sorteios (66, 77 e o 100, que são cartões cifrados) e os formulários e botões, que o Discord não deixa enfeitar. Os emojis (`cruz2`, `cruz6`...) só aparecem em servidores onde o bot tem acesso a eles; nos outros viram `:cruz2:`.

## Imagens por link (gifs do Tenor)

`IMAGENS_URL` no `lore.py` guarda links diretos de imagem (o que termina em `.gif`; a página `/view/` do Tenor não serve). Quando o bot liga, ele **baixa** cada link em segundo plano, confere nos primeiros bytes que é mesmo uma imagem (até 8 MB) e anexa o arquivo no cartão, porque o Discord às vezes não mostra imagem de link. A ordem no cartão é: o que foi baixado, depois a imagem parada de `assets/`, depois o link. O que aconteceu com cada link vai pro log (`[imagens] raca-humano: ok (...)` ou `falhou: ...`). `BAIXAR_IMAGENS=0` desliga o download.

## Mensagem de boas-vindas

`/mestre comecar_aqui` posta no canal uma mensagem com quatro botões: **🆕 Criar personagem** (abre um formulário só com o nome e já abre a ficha), **📋 Minha ficha**, **🎲 Dados** e **❓ Como funciona**. Os botões têm identificador fixo (`inicio:...`) e são registrados na partida (`_preparar_bot`), então continuam funcionando em mensagens antigas depois que o bot reinicia. O mestre deve fixar a mensagem (o pino).

## Perícias e habilidades criadas

A ficha ganhou mais duas abas, **🎯 Perícias** e **✨ Habilidades** (também abrem com `/pericias` e `/habilidades`).

**Perícias.** As 18 perícias comuns do site, cada uma com um ícone. Na aba **🎲 Perícias** o jogador toca no ícone e o bot rola 1d20 + atributo + perícia sozinho (entra no histórico e respeita a sorte do mestre). O atributo é o padrão de cada perícia (`SKILL_DEFAULT_ATTRIBUTE` em `rules.py`) e o botão **Atributo** força outro; o botão do modo troca entre normal, vantagem e desvantagem. A vantagem que a classe dá entra sozinha (`CLASS_SKILL_ADVANTAGES`): Caçador e Mercenário escolhem Luta ou Pontaria e o Mundano escolhe duas, na tela **Distribuir**, que também tem os pontos (25 na criação, Mundano 30, +2 por nível, Sábio +4, máximo 7 em cada, sempre). O modo escolhido pelo jogador aparece com 🎲, a vantagem da classe com ⭐ e a sorte do mestre com 🍀.

**Habilidades criadas.** O jogador aperta **Criar habilidade** e preenche um formulário (nome, descrição, efeito que quer). Cai na fila do mestre (`/mestre habilidades`), que escolhe pelos menus o dado de dano ou cura, o custo (Mana, Estamina, Sanidade ou Vida) e um atributo pra somar, e aprova, pede ajuste (com nota) ou recusa. **Valores exatos** deixa digitar o que não está nos menus e **Corrigir texto** muda o texto. Aprovada, o jogador usa com **⚡ Usar**: o custo sai da barra, o dado rola e o cartão sai no canal (com o histórico). Sem recurso suficiente nada é gasto. O dano e a cura não são aplicados a ninguém (o bot não guarda monstros), o cartão só mostra o número. A lógica está em `habil.py`; as tabelas são `character_skills` e `custom_abilities`.

`/mestre pericia` define os pontos de uma perícia (conserta uma distribuição, sem conferir o limite).

## Mestres: ajuda separada e comandos escondidos

- `/mestre ajuda` lista só os comandos de mestre, por assunto, e `/mestre ajuda comando:dar_xp` explica um deles. O `/ajuda` dos jogadores **não lista nem explica** comandos de mestre (quem não é mestre que procura um deles recebe o mesmo "não achei" de qualquer comando que não existe), e o autocomplete dele também não mostra.
- O grupo `/mestre` fica **escondido** de quem não tem a permissão Gerenciar servidor (`ESCONDER_COMANDOS_DE_MESTRE`, ligado por padrão; `0` desliga). Quem tem só o cargo Mestre precisa ser liberado no Discord: Configurações do servidor, Integrações, o bot, Comandos, `/mestre`, adicionar o cargo. Mesmo escondido, o bot confere de novo quem é mestre em cada comando.
- O aviso dos resultados especiais marca o cargo Mestre e também os cargos de **administrador** do servidor (até 5, sem os cargos de bot nem o @everyone).

## Classes e habilidades

São **oito classes**, iguais às do site: Caçador, Clérigo, Feiticeiros, Ladrão, Mercenário, Mestre de Forja, Mundano e Sábio. Clérigo e Mercenário são as novas. Cada classe tem bônus de Vida, Sanidade, Mana e Estamina (em `rules.py`), vantagem em duas perícias e uma habilidade inicial. O texto de cada classe, a frase curta, os exemplos de profissão e as habilidades ficam em `lore.py` (`CLASSES`, `CLASSE_FRASE`, `CLASSE_COMBINA` e `HABILIDADES`), **copiados do site**: o capítulo Habilidades de Classe do site ainda é rascunho, então esses textos mudam quando ele mudar. O cartão da classe mostra tudo isso, e a prévia do menu também.

- **Duas opções:** só o Clérigo e o Ladrão. A escolha vai pra coluna `class_ability` da ficha e zera quando a classe muda. Ela **não trava a ficha pronta** (quem já tinha classe antes não fica bloqueado): o botão **Classe** da ficha vira **Habilidade** ✨ até a pessoa escolher.
- **Sábio:** ganha o dobro de pontos de perícia por nível (+4 em vez de +2), e o `/niveis` e os avisos de nível já mostram isso.
- **Mundano:** o +5 de perícias na criação e a aprimoração são só texto por enquanto, porque o bot ainda não controla os pontos de perícia.
- Magia inicial continua só pra Vampiro, Dhampir, Feiticeiros e Mestre de Forja: Clérigo e Mercenário não têm.

## Sorte do mestre

`/mestre sorte` põe um efeito nos próximos d20 de um personagem (não do jogador: cada personagem tem os seus): **vantagem** (fica o maior de 2 d20), **desvantagem**, **bônus** ou **penalidade** no total, **dado mínimo**, **dado máximo** ou **dado fixo**. `usos` (de 1 a 20) diz em quantas rolagens ele vale, `Ver` lista os ativos e `Limpar` tira todos. Vários efeitos podem valer ao mesmo tempo (vantagem e desvantagem se anulam). O cartão da rolagem mostra a marca 🍀 com o que aconteceu, a menos que o mestre ligue `discreto`. Tudo fica no registro das ações de mestre.

Só afeta **um d20 sozinho** (`1d20`, `d20+5`, cada rolagem de um `3#d20`), rolado pelo `/rolar`, pela bandeja ou escrito no chat. **Não** mexe nos sorteios da criação nem na iniciativa, nem em outros dados (d6, d100, 2d20). A regra fica em `dice.py` (`aplicar_sorte`) e os efeitos ficam na tabela `dice_effects`.

## Cenas, intenções e o Escudo do Mestre

Pra cena com muita gente (7, 8 jogadores ou mais), pra ninguém mandar dez mensagens no canal. Uma cena vive num **canal** (uma cena aberta por canal).

**O mestre** usa `/mestre escudo` (tela privada, só ele vê):

- **Iniciar cena** abre a cena com um nome. **Encerrar** fecha (pede confirmação).
- A tela mostra a **ordem da iniciativa** com o **texto** de todas as intenções que os jogadores mandaram. Um menu lista as que estão aguardando: escolhe uma e aperta **Permitir** ou **Negar** (o Negar abre um formulário pro motivo, que é opcional e o jogador vê).
- **Próximo turno** passa a vez e **marca só o jogador da vez** no canal (NPC não marca ninguém). Passando do último, começa a **rodada** seguinte, e cada rodada tem as suas intenções.
- **NPC** (➕) põe um NPC com nome e iniciativa (um número, ou uma rolagem como `1d20+3`). O menu de baixo edita a iniciativa de qualquer um ou o tira da cena.
- **Mostrar iniciativa** posta o **quadro público** no canal (uma mensagem só, que o bot edita a cada mudança). Se apagarem o quadro, o próximo Mostrar posta outro.
- Como a tela é privada, ela só se atualiza quando o mestre aperta algo: o botão 🔄 **Atualizar** mostra o que chegou.

**Os jogadores:**

- `/iniciativa` (ou o botão 🎲 do quadro) entra na ordem: **1d20 + Destreza**, a regra do site. Quem tem **Celeridade** (grau 1 ou mais) rola com **vantagem** (dois d20, fica o maior). É uma vez por cena, só o jogador vê o resultado e vale a mesma regra de ficha pronta do `/rolar`.
- `/intencao texto:...` (ou o botão 📝) manda **numa frase, até 200 letras**, o que o personagem quer fazer. **Só o mestre lê.** É uma por rodada: mandar outra troca a anterior, menos se já foi permitida. Sem texto, o `/intencao` (ou o botão 👁) mostra a intenção atual e o motivo, se foi negada.
- O jogador age **na sua vez**, seguindo a ordem.

**O quadro público** mostra a ordem, quem tem a vez (▶️) e o status de cada jogador: ⏳ sem intenção, 📝 aguardando o mestre, ✅ permitida, ❌ negada. **Nunca mostra o texto das intenções** (pode ter ação em segredo). Os botões do quadro têm identificador fixo, então **continuam funcionando depois que o bot reinicia**. Os NPCs aparecem sem status. O limite é de 25 participantes por cena. O bot precisa poder ver, escrever e editar mensagens no canal.

## Botões (sem digitar comando)

Quase tudo da criação e do jogo dá pra fazer clicando:

- **`/minha_ficha`** (e a mensagem de boas-vindas do `/personagem criar`) vêm com botões embaixo da ficha:
  - **Raça, Classe social, Magia:** sorteiam na hora e o cartão com imagem sai no canal pra todo mundo. O botão de um passo que ainda não abriu fica trancado 🔒, o que já foi feito fica verde ✅, o resultado 100 da classe social fica ⏳ (esperando o mestre) e quem não tem magia vê "Sem magia" ➖.
  - **Classe:** abre um menu com as oito classes. Escolher no menu só mostra uma prévia (texto, vantagem e bônus); a classe só vale depois de apertar **Confirmar classe**, porque não dá pra desfazer. Tem botão **Voltar**. No **Clérigo** e no **Ladrão** aparecem dois botões ✨ com as habilidades: marca uma (fica verde) e o botão vira **Confirmar classe e habilidade**, que só libera depois de marcar. Trocar de classe desmarca a habilidade. A classe e a habilidade entram juntas.
  - **Físicos e Mentais:** abrem um formulário com três atributos cada (o Discord só aceita 5 campos por formulário, e são 6 atributos), já preenchidos com o valor atual. Passa pelas mesmas conferências do `/atributos`: só aumenta, confere o total de pontos e os limites da raça. Os botões desligam quando não sobra ponto.
  - **Dados, Níveis, Ajuda:** atalhos pra bandeja de dados, pra tabela de níveis e pra `/ajuda`.
  - **Trocar de personagem:** um menu aparece quando o jogador tem mais de um personagem.
  - A tela se atualiza sozinha a cada clique, e só o dono do painel consegue usar os botões.
- **`/dados`** abre uma bandeja só sua: botões d4, d6, d8, d10, d12, d20 e d100, ➖ e ➕ pra quantidade (1 a 10), -5, -1, +1, +5 e Zerar pro modificador (até ±30) e 📝 Motivo (abre um formulário). **Rolar** manda o resultado pro canal, no nome do personagem em uso, com o motivo, e guarda no histórico. A bandeja continua aberta pra rolar de novo. Vale a mesma regra de ficha pronta do `/rolar` (os mestres passam direto).

Os painéis valem por 14 minutos (limite do Discord pra editar a resposta), e depois os botões se desligam; é só abrir de novo com `/minha_ficha`. Se o bot reiniciar, os painéis que já estavam abertos param de responder pelo mesmo motivo. Por dentro, cada botão chama o **mesmo código** do comando de barra equivalente (o painel recebe uma "interação de mentira" que guarda a resposta em vez de enviar), então nenhuma regra é repetida: mudou a regra num lugar, vale nos dois.

## Cartões com imagem e texto

Quando alguém sorteia a raça, a classe social, a classe ou o Rank de magia, o bot mostra um cartão: o resultado como título, o texto de lore em citação, a rolagem, os campos que importam (na raça, o que ela muda na ficha; na classe, a vantagem e o bônus) e uma **imagem grande** embaixo. O 1º Estado mostra também o clero (Alto ou Baixo) logo abaixo. Nada disso muda regra: é só a forma de mostrar.

- **Textos e cores:** ficam todos em `lore.py`, num lugar só, pra editar sem mexer em mais nada. Os de raça e de Estado são os do servidor, e os do Dhampir, do clero e das classes são os do site.
- **Imagens e gifs:** o bot procura sozinho um arquivo na pasta `assets/` com o nome `<tipo>-<nome>.<extensão>`, tudo em minúsculas, sem acento e com hífen no lugar de espaço. Aceita `gif`, `png`, `jpg`, `jpeg` e `webp` (o gif se mexe no Discord). Sem arquivo, o cartão sai só sem a imagem. Exemplos: `raca-dhampir.gif`, `raca-humano.png`, `estado-3.png`, `estado-mestre.png` (resultado 100), `clero-alto.png`, `classe-cacador.png`, `classe-mestre-de-forja.png`, `magia-super-raro.png`. Se preferir um link direto de imagem hospedada em outro lugar, é só colocar em `IMAGENS_URL`, no `lore.py`.
- **Já tem imagem:** Humano, Vampiro, 1º (a Notre-Dame), 2º e 3º Estado. **Faltam:** Dhampir, resultado 100, Alto e Baixo Clero, as seis classes e os cinco Ranks de magia. Se existir mais de um arquivo com o mesmo nome e extensões diferentes, vale a ordem gif, png, jpg, jpeg, webp: pra trocar uma imagem, apaga a antiga.
- **Estilo decorado (raça e Estado):** os cartões de raça e de Estado seguem o estilo das mensagens do servidor: um cabeçalho enfeitado com emoji (o nome do resultado abre o texto, sem título do embed), o texto em citação, em letra pequena e em negrito, e a imagem embaixo. Os emojis, o texto pequeno e os enfeites ficam no começo do `lore.py` (`EMOJI_TITULO`, `EMOJI_TEXTO`, `TEXTO_PEQUENO` e os caracteres). Os emojis são do servidor: o bot precisa estar nele (ou ter a permissão Usar emojis externos) pra eles aparecerem. Classes e magia ainda usam o estilo antigo.
- Cada cartão manda a imagem como anexo. O bot precisa da permissão de **Anexar Arquivos** e **Inserir Links** no canal.
- O repositório é público, então as imagens da pasta `assets/` ficam públicas junto. Se elas têm direitos autorais, vale deixar o repositório privado (o Railway continua funcionando com repositório privado).

## Dados por texto (sem barra)

O `3#d20+5` também funciona escrito no chat. Pra o bot ler o que você escreve no chat (o `d20+5`), o Discord exige que o **Message Content Intent** esteja ligado. É uma vez só:

1. Abre discord.com/developers, entra no seu aplicativo e vai em **Bot**.
2. Rola até **Privileged Gateway Intents** e liga **Message Content Intent**. Salva.
3. Reinicia o bot no Railway.

O bot já vem pedindo essa permissão, mas **não cai** se ela ainda não estiver ligada: ele detecta a recusa na partida, avisa no log e sobe sem os dados por texto (os comandos de barra seguem normais). Quando você ligar no portal e reiniciar, passa a funcionar. Pra desligar de propósito, coloca `DADOS_POR_TEXTO=0` no Railway. O `/ajuda` só fala dos dados por texto quando o recurso está ligado. O bot também precisa poder **ver o canal** e **responder** nele.

## Comandos de mestre

Só quem tem o cargo `Mestre` ou a permissão de Gerenciar Servidor. Sem `personagem`, vale o que o jogador está usando.

- `/mestre dar_xp usuario:@alguém quantidade:500 motivo:... personagem:...` soma XP no personagem, mostra a barra e marca o jogador. Se o XP passar do que o nível pede, o nível sobe sozinho e o bot diz o que o personagem ganhou. Número negativo tira XP (o XP nunca fica abaixo de zero); se isso derrubar o nível, o bot avisa que os pontos daquele nível precisam ser ajustados na ficha. Tudo entra no extrato do jogador.
- `/mestre upar usuario:@alguém niveis:1 motivo:...` é um atalho: dá exatamente o XP que falta pro personagem subir (máximo 10).
- `/mestre corrigir_nivel usuario:@alguém nivel:...` põe o personagem no começo de um nível, com o XP mínimo dele, pra consertar um erro.
- `/mestre rank_pericia usuario:@alguém pericia:... rank:...` define o Rank (0 a 10) de uma perícia especial.
- `/mestre disciplina usuario:@alguém disciplina:... grau:...` define o grau (0 a 5) de uma Disciplina, sem conferir pontos, com registro. Os graus 1 a 3 contam como pontos gastos do jogador; os graus 4 e 5 (que só o mestre concede) não gastam ponto. Só pra Vampiro e Dhampir, e a Sanguessugia fica bloqueada (ver "Disciplinas").
- `/mestre sorte usuario:@alguém efeito:Vantagem usos:2` mexe na sorte dos d20 de um personagem (ver "Sorte do mestre" abaixo).
- `/mestre escudo` abre o Escudo do Mestre (ver "Cenas, intenções e o Escudo do Mestre").
- `/mestre apagar usuario:@alguém definicao:...` apaga Rank de magia, Raça, Classe social ou tudo isso, pro jogador poder rolar de novo. A rolagem antiga continua no histórico. Enquanto ele não rolar de novo, a ficha dele fica incompleta e os comandos de jogo dele fecham.
- `/mestre corrigir_magia`, `/mestre corrigir_raca` e `/mestre corrigir_estado` definem o valor na mão, sem rolar. O `corrigir_estado` é o jeito de resolver o 100 do sorteio de Classe social.
- `/mestre ficha usuario:@alguém personagem:...` mostra a ficha completa de um personagem de outro jogador (só o mestre vê).
- `/mestre jogador usuario:@alguém` mostra quantos personagens a pessoa tem, quantas vagas usa, o XP de cada um e quantos personagens ela já excluiu.
- `/mestre vagas usuario:@alguém extras:2` define quantas vagas **extras** o jogador tem, além das 3 normais (o número é o total de extras, não soma com o que já tinha). O teto é 10 personagens no total.
- `/mestre excluir_personagem usuario:@alguém personagem:...` exclui pra sempre o personagem de outro jogador, depois de pedir confirmação, e avisa o jogador no canal.
- `/mestre apagar_historico usuario:@alguém` apaga o histórico de rolagens (o que o `/historico` mostra) de um jogador, de todos os personagens dele. Pede confirmação com botões, avisa no canal e fica registrado, com a quantidade apagada. Não mexe na ficha, no XP nem nos personagens, e não tem como desfazer. Atenção: as rolagens dos sorteios de criação (raça, magia e classe social) também somem, e é por elas que dá pra ver se alguém rolou de novo.
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
| `DADOS_POR_TEXTO` | Dados escritos direto no chat (`d20+5`). Ligado por padrão; com `0` desliga. Precisa do Message Content Intent ligado no Portal do Desenvolvedor, senão o bot avisa no log e sobe sem esse recurso |
| `ORDEM_DA_CRIACAO` | Chavinha de segurança. Com `0`, o bot deixa de bloquear comandos por causa da ficha e tudo abre como era antes da ordem. Sem a variável, fica ligada. Dá pra mudar direto no Railway, sem deploy (só reinicia o bot) |
| `LIMITE_PERSONAGENS` | Vagas de personagem que todo jogador tem (padrão: `3`) |
| `LIMITE_MAXIMO_PERSONAGENS` | Teto de personagens por jogador, contando as vagas extras (padrão: `10`) |
| `DB_PATH` | Caminho do arquivo do banco (opcional, ganha do Volume) |
| `RAILWAY_VOLUME_MOUNT_PATH` | Criada pelo Railway sozinha quando tem Volume |

## Arquivos

- `bot.py`: os comandos, a leitura dos dados escritos no chat e a partida.
- `lore.py`: os textos e as cores de cada cartão (raças, Estados, clero, classes, Rank de magia). É o arquivo pra editar texto.
- `vitrine.py`: monta os cartões (título, texto em citação, campos e imagem), o cartão de rolagem e os cartões das Disciplinas.
- `cena.py`: a lógica das cenas (iniciativa, a vez de cada um, intenções) e os quadros público e do mestre.
- `escudo.py`: as telas com botões do Escudo do Mestre e o quadro público da cena (persistente).
- `paineis.py`: os painéis com botões (ficha interativa, escolha de classe, formulários de atributos e bandeja de dados). Não importa o `bot.py`: ele recebe do `bot.py` as funções que usa (`registrar`).
- `assets/`: as imagens e gifs dos cartões (veja "Cartões com imagem e texto").
- `ajuda.py`: os textos do `/ajuda` (um por comando, com exemplo e requisito) e as mensagens de bloqueio da criação. Quando um comando novo entrar, ele precisa de uma entrada aqui: o `tests/test_bot.py` confere isso.
- `dice.py`: notação de dados e as tabelas de sorteio (magia, raça, classe social, clero).
- `rules.py`: regras do sistema (XP e níveis, ganhos por nível, classes, perícias especiais, cálculo de recursos). Se uma regra mudar no site, muda aqui.
- `db.py`: banco SQLite (histórico, personagens, XP e extrato, vagas, ranks, personagens excluídos, registro das ações de mestre).
- `tests/`: testes automáticos (não conectam no Discord). Pra rodar, da pasta do bot: `python tests/test_rules.py`, `python tests/test_dice.py`, `python tests/test_ajuda.py`, `python tests/test_vitrine.py`, `python tests/test_cena.py`, `python tests/test_db.py` e `python tests/test_bot.py`. O `tests/legacy_schemas.py` guarda o formato exato dos bancos antigos, pra testar a migração.

## Bancos antigos

Ao iniciar, o bot atualiza sozinho um banco criado em versões anteriores (o esquema atual é a versão 12, e a atualização é só aditiva, nunca apaga nem reescreve coluna existente): as colunas e tabelas novas são criadas, quem já passou do nível 1 ganha os níveis de trás congelados com os atributos de hoje (a tabela `level_attributes`, que também guarda o atributo da época dali pra frente), o XP de cada personagem passa a ser o do começo do nível em que ele já estava, a raça que se chamava "Meio humano, meio vampiro" vira "Dhampir" e, no formato mais antigo de todos, cada definição por jogador vira um personagem com o nome do jogador.

## O que ainda falta

- Integrar esse histórico com o site (hoje são dois sistemas separados, sem comunicação entre eles).
- Os graus 4 e 5 das Disciplinas e os graus 1 a 3 da Sanguessugia ainda estão em aberto no sistema (o bot mostra "em aberto" e "em desenvolvimento").
- Pontos de perícia (25 na criação, +2 por nível) ainda não são controlados pelo bot.
