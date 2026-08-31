"""
Fala do apresentador, slide a slide, para a apresentacao em sala.

Diferente do roteiro do video: o pitch tem 5 minutos e precisa vender o
resultado. Aqui o objetivo e mostrar o CAMINHO — de onde os dados vieram, como
foram tratados e como viraram informacao. Por isso as notas citam consulta,
join, filtro e regra de agregacao pelo nome.

Entram no painel de anotacoes do proprio .pptx, entao viajam com o arquivo.

Chave: numero do slide (1 a 49).
"""
from __future__ import annotations

NOTAS: dict[int, str] = {

    1: """Bom dia. SaudeViz: um painel que transforma microdados publicos de
saude em resposta que um gestor consegue usar.

Vou mostrar de onde os dados vieram, o que precisou ser feito com eles, e como
viraram informacao. O produto final esta no ar e eu demonstro ao vivo no fim.""",

    2: """Trabalho individual. Lucas Colen, RM 569173, turma 1TSCOA.""",

    3: """Esses numeros sao o resultado da camada Ouro ja carregada no Oracle.

Cinco milhoes e meio de internacoes e o numero DEPOIS do tratamento. O bruto
que baixei do DATASUS foi sete milhoes. A diferenca de um milhao e meio nao e
perda: sao internacoes de 2023 e de 2025 que vieram junto, porque o SIH publica
por mes de pagamento, nao por mes de internacao. Volto nesse ponto, porque foi
ele que reorientou o projeto.

A consulta que gera esta tela e um SELECT com SUM de internacoes, SUM de
dias_permanencia e SUM de valor_total sobre a tabela fato, agrupando nada:
e o total geral.""",

    4: """Primeira entrega: o que prometi na Sprint 1 e o que de fato saiu.""",

    5: """Quatro itens entregues como prometido, dois entregues de forma
diferente, dois substituidos.

Os dois amarelos sao limitacao do ambiente, nao minha: o Select AI exige
Autonomous Database e a conta academica nao tem privilegio de criar diretorio.
Nos dois casos eu entreguei o script pronto e um substituto funcional.

Os dois cinzas sao decisao minha, e eu defendo cada uma na hora certa.""",

    6: """Quadro publico no Trello, 44 cartoes.

A quinta lista e a que interessa numa apresentacao academica: "nao
implementado, com justificativa". Um quadro todo verde esconde as decisoes de
escopo, que sao parte do trabalho. Cada cartao dessa lista tem o motivo tecnico
e o que foi entregue no lugar.""",

    7: """Segunda entrega: o MVP funcionando.""",

    8: """Este e o painel, publicado e conectado ao Oracle da FIAP.

Cada numero desta tela vem de uma consulta com agregacao empurrada para o
banco. Eu nao carrego a tabela e somo no Python: mando SUM e COUNT para o
Oracle e trago so o resultado. Isso importa porque a tabela fato tem centenas
de milhares de linhas, e trazer tudo para o cliente travava a tela.""",

    9: """A pergunta e "onde a capacidade foi ultrapassada".

Para responder eu precisei cruzar duas fontes que nao se conhecem: as
internacoes do SIH e os leitos do CNES. O join e por codigo IBGE de seis
digitos do municipio. Somo os leitos SUS de todos os estabelecimentos de cada
municipio, somo os dias de permanencia consumidos naquele mes, divido um pelo
outro e pelo numero de dias do mes. Isso da a taxa de ocupacao.

Repare nos dois numeros lado a lado: media simples e ponderada. A simples trata
um municipio de tres leitos igual a Sao Paulo. A distancia entre as barras e o
tamanho do erro que eu teria cometido se usasse a media ingenua.""",

    10: """A lista de municipios criticos sai de um filtro sobre a tabela de
indicador: situacao igual a 'Critica', ordenado por taxa de ocupacao
decrescente.

E eu declaro na tela que ocupacao acima de um e alerta para investigar, nao
prova de colapso. Pode ser leito desatualizado no CNES, ou municipio-polo
atendendo a regiao inteira. A ferramenta reduz mil seiscentos e sessenta e oito
municipios a uma lista de dezenas. A decisao continua humana.""",

    11: """Esta tela responde "quais perfis pressionam mais".

O perfil de atendimento nao existe no dado bruto: eu derivei do CID principal,
pegando os tres primeiros caracteres e classificando por faixa. J00 a J99 vira
respiratorio, S00 a T98 vira causa externa, F00 a F99 vira saude mental.

E o ranking nao e por volume. Eu ordeno por pressao relativa: a participacao no
total de leitos-dia dividida pela participacao no total de internacoes. Saude
mental fica no topo com 2,15 — ocupa o dobro de leito por internacao que a
media. Num painel ordenado por volume ela nem apareceria.""",

    12: """Terceira entrega: a arquitetura que de fato foi implementada.""",

    13: """O caminho completo do dado.

Quatro fontes publicas. A ingestao baixa e converte, o Databricks processa em
tres camadas, o Oracle guarda a camada de consumo, o Streamlit consulta.

A conversao do .dbc roda fora do Databricks de proposito: e formato
proprietario do DATASUS que exige extensao compilada em C e acesso FTP, os dois
pouco praticos em compute serverless.""",

    14: """Cada etapa esta onde esta por um motivo, e vale explicar a escolha.

O download local e por causa da biblioteca compilada. O processamento no
Databricks e porque sao sete milhoes de linhas — em pandas na minha maquina
isso daria quatorze giga de memoria e eu tenho cinco livres. Medi antes de
migrar.

O Oracle e a camada de servico: e dele que o painel consulta, e e nele que
estao os COMMENT ON que alimentam o tradutor de linguagem natural.""",

    15: """Isto nao e diagrama, e o catalogo real do Databricks.

As tres camadas existem como schemas separados. Bronze guarda o dado cru sem
transformar nada — se eu errar na Prata, reprocesso sem baixar sessenta
arquivos do DATASUS de novo. Essa e a razao de existir da camada Bronze.""",

    16: """A camada Ouro no Oracle: onze tabelas T_SAUDE.

Fatos, dimensoes e tabelas de indicador ja agregadas. O painel nao calcula
nada em tempo de tela: ele consulta indicador pronto. Isso e o que faz a tela
responder em segundos.""",

    17: """Esta e a prova de que o modelo esta integro.

Eu tenho tres tabelas construidas por caminhos diferentes: o fato agregado por
municipio e mes, o indicador de capacidade que faz join com os leitos, e o
ranking de hospitais agregado por CNES. Sao tres agregacoes independentes,
partindo de granularidades diferentes.

As tres somam exatamente cinco milhoes quinhentos e quarenta e seis mil
oitocentos e dezessete. Se eu tivesse duplicado linha num join ou perdido
registro num filtro, esses numeros divergiriam.""",

    18: """O que nao foi implementado, e por que.

Nos dois primeiros eu verifiquei no banco antes de desistir — nao presumi. No
Select AI, consultei o all_objects. Na External Table, consultei o
all_directories. Os dois retornaram vazio, e eu entreguei o DDL documentado
junto com a consulta que comprova.""",

    19: """Quarta entrega: como os dados foram obtidos, tratados e
transformados.""",

    20: """As fontes, e como cada uma e lida.

O SIH vem por FTP, em arquivo .dbc, um por estado e por mes: sessenta arquivos.
O CNES vem por API REST em JSON — e aqui teve armadilha: o parametro de UF da
API e silenciosamente ignorado. Eu recebia trinta e dois mil registros com
apenas mil e duzentos unicos, repetidos vinte e sete vezes. Descobri contando
distintos, e troquei para busca dirigida por codigo de estabelecimento.

O IBGE vem em CSV, e cumpre a exigencia do terceiro formato. A quarta fonte,
de clima, eu acrescentei por conta.""",

    21: """O .dbc do DATASUS e um DBF comprimido com um algoritmo antigo, o
PKWare DCL. Nenhuma biblioteca padrao le.

E teve um detalhe que custou tempo: a extensao C nao aceita acento no caminho
do arquivo. O projeto mora numa pasta chamada "Educacao/Ciencia de Dados", com
cedilha e acento. A solucao foi copiar cada arquivo para um diretorio
temporario de nome ASCII, converter la, e devolver.

E o tipo de problema que nao aparece em tutorial.""",

    22: """Esta e a descoberta que reorientou o projeto inteiro.

Eu criei uma coluna calculada chamada defasagem_faturamento: a diferenca em
meses entre a competencia do arquivo e o mes real da internacao. Agrupei por
ela e contei.

Sessenta por cento no mesmo mes. Quarenta por cento espalhados nos tres meses
seguintes. Ou seja: a competencia do SIH e o mes de PAGAMENTO da AIH, nao o da
internacao.

Se eu tivesse usado a competencia como eixo de tempo, meu painel responderia
uma pergunta financeira prometendo uma assistencial. Troquei a dimensao
temporal para a data de internacao e ampliei a ingestao ate marco de 2025, para
recuperar dezembro faturado com atraso.

Aqui tambem entram os filtros de qualidade: deduplicacao por numero de AIH
mantendo a versao mais recente, via row_number sobre uma janela particionada
por n_aih; descarte de permanencia fora de zero a trezentos e sessenta e cinco
dias; e descarte de valor negativo.""",

    23: """Dezesseis consultas SQL documentadas, cobrindo as quatro frentes do
desafio.

Cada uma tem a pergunta de negocio escrita antes do SQL, e a leitura do
resultado escrita depois. Nao e SQL solto: e pergunta, consulta, resposta.

Uma delas eu precisei reescrever depois de revisar: a Q11 calculava media
simples de leitos por cem mil habitantes entre municipios, o que da o mesmo
peso a uma cidade de cinco mil e a uma de doze milhoes. Reescrevi com CTE por
municipio, e a conclusao mudou: o Rio passou a ser o pior estado, nao Sao
Paulo.""",

    24: """Duas tecnicas estatisticas, e as duas com proposito.

O IQR de Tukey define o limite de outlier em 1,172. Eu tinha escolhido 1,0 como
limiar de alerta por raciocinio de negocio, antes de calcular isso. O criterio
estatistico, que nao sabe do meu limiar, confirma que ocupacao acima de um e
anomala nesta distribuicao.

A correlacao de Pearson entre ocupacao e transferencia da menos 0,305. Negativa:
municipios com baixa ocupacao transferem MAIS. Nao e contradicao — e a
assinatura de quem nao tem capacidade resolutiva, estabiliza o paciente e
encaminha.""",

    25: """Aqui eu testei duas abordagens e deixei o dado escolher.

A primeira: regressao com tendencia linear, sazonalidade em termos de Fourier e
variavel de feriado. A segunda: perfil semanal simples, que so aprende quanto
cada dia da semana desvia da media.

Validei com janela expansivel — treino no passado, teste no futuro, avancando.
Nunca com dado aleatorio, porque em serie temporal isso vaza o futuro para o
treino.

A regressao perdeu. O erro dela sobe de seis para vinte e sete por cento
conforme o horizonte cresce, porque a tendencia linear extrapola. O modelo
simples fica estavel em cinco e meio.

Reconhecer que a serie nao tem tendencia explorável valeu mais do que forcar
complexidade.""",

    26: """O sinal previsivel esta no calendario.

Sabado cai trinta e oito por cento, domingo quarenta e um, feriado vinte e
seis. E consistente nos quatro estados, com variacao de tres pontos entre eles.

E a leitura importa: isso nao e menos gente doente no fim de semana. E a rede
eletiva parada. Cirurgia programada nao acontece no domingo.""",

    27: """Quinta entrega: as evidencias visuais do que foi construido.""",

    28: """A previsao no painel, com intervalo de noventa e cinco por cento.

O intervalo vem do desvio dos residuos por dia da semana — nao e uma faixa
arbitraria: cada dia tem a sua propria incerteza histórica.""",

    29: """Este e o slide onde o painel deixa de descrever e passa a decidir.

O calculo: dias de permanencia consumidos no mes, divididos pelos dias do mes,
da o numero medio de leitos ocupados. Divido isso pela taxa de ocupacao alvo —
oitenta e cinco por cento — e tenho quantos leitos precisam estar abertos.

O mes de menor necessidade vira a demanda comum: o piso que a rede nao pode
desmobilizar. O que passa disso e capacidade sazonal.

Belo Horizonte: piso de 5.107, pico em abril de 5.904, e so 408 leitos de
folga. Seis por cento. O painel dispara o alerta sozinho.""",

    30: """Consultas de negocio rodando no Oracle, nao em parquet.

Este e o top dez de hospitais por volume, com a taxa de transferencia ao lado.
A Santa Casa de BH tem cinquenta e quatro mil internacoes e transfere zero
virgula dois por cento. E o perfil de quem resolve dentro de casa.""",

    31: """Onde as internacoes crescem: comparacao do segundo semestre contra o
primeiro, por municipio.

Usei CTE com SUM condicional — soma quando o mes e menor ou igual a seis, soma
quando e maior — e filtrei municipios com pelo menos quinhentas internacoes no
primeiro semestre. Sem esse filtro, uma cidade que saiu de duas para dez
internacoes apareceria com quatrocentos por cento de crescimento e lideraria o
ranking.""",

    32: """Quem exporta paciente.

Embu-Guacu tem mil quatrocentas e sessenta internacoes, mil e oitenta e duas
transferencias e quinze leitos. Setenta e quatro por cento dos pacientes seguem
para outro municipio.

Esse numero so existe porque eu incluí a coluna COBRANCA, que nao estava na
minha selecao inicial de vinte e quatro colunas. E antes de usar, validei o
mapeamento: os codigos quarenta e um a quarenta e tres somaram exatamente o
total da coluna MORTE. Confirmei o bloco de obito empiricamente, em vez de
confiar na documentacao.""",

    33: """Esta parte nao era exigida. Entrou para responder o criterio de
inovacao.""",

    34: """Uma quarta fonte publica: clima diario das quatro capitais, via
Open-Meteo.

Recorte nas capitais porque clima e local: a media do estado misturaria o
litoral capixaba com a serra mineira e apagaria qualquer sinal.

E as faixas de temperatura sao quartis calculados DENTRO de cada capital.
Dezoito graus e frio em Vitoria e ameno em Sao Paulo — um limiar absoluto
compararia climas diferentes como se fossem o mesmo.""",

    35: """Primeira hipotese: chuva aumenta internacao por acidente.

Refutada. Menos de um por cento de diferenca.

Mas o que sustenta a conclusao nao e a media: e o teste de gradiente. Se a
chuva causasse acidentes, o efeito cresceria de chuva fraca para forte. Ele
sobe e desce sem padrao, e o valor mais baixo vem de dezesseis dias apenas.

Resultado nulo bem medido tambem e resultado. A consequencia pratica: o
planejamento hospitalar nao deve reservar capacidade para dia de chuva.""",

    36: """Segunda hipotese: frio aumenta internacao respiratoria.

Confirmada. Nove por cento, e com gradiente monotonico nas quatro capitais,
cada uma calculada de forma independente. Quatro replicacoes do mesmo padrao e
mais forte que um numero agregado.""",

    37: """E um detalhe que reforca: a temperatura MAXIMA nao tem correlacao
nenhuma, ronda zero nas quatro cidades. Só a minima correlaciona.

E o frio da madrugada que se relaciona com internacao respiratoria, nao o calor
do dia. Se fosse ruido, as duas variaveis se moveriam juntas.""",

    38: """E aqui eu declaro o limite da propria analise.

A chuva aparece com correlacao negativa: dia chuvoso tem MENOS internacao
respiratoria. Contraintuitivo, ate lembrar que no Sudeste chove no verao e a
seca e no inverno. A chuva esta medindo a estacao, nao a si mesma.

O mesmo confundimento pode valer para o frio. Os nove por cento podem ser
efeito da temperatura, da sazonalidade viral, ou dos dois. E associacao, nao
causa.

Separar exigiria dado de circulacao viral por semana epidemiologica. Esta
registrado como proximo passo.""",

    39: """A parte de linguagem natural do desafio.""",

    40: """A pagina "Pergunte em portugues". Oito exemplos, e campo livre.""",

    41: """Duas perguntas diferentes gerando SQL sobre tabelas diferentes.

O tradutor pontua a pergunta contra um vocabulario de radicais com peso,
escolhe a intencao de maior pontuacao, extrai as entidades — estado, mes,
quantidade — e monta o SQL a partir de um modelo parametrizado.

E ele MOSTRA o SQL antes de executar. Isso e deliberado: num painel de saude
publica, quem decide precisa poder conferir de onde veio o numero.""",

    42: """Por que nao e o Select AI nativo.

Eu consultei o all_objects procurando o DBMS_CLOUD_AI. Retornou zero. O Select
AI so existe no Autonomous Database, e a instancia academica da FIAP e uma 19c
Enterprise.

Entao implementei o equivalente sobre exatamente os mesmos metadados: os
COMMENT ON das tabelas. Eu escrevi esses comentarios em linguagem de negocio de
proposito, desde o DDL, sabendo que seriam o dicionario do tradutor.

Migrar para o Autonomous nao exige remodelar nada. O script ja esta entregue.""",

    43: """Fechamento: repositorio, video e conclusoes.""",

    44: """O codigo esta todo publico no GitHub. Notebooks, pipeline de
ingestao, DDL, tradutor e painel.

E a camada Ouro esta versionada junto — cerca de seis mega de parquet. Isso
permite que qualquer pessoa reproduza o painel sem ter acesso ao Oracle da
FIAP.""",

    45: """O video de cinco minutos com a demonstracao ao vivo.""",

    46: """Tres coisas que os dados me ensinaram, e que eu nao sabia quando
comecei.

A primeira mudou a dimensao temporal do projeto inteiro. A segunda mudou a
pergunta que o painel responde. A terceira me fez descartar o modelo mais
sofisticado em favor do mais simples.

Nenhuma das tres estava no plano da Sprint 1.""",

    47: """E o que este painel NAO pode afirmar.

Declarar limite nao enfraquece o trabalho: e o que separa analise de opiniao
com grafico. Cada um desses itens eu medi antes de declarar — inclusive o menos
de um por cento dos leitos-dia de pacientes internados antes de 2024.""",

    48: """Os proximos passos saem direto das limitacoes do slide anterior.

Nenhum deles exige refazer o que esta feito: o pipeline ja e parametrizado por
estado, e a migracao para o Autonomous e troca de motor, nao de modelo.""",

    49: """O painel esta no ar e o codigo esta aberto.

Obrigado.""",
}
